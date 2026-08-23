# -*- coding: utf-8 -*-
"""End-to-end tests: merge -> split -> re-merge, plus the option surface.

These are the checks that caught the real bug during development (chapter
headings being rendered twice, once without a lang attribute, which corrupted
the split step) -- so they assert on structure, not just on "it didn't crash".
"""
import os
import zipfile

import pytest

from bilingual_epub import merge_bilingual, split_by_lang


def read_chapter(epub_path, name='OEBPS/text/ch001.xhtml'):
    with zipfile.ZipFile(epub_path) as zf:
        return zf.read(name).decode('utf-8')


def chapter_names(epub_path):
    with zipfile.ZipFile(epub_path) as zf:
        return sorted(n for n in zf.namelist() if n.startswith('OEBPS/text/ch'))


# --------------------------------------------------------------------------- #
# merge
# --------------------------------------------------------------------------- #

def test_merge_produces_valid_epub(en_epub, fr_epub, tmp_path):
    out = str(tmp_path / 'bi.epub')
    result, stats = merge_bilingual(en_epub, fr_epub, out)

    assert os.path.exists(result)
    with zipfile.ZipFile(result) as zf:
        names = zf.namelist()
        # mimetype must be first and stored uncompressed, per the EPUB spec
        assert names[0] == 'mimetype'
        assert zf.getinfo('mimetype').compress_type == zipfile.ZIP_STORED
        assert zf.read('mimetype') == b'application/epub+zip'
        assert 'META-INF/container.xml' in names
        assert 'OEBPS/content.opf' in names
        assert 'OEBPS/nav.xhtml' in names
    assert len(stats) == 3, 'three source chapters should yield three chapters'


def test_merge_aligns_paragraphs_one_to_one(en_epub, fr_epub, tmp_path):
    _out, stats = merge_bilingual(en_epub, fr_epub, str(tmp_path / 'bi.epub'))
    total_11 = sum(row[3] for row in stats)
    total_other = sum(row[4] + row[5] + row[6] for row in stats)
    assert total_11 == 10, 'these two fixtures align perfectly'
    assert total_other == 0


def test_merge_tags_each_side_with_its_own_language(en_epub, fr_epub, tmp_path):
    out = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, out)
    html = read_chapter(out)
    assert 'lang="en"' in html
    assert 'lang="fr"' in html
    # b-side is the blurred/tap-to-reveal one by default
    assert 'class="b blurred"' in html
    assert 'class="a blurred"' not in html


def test_chapter_heading_appears_exactly_once(en_epub, fr_epub, tmp_path):
    """Regression: headings were once emitted twice -- as an untagged banner
    and again inline -- which duplicated text and broke language bucketing."""
    out = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, out)
    html = read_chapter(out)
    assert html.count('Chapter One: The Beginning') == 2, (
        'expected exactly two occurrences: the <title> element and one inline '
        'heading -- a third means the duplicate banner is back')


def test_blur_side_can_be_flipped(en_epub, fr_epub, tmp_path):
    out = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, out, blur_side='a')
    html = read_chapter(out)
    assert 'class="a blurred"' in html
    assert 'class="b blurred"' not in html


def test_blur_can_be_disabled(en_epub, fr_epub, tmp_path):
    out = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, out, blur_side='none')
    html = read_chapter(out)
    assert 'blurred' not in html
    assert 'noblur' in html


def test_custom_blur_amount_reaches_the_stylesheet(en_epub, fr_epub, tmp_path):
    out = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, out, blur='0.9em')
    with zipfile.ZipFile(out) as zf:
        css = zf.read('OEBPS/css/bilingual.css').decode('utf-8')
    assert 'blur(0.9em)' in css
    # the literal percent signs in the template must survive formatting
    assert '100%;' in css


def test_metadata_merges_both_sides(en_epub, fr_epub, tmp_path):
    out = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, out)
    with zipfile.ZipFile(out) as zf:
        opf = zf.read('OEBPS/content.opf').decode('utf-8')
    assert 'The Invented Town' in opf and 'La Ville Inventée' in opf
    assert '<dc:language>en</dc:language>' in opf
    assert '<dc:language>fr</dc:language>' in opf


def test_cover_is_taken_from_whichever_side_has_one(en_epub, fr_epub, tmp_path):
    out = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, out)   # only the EN fixture has a cover
    with zipfile.ZipFile(out) as zf:
        assert 'OEBPS/images/cover.jpg' in zf.namelist()


def test_title_override(en_epub, fr_epub, tmp_path):
    out = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, out, title='My Custom Title')
    with zipfile.ZipFile(out) as zf:
        assert 'My Custom Title' in zf.read('OEBPS/content.opf').decode('utf-8')


# --------------------------------------------------------------------------- #
# split
# --------------------------------------------------------------------------- #

def test_split_recovers_both_languages(en_epub, fr_epub, tmp_path):
    bi = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, bi)
    results = split_by_lang(bi, str(tmp_path / 'out'))

    assert set(results) == {'en', 'fr'}
    for path in results.values():
        assert os.path.exists(path)


def test_split_keeps_languages_separate(en_epub, fr_epub, tmp_path):
    bi = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, bi)
    results = split_by_lang(bi, str(tmp_path / 'out'))

    en_text = ''.join(read_chapter(results['en'], n) for n in chapter_names(results['en']))
    fr_text = ''.join(read_chapter(results['fr'], n) for n in chapter_names(results['fr']))

    assert 'bright cold day' in en_text
    assert 'journée froide' not in en_text, 'French leaked into the English book'
    assert 'journée froide' in fr_text
    assert 'bright cold day' not in fr_text, 'English leaked into the French book'


def test_split_does_not_leak_ui_chrome_into_content(en_epub, fr_epub, tmp_path):
    """The toolbar button is UI we render, not book text -- it must not end up
    as a paragraph in a split-out book."""
    bi = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, bi)
    results = split_by_lang(bi, str(tmp_path / 'out'))
    en_text = ''.join(read_chapter(results['en'], n) for n in chapter_names(results['en']))
    assert 'Show / Hide translation' not in en_text


def test_split_can_select_a_subset_of_languages(en_epub, fr_epub, tmp_path):
    bi = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, bi)
    results = split_by_lang(bi, str(tmp_path / 'out'), langs=['fr'])
    assert set(results) == {'fr'}


# --------------------------------------------------------------------------- #
# round trip
# --------------------------------------------------------------------------- #

def test_merge_split_merge_round_trip(en_epub, fr_epub, tmp_path):
    bi = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, fr_epub, bi)
    parts = split_by_lang(bi, str(tmp_path / 'parts'))

    again = str(tmp_path / 'again.epub')
    _out, stats = merge_bilingual(parts['en'], parts['fr'], again, blur_side='a')

    assert os.path.exists(again)
    assert sum(row[3] for row in stats) == 10, 'alignment survives the round trip'
    html = read_chapter(again)
    assert 'class="a blurred"' in html


# --------------------------------------------------------------------------- #
# conversion + error handling
# --------------------------------------------------------------------------- #

def test_opencc_conversion_traditional_to_simplified(en_epub, zh_hant_epub, tmp_path):
    pytest.importorskip('opencc')
    out = str(tmp_path / 'bi.epub')
    merge_bilingual(en_epub, zh_hant_epub, out, convert_side='b', cc_config='tw2sp')
    html = read_chapter(out)
    assert '强大' in html or '开始' in html or '信息' in html, 'expected Simplified output'
    assert '網路' not in html, 'Traditional text should have been converted'


def test_missing_file_gives_a_readable_error(fr_epub, tmp_path):
    with pytest.raises(SystemExit) as exc:
        merge_bilingual('/nonexistent/nope.epub', fr_epub, str(tmp_path / 'x.epub'))
    assert 'not found' in str(exc.value).lower()


def test_non_epub_input_gives_a_readable_error(fr_epub, tmp_path):
    junk = tmp_path / 'junk.epub'
    junk.write_bytes(b'this is definitely not a zip file')
    with pytest.raises(SystemExit) as exc:
        merge_bilingual(str(junk), fr_epub, str(tmp_path / 'x.epub'))
    assert 'EPUB' in str(exc.value)
