#!/usr/bin/env python3
"""Generic merge: two monolingual (or already-tagged bilingual) EPUBs -> one
bilingual EPUB, tap-to-reveal styled. Works on any standards-compliant book --
chapter boundaries are found automatically from heading tags, not from a
hand-written table for one specific book.
"""
import os
import re
import shutil
import tempfile

from . import align_engine as ae
from . import epub_io

try:
    import opencc
except ImportError:
    opencc = None


class _Identity:
    def convert(self, s):
        return s


PAGE = '''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
<meta charset="utf-8"/>
<title>%(title)s</title>
<link rel="stylesheet" type="text/css" href="../css/bilingual.css"/>
<script type="text/javascript" src="../js/peek.js"></script>
</head>
<body>
<section epub:type="chapter" class="%(chapcls)s">
%(toolbar)s
%(body)s
</section>
</body>
</html>
'''

CSS_TEMPLATE = '''@charset "utf-8";
html { -webkit-text-size-adjust: 100%%; }
body { margin: 0 4%%; line-height: 1.55; widows: 2; orphans: 2; }
.toolbar { display: none; margin: 0 0 2em; text-align: center; }
body.js .toolbar { display: block; }
a.toggle-all { font-size: .78em; text-decoration: none; color: inherit;
  opacity: .55; border: 1px solid currentColor; border-radius: 1em; padding: .18em .9em; }
.pair { margin: 0 0 1.35em; }
.pair.sec { margin-top: 2.2em; }
p.a, p.b, h2.a, h2.b { text-indent: 0; }
p.a { margin: 0 0 .3em; }
p.b { margin: 0; }
h2.a { margin: 0 0 .2em; font-size: 1.12em; font-weight: bold; line-height: 1.3; }
h2.b { margin: 0; font-size: 1.02em; font-weight: bold; }
.b { font-size: .94em; }
a.peek { color: inherit; text-decoration: none; -webkit-tap-highlight-color: rgba(0,0,0,0); }
.chap .blurred { -webkit-filter: blur(%(blur)s); filter: blur(%(blur)s);
  -webkit-transition: -webkit-filter .15s ease-out; transition: filter .15s ease-out; }
.chap .blurred:target, .chap .blurred.revealed,
body.all-revealed .chap .blurred, .chap.noblur .blurred {
  -webkit-filter: none; filter: none; }
@supports not (filter: blur(1px)) {
  .chap .blurred { color: transparent; text-shadow: 0 0 0.45em #808080; }
  .chap .blurred:target, .chap .blurred.revealed,
  body.all-revealed .chap .blurred, .chap.noblur .blurred { color: inherit; text-shadow: none; }
}
'''

JS = '''(function () {
  function ready(fn) {
    if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", fn, false); }
    else { fn(); }
  }
  ready(function () {
    var b = document.body;
    if (!b) { return; }
    b.className = b.className ? b.className + " js" : "js";
    document.addEventListener("click", function (ev) {
      var el = ev.target;
      while (el && el.nodeType === 1) {
        var c = " " + (el.className || "") + " ";
        if (c.indexOf(" toggle-all ") >= 0) {
          ev.preventDefault();
          var bc = " " + b.className + " ";
          b.className = bc.indexOf(" all-revealed ") >= 0
            ? bc.replace(" all-revealed ", " ").replace(/^\\s+|\\s+$/g, "")
            : b.className + " all-revealed";
          return;
        }
        if (c.indexOf(" blurred ") >= 0) {
          ev.preventDefault();
          var ec = " " + el.className + " ";
          el.className = ec.indexOf(" revealed ") >= 0
            ? ec.replace(" revealed ", " ").replace(/^\\s+|\\s+$/g, "")
            : el.className + " revealed";
          return;
        }
        el = el.parentNode;
      }
    }, false);
  });
})();
'''


def _cc(config):
    if not config or config == 'none':
        return _Identity()
    if opencc is None:
        raise SystemExit('--convert 需要 opencc-python-reimplemented，未安装: pip3 install opencc-python-reimplemented')
    return opencc.OpenCC(config)


def _convert_frag(cc, frag):
    return ''.join(part if part.startswith('<') else cc.convert(part)
                   for part in re.split(r'(<[^>]+>)', frag))


def _plain(frag):
    """Strip tags from a fragment.

    Tolerates None: a chapter can legitimately have no heading on either side,
    and the caller falls back to a generated title. This used to raise a
    TypeError deep inside re.sub, which crashed the whole merge on any book
    with an untitled chapter -- the exact case the README says degrades to a
    single chapter.
    """
    return re.sub(r'<[^>]+>', '', frag).strip() if frag else ''


def render_chapter(cid, idx, title_a, title_b, bead_slice, blur_side, blur_em,
                   cc, convert_side, toggle_label, stats):
    out, k = [], 0
    n11 = nxx = n_a_only = n_b_only = a_count = b_count = 0

    # NOTE: we deliberately do NOT render a separate "chapter title" header
    # here -- the heading pair that triggered this chapter cut is still the
    # first bead in bead_slice below and renders inline (as an <h2 class=sec>
    # pair) with correct per-language lang= attributes. An earlier version of
    # this function additionally rendered a plain <p> announcement above that
    # had no lang= attribute at all; besides being a visible duplicate of the
    # same title, it meant split.py (which buckets blocks by lang=) mis-typed
    # or mis-scattered that duplicate text. One rendering, correctly tagged,
    # is both simpler and correct.
    has_blur = False
    for a_bs, b_bs in bead_slice:
        a_count += len(a_bs)
        b_count += len(b_bs)
        if a_bs and b_bs:
            n11 += 1 if (len(a_bs) == 1 and len(b_bs) == 1) else 0
            nxx += 0 if (len(a_bs) == 1 and len(b_bs) == 1) else 1
            cls = 'pair'
        elif a_bs:
            n_a_only += 1
            cls = 'pair only-a'
        else:
            n_b_only += 1
            cls = 'pair only-b'
        is_head = any(t.startswith('h') for t, _f, _l in a_bs) or any(t.startswith('h') for t, _f, _l in b_bs)
        if is_head:
            cls += ' sec'
        out.append('<div class="%s">' % cls)
        for side_name, side_bs in (('a', a_bs), ('b', b_bs)):
            for tag, frag, lang in side_bs:
                t = 'h2' if tag.startswith('h') else 'p'
                body = frag
                if convert_side == side_name:
                    body = _convert_frag(cc, body)
                blur_here = (blur_side == side_name) and bool(a_bs and b_bs)
                cls2 = side_name
                if blur_here:
                    has_blur = True
                    k += 1
                    pid = '%s-p%d' % (cid, k)
                    body = '<a class="peek" href="#%s">%s</a>' % (pid, body)
                    out.append('<%s class="%s blurred" id="%s" lang="%s" xml:lang="%s">%s</%s>'
                               % (t, cls2, pid, lang or '', lang or '', body, t))
                else:
                    out.append('<%s class="%s" lang="%s" xml:lang="%s">%s</%s>'
                               % (t, cls2, lang or '', lang or '', body, t))
        out.append('</div>')

    stats.append((cid, a_count, b_count, n11, nxx, n_a_only, n_b_only))
    return PAGE % {
        'title': (_plain(title_a or title_b) or ('Chapter %d' % idx)),
        'chapcls': 'chap' if has_blur else 'chap noblur',
        'toolbar': ('<p class="toolbar" data-nocontent="1"><a class="toggle-all" href="#">%s</a></p>' % toggle_label) if has_blur else '',
        'body': '\n'.join(out),
    }


def merge_bilingual(a_epub, b_epub, out_path, workdir=None, blur='0.25em',
                    blur_side='b', convert_side=None, cc_config='none',
                    title=None, authors=None, toggle_label='Show / Hide translation'):
    """Merge two EPUBs (any book, any languages) into one tap-to-reveal
    bilingual EPUB. 'a' is the side rendered first/undimmed by default;
    'b' is the side blurred by default (flip with blur_side='a', or pass
    blur_side='none' to render both sides plainly with no tap-to-reveal).

    Returns (out_path, stats) where stats mirrors the old build.py's
    per-chapter (cid, a_blocks, b_blocks, 1:1, n:m, a-only, b-only) rows.
    """
    own_workdir = workdir is None
    workdir = workdir or tempfile.mkdtemp(prefix='epubmerge_')
    try:
        docA = epub_io.load(a_epub, os.path.join(workdir, 'a'))
        docB = epub_io.load(b_epub, os.path.join(workdir, 'b'))
        lang_a = (docA.metadata['languages'] or ['und'])[0]
        lang_b = (docB.metadata['languages'] or ['und'])[0]

        a_blocks, b_blocks = [], []
        for p in docA.spine_doc_paths():
            a_blocks += ae.parse_blocks(p, lang=lang_a)
        for p in docB.spine_doc_paths():
            b_blocks += ae.parse_blocks(p, lang=lang_b)
        if not a_blocks:
            raise SystemExit('A 侧 EPUB 提取不到任何正文段落，检查文件是否有效/是否加了 DRM: %s' % a_epub)
        if not b_blocks:
            raise SystemExit('B 侧 EPUB 提取不到任何正文段落，检查文件是否有效/是否加了 DRM: %s' % b_epub)

        beads = ae.align(a_blocks, b_blocks)
        level = ae.pick_chapter_level(beads)
        raw_chapters = ae.split_into_chapters(beads, level)

        cc = _cc(cc_config)
        stats = []
        chapters = []
        for idx, (title_a, title_b, bead_slice) in enumerate(raw_chapters, 1):
            cid = 'ch%03d' % idx
            xhtml = render_chapter(cid, idx, title_a, title_b, bead_slice,
                                   blur_side, blur, cc, convert_side, toggle_label, stats)
            chapters.append((cid, _plain(title_a or title_b or ('Chapter %d' % idx)), xhtml, {'scripted'}))

        cover_bytes = None
        for doc in (docA, docB):
            cp = doc.cover_path()
            if cp:
                with open(cp, 'rb') as f:
                    cover_bytes = f.read()
                break

        merged_title = title or ' / '.join(t for t in (docA.metadata['title'], docB.metadata['title']) if t)
        merged_authors = authors or list(dict.fromkeys(docA.metadata['creators'] + docB.metadata['creators']))
        meta = {
            'title': merged_title,
            'creators': merged_authors,
            'languages': [lang_a, lang_b],
            'description': 'Bilingual (%s + %s) tap-to-reveal edition, merged automatically.' % (lang_a, lang_b),
        }
        import uuid
        result = epub_io.write_epub(out_path, chapters,
                                    {'bilingual.css': CSS_TEMPLATE % {'blur': blur}},
                                    {'peek.js': JS}, cover_bytes, meta,
                                    uuid.uuid5(uuid.NAMESPACE_URL, os.path.abspath(out_path)).hex)
        return result, stats
    finally:
        if own_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
