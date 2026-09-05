"""Streaming multipart parsing.

The point of this module is constant memory, so the tests deliberately feed it
bodies in awkward pieces: boundaries split across chunk edges, binary content,
several parts at once.
"""
import io
import os

import pytest

from bilingual_epub import multipart

B = b'----test-boundary-12345'


def build(parts):
    """parts: [(name, filename_or_None, bytes)] -> body bytes"""
    out = b''
    for name, filename, data in parts:
        disp = 'form-data; name="%s"' % name
        if filename:
            disp += '; filename="%s"' % filename
        out += b'--' + B + b'\r\n'
        out += b'Content-Disposition: ' + disp.encode('utf-8') + b'\r\n\r\n'
        out += data + b'\r\n'
    return out + b'--' + B + b'--\r\n'


class Trickle(io.BytesIO):
    """A stream that returns tiny reads, so boundaries land across chunks."""

    def __init__(self, data, size=7):
        super().__init__(data)
        self.size = size

    def read(self, n=-1):
        return super().read(min(n, self.size) if n and n > 0 else self.size)


def test_fields_and_files(tmp_path):
    body = build([('page_token', None, b'abc123'),
                  ('a_file', 'book.epub', b'PK\x03\x04binary\x00content')])
    fields, files = multipart.parse(io.BytesIO(body), B, len(body), str(tmp_path))
    assert fields == {'page_token': 'abc123'}
    assert set(files) == {'a_file'}
    name, path = files['a_file']
    assert name == 'book.epub'
    assert open(path, 'rb').read() == b'PK\x03\x04binary\x00content'


def test_survives_boundaries_split_across_reads(tmp_path):
    """The whole reason this is hard: a boundary can straddle a chunk edge."""
    payload = bytes(range(256)) * 40
    body = build([('a_file', 'x.epub', payload), ('note', None, b'ok')])
    fields, files = multipart.parse(Trickle(body, 7), B, len(body), str(tmp_path))
    assert open(files['a_file'][1], 'rb').read() == payload
    assert fields['note'] == 'ok'


def test_content_that_merely_resembles_a_boundary(tmp_path):
    """A book containing the boundary text minus the CRLF must not be cut."""
    payload = b'before--' + B + b'after'
    body = build([('a_file', 'x.epub', payload)])
    _f, files = multipart.parse(Trickle(body, 5), B, len(body), str(tmp_path))
    assert open(files['a_file'][1], 'rb').read() == payload


def test_two_files_land_in_separate_paths(tmp_path):
    body = build([('a_file', 'same.epub', b'AAA'), ('b_file', 'same.epub', b'BBB')])
    _f, files = multipart.parse(io.BytesIO(body), B, len(body), str(tmp_path))
    pa, pb = files['a_file'][1], files['b_file'][1]
    assert pa != pb, 'identical client names must not collide'
    assert open(pa, 'rb').read() == b'AAA'
    assert open(pb, 'rb').read() == b'BBB'


def test_empty_file_part_is_dropped(tmp_path):
    """An untouched <input type=file> submits an empty part."""
    body = build([('a_file', '', b''), ('note', None, b'x')])
    fields, files = multipart.parse(io.BytesIO(body), B, len(body), str(tmp_path))
    assert files == {}
    assert fields['note'] == 'x'


def test_refuses_a_body_over_the_ceiling(tmp_path):
    body = build([('a_file', 'x.epub', b'0' * 5000)])
    with pytest.raises(multipart.TooLarge):
        multipart.parse(io.BytesIO(body), B, len(body), str(tmp_path),
                        max_bytes=1000)


def test_filename_cannot_escape_the_destination(tmp_path):
    body = build([('a_file', '../../etc/passwd', b'nope')])
    _f, files = multipart.parse(io.BytesIO(body), B, len(body), str(tmp_path))
    path = os.path.realpath(files['a_file'][1])
    assert path.startswith(os.path.realpath(str(tmp_path)) + os.sep)
    assert 'etc/passwd' not in path


def test_memory_stays_flat_for_a_large_upload(tmp_path):
    """The regression that mattered: a big body must not be held in memory."""
    big = os.urandom(4 * 1024 * 1024)
    body = build([('a_file', 'big.epub', big)])

    peak = {'n': 0}
    real_read = io.BytesIO.read

    class Watched(io.BytesIO):
        def read(self, n=-1):
            peak['n'] = max(peak['n'], n if n and n > 0 else 0)
            return real_read(self, n)

    _f, files = multipart.parse(Watched(body), B, len(body), str(tmp_path))
    assert open(files['a_file'][1], 'rb').read() == big
    assert peak['n'] <= multipart.CHUNK, 'never asked for more than one chunk'
