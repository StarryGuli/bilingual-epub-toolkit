"""Get the text out of a book, and a translation of it back in.

This is the piece both translation routes share. One route calls a model API
directly; the other hands the exported file to an agent that already has the
user's own quota and takes the finished file back. Neither needs to know how
EPUBs work, and the tool does not need to know how the translating happened.

Why the round trip is structured this way: a translation is only useful to
this toolkit if it comes back with the *same number of blocks in the same
order*. Keep that invariant and the aligner has nothing left to guess -- every
paragraph pairs with its own translation, and merge produces a clean 1:1 book
instead of the 90-odd percent a length model gets on two independent editions.
So the export is numbered, the import checks the numbering, and a mismatch is
an error rather than something to paper over.

Inline markup (<i>, <b>, links) is deliberately dropped from the exported
text. Asking a model to preserve tags inside a sentence it is reordering is a
reliable way to get malformed HTML back; the source side keeps its formatting,
the translated side is plain prose.
"""
import html as _html
import json
import os
import re
import shutil
import tempfile
import uuid

from . import align_engine as ae
from . import epub_io

FORMAT = 'bilingual-epub-text/1'

PAGE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="%(lang)s" xml:lang="%(lang)s">
<head><meta charset="utf-8"/><title>%(title)s</title>
<link rel="stylesheet" type="text/css" href="../css/mono.css"/></head>
<body>
%(body)s
</body></html>
"""

CSS = """body { line-height: 1.7; margin: 0 6%; }
h1, h2, h3 { line-height: 1.3; margin: 1.6em 0 .6em; }
p { margin: .65em 0; text-indent: 0; }
"""


def _plain(frag):
    """Fragment -> readable plain text."""
    if not frag:
        return ''
    txt = re.sub(r'<[^>]+>', '', frag)
    return _html.unescape(txt).replace('　', ' ').strip()


def export_text(epub_path, workdir=None):
    """Read a book and return the translatable payload as a dict.

    The dict is JSON-serialisable and is the unit of exchange for both
    translation routes.
    """
    own = workdir is None
    workdir = workdir or tempfile.mkdtemp(prefix='epubtext_')
    try:
        doc = epub_io.load(epub_path, os.path.join(workdir, 'src'))
        book_lang = (doc.metadata['languages'] or ['und'])[0]
        blocks = []
        for p in doc.spine_doc_paths():
            blocks += ae.parse_blocks(p, lang=book_lang)
        if not blocks:
            raise SystemExit(
                'No body text found -- check the file is a valid, non-DRM EPUB: %s'
                % epub_path)
        return {
            'format': FORMAT,
            'source_file': os.path.basename(epub_path),
            'source_lang': book_lang,
            'title': doc.metadata.get('title') or '',
            'creators': doc.metadata.get('creators') or [],
            'blocks': [{'i': i, 'tag': tag, 'text': _plain(frag)}
                       for i, (tag, frag, _lg) in enumerate(blocks)],
        }
    finally:
        if own:
            shutil.rmtree(workdir, ignore_errors=True)


def write_export(payload, out_path):
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return out_path


def read_export(path):
    with open(path, encoding='utf-8') as f:
        payload = json.load(f)
    if payload.get('format') != FORMAT:
        raise SystemExit('Not a %s file: %s' % (FORMAT, path))
    return payload


def check_translation(payload, texts):
    """Validate a list of translated strings against the exported payload.

    Returns the list unchanged, or raises SystemExit describing exactly what is
    wrong. Silently accepting a short list would shift every later paragraph up
    by one and quietly mispair the whole book from that point on, which is the
    kind of damage nobody notices until they are reading it.
    """
    want = len(payload['blocks'])
    got = len(texts)
    if got != want:
        raise SystemExit(
            'Translation has %d blocks but the book has %d. They must line up '
            'one to one, in the original order. Re-export and translate each '
            'block exactly once, leaving none out and merging none together.'
            % (got, want))
    empty = [i for i, s in enumerate(texts) if not (s or '').strip()]
    if empty:
        show = ', '.join(str(i) for i in empty[:10])
        more = '' if len(empty) <= 10 else ' (and %d more)' % (len(empty) - 10)
        raise SystemExit('These blocks came back empty: %s%s' % (show, more))
    return texts


def build_epub(payload, texts, out_path, lang, title=None):
    """Write a monolingual EPUB from translated text.

    Block order and tags come from the export, so the result is structurally a
    mirror of the source and merges against it cleanly.
    """
    check_translation(payload, texts)
    blocks = [(b['tag'], _html.escape(t, quote=False), lang)
              for b, t in zip(payload['blocks'], texts)]

    level = ae.pick_level_single(blocks)
    raw_chapters = ae.split_single(blocks, level)

    chapters = []
    for idx, (heading, ch_blocks) in enumerate(raw_chapters, 1):
        cid = 'ch%03d' % idx
        body = []
        for tag, frag, _lg in ch_blocks:
            t = 'h2' if tag.startswith('h') else 'p'
            body.append('<%s lang="%s" xml:lang="%s">%s</%s>' % (t, lang, lang, frag, t))
        nav_title = _plain(heading) or ('Chapter %d' % idx)
        xhtml = PAGE % {'lang': lang, 'title': _html.escape(nav_title, quote=False),
                        'body': '\n'.join(body)}
        chapters.append((cid, nav_title, xhtml, set()))

    meta = {
        'title': title or ('%s (%s)' % (payload.get('title') or 'Untitled', lang)),
        'creators': payload.get('creators') or [],
        'languages': [lang],
        'description': 'Machine translation of the %s edition, produced by '
                       'bilingual-epub-toolkit.' % payload.get('source_lang', '?'),
    }
    epub_io.write_epub(out_path, chapters, {'mono.css': CSS}, {}, None, meta,
                       uuid.uuid5(uuid.NAMESPACE_URL, os.path.abspath(out_path)).hex)
    return out_path


def import_text(export_path, translation_path, out_path, lang=None, title=None):
    """Turn an export plus its translation into a monolingual EPUB.

    The translation file may be a JSON list of strings, a JSON object with a
    "blocks" list (either strings, or objects with a "text" key), or a plain
    text file with one block per line. Agents produce all three shapes and
    none of them is wrong.
    """
    payload = read_export(export_path)
    texts, lang_from_file = _read_translation(translation_path)
    return build_epub(payload, texts, out_path, lang or lang_from_file or 'und', title)


def _read_translation(path):
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    # Decide by whether it parses, not by its first character: a line-per-block
    # file whose first line legitimately opens with '[' or '{' is common enough
    # (bracketed speaker names, stage directions) that sniffing on that alone
    # misreads real translations as malformed JSON.
    try:
        data = json.loads(raw)
    except ValueError:
        return [ln.strip() for ln in raw.splitlines() if ln.strip()], None
    if isinstance(data, list):
        return [_one(x) for x in data], None
    if isinstance(data, dict):
        blocks = data.get('blocks')
        if blocks is None:
            raise SystemExit('JSON translation needs a "blocks" list.')
        return [_one(x) for x in blocks], data.get('target_lang') or data.get('lang')
    raise SystemExit('Do not understand a translation file of type %s'
                     % type(data).__name__)


def _one(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ('text', 'translation', 'target'):
            if key in item:
                return item[key]
    raise SystemExit('Do not understand a translation entry of type %s'
                     % type(item).__name__)
