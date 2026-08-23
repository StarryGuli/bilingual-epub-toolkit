"""Build the two sample EPUBs shipped in this directory.

    python3 examples/make_sample_books.py

Writes sample-en.epub and sample-fr.epub next to this script. Both are
standards-compliant EPUB 3 files built from the original text in
sample_text.py -- see the note there about why they are invented rather
than borrowed.

The generated files are committed to the repository so the toolkit can be
tried without running this first; re-run it after editing sample_text.py.
"""
import os
import struct
import sys
import zipfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sample_text import (  # noqa: E402
    AUTHOR_EN,
    AUTHOR_FR,
    CHAPTERS_EN,
    CHAPTERS_FR,
    TITLE_EN,
    TITLE_FR,
)

HERE = os.path.dirname(os.path.abspath(__file__))

CONTAINER = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
'''

OPF = '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:sample-vellmark-{lang}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>{lang}</dc:language>
    <dc:rights>Original text, Apache-2.0, written for bilingual-epub-toolkit.</dc:rights>
    <meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>
{covermeta}
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
{items}
  </manifest>
  <spine>
{spine}
  </spine>
</package>
'''

XHTML = '''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="{lang}" xml:lang="{lang}">
<head><meta charset="utf-8"/><title>{heading}</title></head>
<body>
<h1>{heading}</h1>
{paras}
</body>
</html>
'''

NAV = '''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"
      lang="{lang}" xml:lang="{lang}">
<head><meta charset="utf-8"/><title>{title}</title></head>
<body>
<nav epub:type="toc" id="toc"><h1>Contents</h1>
<ol>
{items}
</ol>
</nav>
</body>
</html>
'''


def _esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _png(width, height, rgb):
    """A minimal valid solid-colour PNG, so the cover path has something real
    to carry without pulling in Pillow just to build an example."""
    row = b'\x00' + bytes(rgb) * width
    raw = row * height

    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9))
            + chunk(b'IEND', b''))


def build(path, lang, title, author, chapters, cover_rgb=None):
    items, spine, files = [], [], {}

    if cover_rgb is not None:
        files['images/cover.png'] = _png(600, 900, cover_rgb)
        items.append('    <item id="cover-image" href="images/cover.png" '
                     'media-type="image/png" properties="cover-image"/>')

    nav_items = []
    for i, (heading, paras) in enumerate(chapters, 1):
        cid = 'chap%02d' % i
        href = 'text/%s.xhtml' % cid
        body = '\n'.join('<p>%s</p>' % _esc(p) for p in paras)
        files[href] = XHTML.format(lang=lang, heading=_esc(heading), paras=body).encode('utf-8')
        items.append('    <item id="%s" href="%s" media-type="application/xhtml+xml"/>'
                     % (cid, href))
        spine.append('    <itemref idref="%s"/>' % cid)
        nav_items.append('  <li><a href="%s">%s</a></li>' % (href, _esc(heading)))

    files['nav.xhtml'] = NAV.format(lang=lang, title=_esc(title),
                                    items='\n'.join(nav_items)).encode('utf-8')

    opf = OPF.format(
        lang=lang, title=_esc(title), author=_esc(author),
        covermeta=('    <meta name="cover" content="cover-image"/>'
                   if cover_rgb is not None else ''),
        items='\n'.join(items), spine='\n'.join(spine))

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # mimetype must be the first entry and stored uncompressed
        zi = zipfile.ZipInfo('mimetype')
        zi.compress_type = zipfile.ZIP_STORED
        zf.writestr(zi, 'application/epub+zip')
        zf.writestr('META-INF/container.xml', CONTAINER)
        zf.writestr('OEBPS/content.opf', opf)
        for rel, data in sorted(files.items()):
            zf.writestr('OEBPS/' + rel, data)
    return path


def main():
    en = build(os.path.join(HERE, 'sample-en.epub'), 'en', TITLE_EN, AUTHOR_EN,
               CHAPTERS_EN, cover_rgb=(28, 42, 66))
    fr = build(os.path.join(HERE, 'sample-fr.epub'), 'fr', TITLE_FR, AUTHOR_FR,
               CHAPTERS_FR)
    for p in (en, fr):
        print('wrote %s (%d KB)' % (os.path.relpath(p), os.path.getsize(p) // 1024 or 1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
