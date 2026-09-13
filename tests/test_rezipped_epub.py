"""EPUBs that were unzipped and zipped again.

Two reports on the hosted instance, one Chinese book and one English, were
both this: macOS expands an .epub on download when the server sends it as a
generic archive, and compressing the folder afterwards produces a zip whose
entries all live under one directory, with a __MACOSX sidecar beside it.

The book inside is untouched and valid. Only the extra layer is wrong, and it
is invisible to the person uploading -- the file still ends in .epub or .zip
and still opens in their reader. Rejecting it taught them nothing, so these
pin that it loads.
"""
import zipfile

import pytest

from bilingual_epub import epub_io, merge_bilingual
from bilingual_epub.errors import UserFacing


def rewrap(src, dest, prefix, macosx=True, depth=1):
    """Rebuild an EPUB the way Archive Utility would, under `prefix`."""
    folder = '/'.join([prefix] * depth) if depth > 1 else prefix
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, 'w') as zout:
        for name in zin.namelist():
            zout.writestr('%s/%s' % (folder, name), zin.read(name))
            if macosx and name.endswith(('.opf', '.xhtml', '.html')):
                # the sidecar mirrors the real tree, which is why the search
                # for container.xml has to skip it rather than walk into it
                head, _, tail = name.rpartition('/')
                zout.writestr('__MACOSX/%s/%s%s._%s'
                              % (folder, head, '/' if head else '', tail),
                              b'\x00\x05\x16\x07')
    return dest


def test_a_rezipped_epub_still_loads(en_epub, tmp_path):
    wrapped = rewrap(en_epub, tmp_path / 'wrapped.zip', 'The Invented Town.epub')
    doc = epub_io.load(str(wrapped), str(tmp_path / 'x'))
    assert doc.metadata['title'] == 'The Invented Town'
    assert doc.spine_doc_paths(), 'spine resolved against the wrong root'


def test_the_macosx_sidecar_is_not_mistaken_for_the_book(en_epub, tmp_path):
    """__MACOSX mirrors the directory tree, so a naive search finds it too."""
    wrapped = rewrap(en_epub, tmp_path / 'w.zip', 'Book.epub', macosx=True)
    doc = epub_io.load(str(wrapped), str(tmp_path / 'x'))
    assert '__MACOSX' not in doc.root_dir


def test_both_sides_rezipped_merge_normally(en_epub, fr_epub, tmp_path):
    """The reported case: both uploads came out of the same archive tool."""
    a = rewrap(en_epub, tmp_path / 'a.zip', 'English.epub')
    b = rewrap(fr_epub, tmp_path / 'b.zip', 'Francais.epub')
    out, stats = merge_bilingual(str(a), str(b), str(tmp_path / 'bi.epub'))
    assert zipfile.is_zipfile(out)
    assert stats, 'merged but produced no chapters'


def test_order_does_not_matter(en_epub, fr_epub, tmp_path):
    """Reported as an A/B asymmetry; it never was one. Pinned so that a future
    fallback cannot quietly work on one side only."""
    a = rewrap(en_epub, tmp_path / 'a.zip', 'English.epub')
    b = rewrap(fr_epub, tmp_path / 'b.zip', 'Francais.epub')
    one, _s = merge_bilingual(str(a), str(b), str(tmp_path / 'ab.epub'))
    two, _s = merge_bilingual(str(b), str(a), str(tmp_path / 'ba.epub'))
    assert zipfile.is_zipfile(one) and zipfile.is_zipfile(two)


def test_nested_two_levels_deep(en_epub, tmp_path):
    wrapped = rewrap(en_epub, tmp_path / 'deep.zip', 'books', depth=2)
    doc = epub_io.load(str(wrapped), str(tmp_path / 'x'))
    assert doc.metadata['title'] == 'The Invented Town'


def test_two_books_in_one_archive_is_refused_not_guessed(en_epub, fr_epub,
                                                         tmp_path):
    both = tmp_path / 'both.zip'
    with zipfile.ZipFile(both, 'w') as zout:
        for src, prefix in ((en_epub, 'en.epub'), (fr_epub, 'fr.epub')):
            with zipfile.ZipFile(src) as zin:
                for name in zin.namelist():
                    zout.writestr('%s/%s' % (prefix, name), zin.read(name))
    with pytest.raises(UserFacing, match='2'):
        epub_io.load(str(both), str(tmp_path / 'x'))


def test_a_zip_that_is_not_a_book_still_reports_clearly(tmp_path):
    junk = tmp_path / 'junk.zip'
    with zipfile.ZipFile(junk, 'w') as z:
        z.writestr('notes/todo.txt', 'nothing to see')
    with pytest.raises(UserFacing) as exc:
        epub_io.load(str(junk), str(tmp_path / 'x'))
    # the message names what to do, not what is missing from the container
    assert 'META-INF' not in str(exc.value)
    assert '.epub' in str(exc.value)
