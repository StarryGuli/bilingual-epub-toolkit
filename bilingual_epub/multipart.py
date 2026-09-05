"""Streaming multipart/form-data parsing.

The first version of this read the whole request body with rfile.read(length)
and then split() it on the boundary. That holds the upload twice -- once as the
body, once as the pieces -- so two 40 MB books cost well over 160 MB before any
book is even opened, and the service was OOM-killed nine times in a week
because of it. Raising the memory limit only moved the ceiling; the process
grew to whatever it was given and died there.

So file parts are written straight to disk as they arrive and never held whole
in memory. Peak usage is a fixed buffer regardless of upload size.

The fiddly part of streaming multipart is that a boundary can straddle a chunk
edge. The rule here: never emit the last len(boundary)+4 bytes of the buffer,
because they might turn out to be the start of one.
"""
import os
import re
import tempfile

CHUNK = 64 * 1024
MAX_FIELD = 1024 * 1024          # a text field this large is not a text field

_DISPOSITION = re.compile(r'(\w+)="([^"]*)"')


class TooLarge(Exception):
    """The body exceeded the caller's ceiling."""


def _headers_of(raw):
    out = {}
    for line in raw.decode('utf-8', 'replace').split('\r\n'):
        name, _, value = line.partition(':')
        if value:
            out[name.strip().lower()] = value.strip()
    return out


def parse(stream, boundary, content_length, dest_dir, max_bytes=None):
    """Read a multipart body, spilling file parts to files in dest_dir.

    Returns (fields, files):
      fields -- {name: str} for ordinary form fields
      files  -- {name: (client_filename, path_on_disk)}

    Raises TooLarge if the declared or actual length exceeds max_bytes.
    """
    if max_bytes is not None and content_length > max_bytes:
        raise TooLarge()

    delim = b'--' + boundary
    keep = len(delim) + 4          # never emit bytes that might begin a boundary
    fields, files = {}, {}

    buf = b''
    remaining = content_length
    finished = False

    def refill():
        """Pull one chunk off the wire. -> False at end of body."""
        nonlocal buf, remaining
        if remaining <= 0:
            return False
        block = stream.read(min(CHUNK, remaining))
        if not block:
            remaining = 0
            return False
        remaining -= len(block)
        buf += block
        return True

    # skip the preamble up to the first boundary
    while delim not in buf:
        if not refill():
            return fields, files
    buf = buf[buf.index(delim) + len(delim):]

    while not finished:
        # a boundary is followed by "--" at the end of the body, else CRLF
        while len(buf) < 2 and refill():
            pass
        if buf[:2] == b'--':
            break
        buf = buf[2:] if buf[:2] == b'\r\n' else buf

        # ---- part headers ----
        while b'\r\n\r\n' not in buf:
            if not refill():
                return fields, files
        head, _, buf = buf.partition(b'\r\n\r\n')
        headers = _headers_of(head)
        attrs = dict(_DISPOSITION.findall(headers.get('content-disposition', '')))
        name = attrs.get('name')
        filename = attrs.get('filename')

        sink = None
        path = None
        if filename:
            # one directory per part so the client's filename cannot collide
            # with another part's, and cannot escape dest_dir
            slot = tempfile.mkdtemp(dir=dest_dir)
            path = os.path.join(slot, os.path.basename(filename) or 'upload.bin')
            sink = open(path, 'wb')
        collected = bytearray()

        # ---- part body ----
        try:
            while True:
                at = buf.find(b'\r\n' + delim)
                if at >= 0:
                    piece, buf = buf[:at], buf[at + 2 + len(delim):]
                    if sink:
                        sink.write(piece)
                    else:
                        collected += piece
                    break
                # hold back what could still become a boundary
                if len(buf) > keep:
                    piece, buf = buf[:-keep], buf[-keep:]
                    if sink:
                        sink.write(piece)
                    else:
                        collected += piece
                        if len(collected) > MAX_FIELD:
                            raise TooLarge()
                if not refill():
                    # truncated body: keep what arrived, stop cleanly
                    if sink:
                        sink.write(buf)
                    else:
                        collected += buf
                    buf = b''
                    finished = True
                    break
        finally:
            if sink:
                sink.close()

        if name:
            if filename:
                if os.path.getsize(path) > 0:
                    files[name] = (filename, path)
            else:
                fields[name] = bytes(collected).decode('utf-8', 'replace')

    return fields, files
