#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Split a bilingual (or any multi-language) EPUB back into independent
monolingual EPUBs, by looking at each block's lang/xml:lang attribute.

Works on EPUBs this tool produced (merge.py tags every paragraph with lang=)
and, in practice, on most real bilingual books that mark language the
standard way. Blocks with no discoverable language end up bucketed under
'und' -- nothing is ever silently dropped.
"""
import os
import re
import shutil
import tempfile
import uuid

from . import align_engine as ae
from . import epub_io

PAGE = '''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><meta charset="utf-8"/><title>%(title)s</title>
<link rel="stylesheet" type="text/css" href="../css/mono.css"/></head>
<body><section class="chap">
%(header)s
%(body)s
</section></body></html>
'''

CSS = '''@charset "utf-8";
html { -webkit-text-size-adjust: 100%; }
body { margin: 0 4%; line-height: 1.6; widows: 2; orphans: 2; }
h1.title { text-align: center; margin: 2.4em 0 1.6em; }
p { margin: 0 0 .9em; text-indent: 0; }
'''


def split_by_lang(epub_path, out_dir, langs=None, workdir=None):
    """Returns {lang_code: out_epub_path}. `langs`: optional explicit list of
    language codes to keep (others get dropped into an 'und' bucket if any
    remain unclaimed); default is "keep every language found"."""
    own_workdir = workdir is None
    workdir = workdir or tempfile.mkdtemp(prefix='epubsplit_')
    try:
        doc = epub_io.load(epub_path, os.path.join(workdir, 'src'))
        book_lang = (doc.metadata['languages'] or ['und'])[0]

        blocks = []
        for p in doc.spine_doc_paths():
            blocks += ae.parse_blocks(p, lang=book_lang)
        if not blocks:
            raise SystemExit('提取不到任何正文段落，检查文件是否有效/是否加了 DRM: %s' % epub_path)

        found = list(dict.fromkeys(lang or 'und' for _t, _f, lang in blocks))
        keep = langs or found
        cover_bytes = None
        cp = doc.cover_path()
        if cp:
            with open(cp, 'rb') as f:
                cover_bytes = f.read()

        os.makedirs(out_dir, exist_ok=True)
        base = re.sub(r'[^\w.-]+', '_', os.path.splitext(os.path.basename(epub_path))[0])
        results = {}
        for lang in keep:
            lang_blocks = [(t, f, l) for t, f, l in blocks if (l or 'und') == lang]
            if not lang_blocks:
                continue
            level = ae.pick_level_single(lang_blocks)
            raw_chapters = ae.split_single(lang_blocks, level)

            chapters = []
            for idx, (title, ch_blocks) in enumerate(raw_chapters, 1):
                cid = 'ch%03d' % idx
                body = []
                # ch_blocks already includes the heading block that gave us
                # `title` (used below only for the <title>/nav label) -- don't
                # also render it as a separate <h1>, or it shows up twice.
                for tag, frag, _l in ch_blocks:
                    t = 'h2' if tag.startswith('h') else 'p'
                    body.append('<%s lang="%s">%s</%s>' % (t, lang, frag, t))
                xhtml = PAGE % {'title': re.sub(r'<[^>]+>', '', title or ('Chapter %d' % idx)),
                                'header': '', 'body': '\n'.join(body)}
                nav_title = re.sub(r'<[^>]+>', '', title or ('Chapter %d' % idx))
                chapters.append((cid, nav_title, xhtml, set()))

            out_path = os.path.join(out_dir, '%s.%s.epub' % (base, lang))
            meta = {
                'title': '%s (%s)' % (doc.metadata['title'], lang),
                'creators': doc.metadata['creators'],
                'languages': [lang],
                'description': 'Split out of the %s language layer of a bilingual edition.' % lang,
            }
            epub_io.write_epub(out_path, chapters, {'mono.css': CSS}, {}, cover_bytes, meta,
                               uuid.uuid5(uuid.NAMESPACE_URL, os.path.abspath(out_path)).hex)
            results[lang] = out_path
        return results
    finally:
        if own_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
