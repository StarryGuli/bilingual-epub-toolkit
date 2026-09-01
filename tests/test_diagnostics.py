"""What a failure report contains, and what it must never contain."""
import json
import os

from bilingual_epub import diagnostics


def test_fingerprint_describes_structure(en_epub):
    fp = diagnostics.fingerprint(en_epub)
    assert fp['is_zip'] is True
    assert fp['has_container'] is True
    assert fp['has_mimetype'] is True
    assert fp['mimetype'] == 'application/epub+zip'
    assert fp['opf'], 'should locate the OPF'
    assert fp['entries'] > 0
    assert fp['by_extension'].get('.xhtml')


def test_fingerprint_carries_no_book_text(en_epub, tmp_path):
    """The whole point: enough to debug, nothing to read."""
    blob = json.dumps(diagnostics.fingerprint(en_epub), ensure_ascii=False)
    for sentence in ('bright cold day', 'Nobody had ever seen',
                     'The clock on the square', 'Chapter One'):
        assert sentence not in blob, 'prose leaked into the report: %r' % sentence


def test_entry_names_are_shape_only():
    """A filename can name the book through an ISBN; keep only its shape."""
    got = diagnostics._anon_name('OEBPS/xhtml/Kros_9780525575252_epub3_c01_r1.xhtml')
    assert '9780525575252' not in got
    assert 'Kros' not in got, 'a truncated author name still names the book'
    assert got.endswith('.xhtml')
    assert got.startswith('OEBPS/xhtml/')


def test_entry_names_are_flattened_in_every_script():
    """Matching only [A-Za-z] would let a Chinese or Cyrillic title through
    untouched, which for this tool's audience is the common case."""
    zh = diagnostics._anon_name('OEBPS/\u60b2\u60e8\u4e16\u754c-\u7b2c\u4e09\u5377.xhtml')
    assert '\u60b2\u60e8\u4e16\u754c' not in zh
    assert zh == 'OEBPS/x-x.xhtml'
    ru = diagnostics._anon_name('OEBPS/text/\u0412\u043e\u0439\u043d\u0430_01.xhtml')
    assert '\u0412\u043e\u0439\u043d\u0430' not in ru


def test_fingerprint_flags_a_file_that_is_not_a_zip(tmp_path):
    junk = tmp_path / 'nope.epub'
    junk.write_bytes(b'this is not a zip at all')
    fp = diagnostics.fingerprint(str(junk))
    assert fp['is_zip'] is False
    assert fp['bad_zip'] is True
    assert fp['bytes'] == 24


def test_fingerprint_survives_a_missing_file():
    fp = diagnostics.fingerprint('/nonexistent/gone.epub')
    assert fp['bytes'] is None
    assert fp['is_zip'] is False


def test_record_writes_one_json_line_per_failure(en_epub, tmp_path):
    log = str(tmp_path / 'sub' / 'errors.jsonl')
    diagnostics.record(log, '/api/merge', SystemExit('not a valid EPUB'), [en_epub])
    diagnostics.record(log, '/api/split', ValueError('boom'), [en_epub])
    lines = open(log, encoding='utf-8').read().strip().split('\n')
    assert len(lines) == 2
    first, second = json.loads(lines[0]), json.loads(lines[1])
    assert first['endpoint'] == '/api/merge'
    assert first['error_type'] == 'SystemExit'
    assert 'traceback' not in first, 'a readable error needs no traceback'
    assert second['error_type'] == 'ValueError'
    assert first['inputs'][0]['is_zip'] is True
    assert first['at'].endswith('+00:00')


def test_record_never_raises(tmp_path):
    """Diagnostics must not be able to fail a request."""
    diagnostics.record('/proc/cannot/write/here.jsonl', '/api/merge',
                       ValueError('x'), ['/nonexistent'])
    assert not os.path.exists('/proc/cannot/write/here.jsonl')


def test_scrub_drops_data_paths_but_keeps_source_paths():
    """The path an engine error quotes ends in the name the user uploaded,
    which is usually the book's title. The toolkit's own .py paths are the
    useful half of a traceback and stay."""
    msg = "not a valid EPUB: '/var/tmp/sessions/abc/悲惨世界.epub'"
    assert '悲惨世界' not in diagnostics.scrub(msg)
    assert '<path>' in diagnostics.scrub(msg)

    tb = 'File "/opt/app/lib/bilingual_epub/merge.py", line 12, in merge'
    assert 'merge.py' in diagnostics.scrub(tb), 'source location is the point'


def test_recorded_error_carries_no_uploaded_filename(tmp_path):
    log = str(tmp_path / 'e.jsonl')
    book = tmp_path / '悲惨世界.epub'
    book.write_bytes(b'not a zip')
    diagnostics.record(log, '/api/merge',
                       SystemExit("bad EPUB: '%s'" % book), [str(book)])
    blob = open(log, encoding='utf-8').read()
    assert '悲惨世界' not in blob, 'book title leaked into the log'
    assert json.loads(blob)['inputs'][0]['bad_zip'] is True
