"""What the person on the other end is told when their file cannot be used.

The rule these enforce: a problem with the file is explained in the reader's
own language and says what to do; a defect in this program says so plainly and
offers the report button. Neither ever shows a path, an exception name, or a
part of the EPUB specification.

This is pinned because the failure mode was silent. The loader raised
ValueError, the web interface treated every ValueError as a crash, and so a
book that had merely been zipped twice produced "the details are in the
terminal running this server" -- a terminal belonging to someone else. The
sentence explaining the real cause existed the whole time and never arrived.
"""
import pytest

from bilingual_epub import epub_io, i18n
from bilingual_epub.errors import UserFacing

#: every message a reader can be shown for a file this tool cannot use,
#: with whatever that message interpolates
READER_MESSAGES = {
    'err.not_epub': (),
    'err.no_book_in': (),
    'err.many_books': (2,),
    'err.damaged_index': (),
    'err.no_order': (),
    'err.no_text': ('A side (original)',),
    'err.missing_file': ('book.epub',),
    'web.crashed': (),
    'web.file_note': (),
}
READER_KEYS = sorted(READER_MESSAGES)

JARGON = ['META-INF', 'container.xml', 'OPF', '<spine>', 'Traceback',
          'ValueError', 'SystemExit', 'stderr', 'stdout']


@pytest.fixture(autouse=True)
def _restore_language():
    before = i18n.get_lang()
    yield
    i18n.set_lang(before)


@pytest.mark.parametrize('key', READER_KEYS)
@pytest.mark.parametrize('lang', ['en', 'zh'])
def test_every_reader_message_exists_in_both_languages(key, lang):
    i18n.set_lang(lang)
    text = i18n.t(key, *READER_MESSAGES[key])
    assert text and not text.startswith('%'), '%s missing for %s' % (key, lang)
    assert text != key, '%s falls through untranslated in %s' % (key, lang)


@pytest.mark.parametrize('key', READER_KEYS)
@pytest.mark.parametrize('lang', ['en', 'zh'])
def test_reader_messages_carry_no_jargon(key, lang):
    i18n.set_lang(lang)
    text = i18n.t(key, *READER_MESSAGES[key])
    for term in JARGON:
        assert term not in text, '%s (%s) exposes %r to a reader' % (key, lang, term)


def test_the_message_follows_the_readers_language(tmp_path):
    """Raised by the engine, read by the interface, possibly in between a
    language switch -- so it resolves on access, not on raise."""
    junk = tmp_path / 'junk.epub'
    junk.write_bytes(b'not a zip')
    i18n.set_lang('zh')
    try:
        epub_io.load(str(junk), str(tmp_path / 'x'))
    except UserFacing as e:
        zh = str(e)
        i18n.set_lang('en')
        en = str(e)
    assert 'EPUB' in zh and 'DRM' in zh
    assert zh != en, 'the same object rendered the same text in both languages'
    assert 'download' in en.lower()


def test_a_file_problem_is_not_reported_as_a_crash(tmp_path):
    """The distinction the web interface depends on."""
    junk = tmp_path / 'junk.epub'
    junk.write_bytes(b'not a zip')
    with pytest.raises(UserFacing):
        epub_io.load(str(junk), str(tmp_path / 'x'))


def test_reader_messages_say_what_to_do(tmp_path):
    """Not a style rule: every one of these was reached by a real upload, and
    an explanation with no next step is what produced the repeat attempts in
    the log -- the same file, four times in four minutes."""
    i18n.set_lang('en')
    actionable = ('again', 'upload', 'check', 'report', 'instead', 'cannot')
    for key in ['err.not_epub', 'err.no_book_in', 'err.many_books',
                'err.damaged_index', 'err.no_order', 'web.crashed']:
        text = i18n.t(key, *READER_MESSAGES[key]).lower()
        assert any(w in text for w in actionable), \
            '%s explains the cause but gives the reader nothing to do' % key


def textless_epub(path):
    """A structurally valid EPUB whose spine document holds no block text."""
    import zipfile
    with zipfile.ZipFile(path, 'w') as z:
        zi = zipfile.ZipInfo('mimetype')
        zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, 'application/epub+zip')
        z.writestr('META-INF/container.xml',
                   '<?xml version="1.0"?><container version="1.0" xmlns='
                   '"urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="c.opf" media-type='
                   '"application/oebps-package+xml"/></rootfiles></container>')
        z.writestr('c.opf',
                   '<?xml version="1.0"?><package xmlns="http://www.idpf.org/'
                   '2007/opf" version="3.0"><metadata/><manifest><item id="a" '
                   'href="a.xhtml" media-type="application/xhtml+xml"/>'
                   '</manifest><spine><itemref idref="a"/></spine></package>')
        z.writestr('a.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml">'
                              '<body></body></html>')
    return str(path)


def test_an_interpolated_label_follows_the_language_too(en_epub, tmp_path):
    """The side label is part of the sentence, so it has to travel as a key.

    Resolving it where the engine raises looks identical in English and
    produces "无法从A side (original)读取到任何正文" for everyone else.
    """
    from bilingual_epub import merge_bilingual

    blank = textless_epub(tmp_path / 'blank.epub')
    i18n.set_lang('zh')
    with pytest.raises(UserFacing) as exc:
        merge_bilingual(blank, str(en_epub), str(tmp_path / 'out.epub'))
    zh = str(exc.value)
    i18n.set_lang('en')
    en = str(exc.value)
    assert 'side' not in zh, 'English leaked into the Chinese sentence: %s' % zh
    assert 'A 侧' in zh
    assert 'A side' in en


# --------------------------------------------------------------------------- #
# the way out of a wrong diagnosis
# --------------------------------------------------------------------------- #

def test_every_failure_offers_a_way_to_disagree():
    """The report route is not reserved for failures this tool cannot explain.

    A confident sentence reads as a verdict. "The download did not finish" is
    inferred from the file's structure and is sometimes simply wrong -- the
    reader may have a book that opens perfectly in their own app -- and if the
    only invitation to report appears on unrecognised errors, the cases most
    worth hearing about are the ones that stay silent.
    """
    page = _rendered_page()
    assert 'reportWrong' in page, 'the failure card offers no way to push back'
    for lang in ('en', 'zh'):
        i18n.set_lang(lang)
        text = i18n.t('web.report.wrong')
        assert text and text != 'web.report.wrong'


def test_the_invitation_admits_the_reason_may_be_wrong():
    for lang, words in (('en', ('wrong', 'report')), ('zh', ('判断错误', '报告'))):
        i18n.set_lang(lang)
        text = i18n.t('web.report.wrong')
        for w in words:
            assert w in text, '%s (%s) does not admit it may be mistaken' % (w, lang)


def _rendered_page():
    from bilingual_epub import webui
    return webui.render_page(webui.Config(public=True), 'tok', reports_on=True)


def test_the_report_line_is_absent_when_reporting_is_off():
    from bilingual_epub import webui
    page = webui.render_page(webui.Config(public=True), 'tok', reports_on=False)
    assert 'canReport": false' in page or "'canReport': False" in page or \
        '"canReport":false' in page.replace(' ', ''), \
        'reporting must be off when no reports directory is configured'


def test_the_converter_message_matches_who_is_reading_it(monkeypatch):
    """A hosted reader cannot run pip on someone else's server.

    Reached live: a page that offers simplified/traditional conversion, on a
    server without the converter installed, answered a reader with
    "pip3 install opencc-python-reimplemented".
    """
    from bilingual_epub import merge as merge_mod
    monkeypatch.setattr(merge_mod, 'opencc', None)
    i18n.set_lang('zh')

    monkeypatch.setenv('BILINGUAL_EPUB_HOSTED', '1')
    with pytest.raises(UserFacing) as hosted:
        merge_mod._cc('s2t')
    assert 'pip' not in str(hosted.value)
    assert '不转换' in str(hosted.value), 'no way forward was offered'

    monkeypatch.delenv('BILINGUAL_EPUB_HOSTED')
    with pytest.raises(UserFacing) as local:
        merge_mod._cc('s2t')
    assert 'pip install' in str(local.value), 'the terminal should say what to install'
