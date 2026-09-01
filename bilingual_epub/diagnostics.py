"""What to record when a job fails, and what not to record.

A hosted instance sees failures its operator cannot reproduce, because the
file that caused them belongs to someone else. The obvious fix -- keep the
uploads -- is the wrong one: these are books, almost always still in copyright,
and a server that accumulates them is a liability far out of proportion to the
debugging it buys. It also asks users to hand over their reading history to
get a bug fixed.

Nothing here needs the text. The failures this tool actually produces are
structural: a missing OPF, a spine pointing at files that are not there, XHTML
that will not parse, a zip that is not an EPUB. All of that is visible in the
*shape* of the file, so that is what gets recorded -- entry names, sizes,
counts, and the parser's own complaint. The prose never leaves the request.

The result is a line of JSON per failure that is usually enough to write a
regression test from, and that could be published without exposing anything
about the book or the person who uploaded it.
"""
import datetime
import json
import os
import re
import threading
import traceback
import zipfile

_LOCK = threading.Lock()

#: Entry names are structural, but a filename can carry the book's identity --
#: "Kros_9780525575252_epub3_c01_r1.xhtml" gives away both author and ISBN.
#: Only the *pattern* is diagnostically useful (how many segments, digits vs
#: letters, the extension), so letters and digits are both flattened. Two
#: traps here: keeping letter runs intact is not enough, because a truncated
#: author name still names the book; and matching only [A-Za-z] leaks every
#: non-Latin script untouched, which for this tool's audience means Chinese
#: titles passing through in full.
_RUNS = re.compile(r'[^\W\d_]+|\d+', re.UNICODE)


def _anon_name(name):
    head, tail = os.path.split(name)
    stem, ext = os.path.splitext(tail)
    shape = _RUNS.sub(lambda m: '#' if m.group()[0].isdigit() else 'x', stem)
    return '%s%s%s%s' % (head, '/' if head else '', shape[:32], ext)


def fingerprint(path, max_entries=40):
    """Describe an EPUB's structure without reading its prose."""
    out = {'bytes': None, 'is_zip': False}
    try:
        out['bytes'] = os.path.getsize(path)
    except OSError:
        return out
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            out['is_zip'] = True
            out['entries'] = len(names)
            out['has_container'] = 'META-INF/container.xml' in names
            out['has_mimetype'] = 'mimetype' in names
            out['opf'] = [n for n in names if n.endswith('.opf')][:3]
            out['encrypted'] = any(n.endswith('encryption.xml') for n in names)
            exts = {}
            for n in names:
                exts[os.path.splitext(n)[1].lower() or '(none)'] = \
                    exts.get(os.path.splitext(n)[1].lower() or '(none)', 0) + 1
            out['by_extension'] = dict(sorted(exts.items(), key=lambda kv: -kv[1])[:10])
            out['sample_entries'] = [_anon_name(n) for n in names[:max_entries]]
            if out['has_mimetype']:
                try:
                    out['mimetype'] = zf.read('mimetype')[:64].decode('ascii', 'replace')
                except Exception:
                    out['mimetype'] = '(unreadable)'
    except zipfile.BadZipFile:
        out['bad_zip'] = True
    except Exception as e:
        out['inspect_error'] = type(e).__name__
    return out


#: Engine errors quote the path they failed on, and that path ends in the name
#: the user uploaded -- often the book's title. Those have to go. Paths ending
#: in .py are the toolkit's own source and are the most useful part of a
#: traceback, so they stay: the rule is "drop where the data lives, keep where
#: the code lives".
_PATHS = re.compile(r"(?:/[^\s'\"/]+)+/?")


def scrub(text):
    """Remove filesystem paths that could name a user's file."""
    def repl(m):
        p = m.group()
        return p if p.endswith('.py') else '<path>'
    return _PATHS.sub(repl, text or '')


def record(log_path, endpoint, error, inputs=(), extra=None):
    """Append one JSON line describing a failure. Never raises."""
    try:
        entry = {
            'at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
            'endpoint': endpoint,
            'error_type': type(error).__name__,
            'error': scrub(str(error))[:800],
            'inputs': [fingerprint(p) for p in inputs if p],
        }
        if not isinstance(error, SystemExit):
            entry['traceback'] = scrub(traceback.format_exc())[-3000:]
        if extra:
            entry.update(extra)
        line = json.dumps(entry, ensure_ascii=False)
        with _LOCK:
            d = os.path.dirname(log_path)
            if d and not os.path.isdir(d):
                os.makedirs(d)
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
    except Exception:
        pass        # diagnostics must never be the reason a request fails
