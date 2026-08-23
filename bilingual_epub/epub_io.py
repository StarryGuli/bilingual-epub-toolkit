#!/usr/bin/env python3
"""Generic EPUB2/3 reading and writing helpers.

Not tied to any specific book: reads any standards-compliant EPUB by walking
its META-INF/container.xml -> OPF -> manifest/spine, and writes a fresh
EPUB3 from a list of already-rendered XHTML chapter strings.
"""
import os
import shutil
import tempfile
import zipfile

from lxml import etree

XH = '{http://www.w3.org/1999/xhtml}'


def _local(tag):
    if not isinstance(tag, str):
        return None
    return tag.split('}')[-1]


class EpubDoc:
    def __init__(self, root_dir, manifest, spine_ids, metadata, cover_href):
        self.root_dir = root_dir        # dir containing content.opf
        self.manifest = manifest        # id -> {'href','media-type','properties': set}
        self.spine_ids = spine_ids      # ordered manifest ids, per OPF spine
        self.metadata = metadata        # {'title', 'creators': [...], 'languages': [...]}
        self.cover_href = cover_href    # href relative to root_dir, or None

    def spine_doc_paths(self):
        """Absolute paths of the spine's XHTML/HTML content documents, in
        reading order (skips non-(x)html spine items, e.g. any stray NCX)."""
        out = []
        for i in self.spine_ids:
            info = self.manifest.get(i)
            if not info:
                continue
            mt = (info['media-type'] or '').lower()
            if 'html' in mt:
                out.append(os.path.join(self.root_dir, info['href']))
        return out

    def cover_path(self):
        if self.cover_href:
            p = os.path.join(self.root_dir, self.cover_href)
            if os.path.exists(p):
                return p
        return None


def extract_epub(epub_path, dest_dir):
    if not epub_path or not os.path.exists(epub_path):
        raise SystemExit('EPUB not found: %r' % epub_path)
    if os.path.isdir(dest_dir):
        shutil.rmtree(dest_dir)
    os.makedirs(dest_dir)
    try:
        with zipfile.ZipFile(epub_path) as zf:
            zf.extractall(dest_dir)
    except zipfile.BadZipFile as err:
        raise SystemExit('不是合法的 EPUB(不是有效的 zip 文件，可能是下载不完整或带了 DRM): %r'
                         % epub_path) from err
    return dest_dir


def _find_opf_path(extracted_dir):
    container = os.path.join(extracted_dir, 'META-INF', 'container.xml')
    if not os.path.exists(container):
        raise ValueError('不是合法 EPUB：缺 META-INF/container.xml (%s)' % extracted_dir)
    parser = etree.XMLParser(recover=True)
    root = etree.parse(container, parser).getroot()
    for el in root.iter():
        if _local(el.tag) == 'rootfile':
            full_path = el.get('full-path')
            if full_path:
                return os.path.join(extracted_dir, full_path)
    raise ValueError('container.xml 里没有 rootfile')


def load(epub_path, extract_to):
    """Extract epub_path into extract_to/ and parse its OPF generically.
    Returns EpubDoc. Raises ValueError with a clear message on anything that
    doesn't look like a standard EPUB (e.g. DRM-wrapped files usually still
    unzip but the OPF may reference encrypted resources we can't read --
    those will surface as a normal file-not-found further down the pipeline,
    not here)."""
    dest = extract_epub(epub_path, extract_to)
    opf_path = _find_opf_path(dest)
    root_dir = os.path.dirname(opf_path)
    parser = etree.XMLParser(recover=True, huge_tree=True)
    opf = etree.parse(opf_path, parser).getroot()

    manifest = {}
    spine_ids = []
    titles, creators, langs = [], [], []
    cover_id = None

    for ch in opf:
        tag = _local(ch.tag)
        if tag == 'manifest':
            for item in ch:
                if _local(item.tag) != 'item':
                    continue
                iid = item.get('id')
                href = item.get('href')
                if not iid or not href:
                    continue
                props = set((item.get('properties') or '').split())
                manifest[iid] = {
                    'href': os.path.normpath(href).replace('\\', '/'),
                    'media-type': item.get('media-type') or '',
                    'properties': props,
                }
        elif tag == 'spine':
            for itemref in ch:
                if _local(itemref.tag) != 'itemref':
                    continue
                idref = itemref.get('idref')
                if idref:
                    spine_ids.append(idref)
        elif tag == 'metadata':
            for m in ch:
                mt = _local(m.tag)
                if mt == 'title' and (m.text or '').strip():
                    titles.append(m.text.strip())
                elif mt == 'creator' and (m.text or '').strip():
                    creators.append(m.text.strip())
                elif mt == 'language' and (m.text or '').strip():
                    langs.append(m.text.strip())
                elif mt == 'meta' and m.get('name') == 'cover':
                    cover_id = m.get('content')

    if not spine_ids:
        raise ValueError('EPUB 的 OPF 里没有 <spine> 条目，读不出正文顺序: %s' % epub_path)

    cover_href = None
    for info in manifest.values():
        if 'cover-image' in info['properties']:
            cover_href = info['href']
            break
    if not cover_href and cover_id and cover_id in manifest:
        cover_href = manifest[cover_id]['href']

    metadata = {
        'title': titles[0] if titles else os.path.splitext(os.path.basename(epub_path))[0],
        'creators': creators,
        'languages': langs or ['und'],   # 'und' = undetermined (ISO 639-2 code)
    }
    return EpubDoc(root_dir, manifest, spine_ids, metadata, cover_href)


# --------------------------------------------------------------------------- #
# writing
# --------------------------------------------------------------------------- #

def _esc(s):
    import html as _html
    return _html.escape(s or '', quote=True)


# Cover images are copied through byte-for-byte, so the manifest has to
# describe what they actually are -- declaring a PNG as image/jpeg produces an
# EPUB that fails validation and shows no cover in strict readers.
_COVER_TYPES = (
    (b'\x89PNG\r\n\x1a\n', 'png', 'image/png'),
    (b'\xff\xd8\xff', 'jpg', 'image/jpeg'),
    (b'GIF87a', 'gif', 'image/gif'),
    (b'GIF89a', 'gif', 'image/gif'),
    (b'RIFF', 'webp', 'image/webp'),          # refined below
    (b'<?xml', 'svg', 'image/svg+xml'),
    (b'<svg', 'svg', 'image/svg+xml'),
)


def sniff_cover_type(data):
    """(extension, media_type) for raw cover bytes, defaulting to JPEG."""
    for magic, ext, mime in _COVER_TYPES:
        if data.startswith(magic):
            if magic == b'RIFF':
                if data[8:12] != b'WEBP':
                    continue
            return ext, mime
    return 'jpg', 'image/jpeg'


def write_epub(out_path, chapters, css_files, js_files, cover_bytes, meta, uid):
    """Write a fresh, generic EPUB3.

    chapters:  list of (cid, nav_title, xhtml_str, extra_manifest_properties)
    css_files: {'bilingual.css': css_text, ...} written under OEBPS/css/
    js_files:  {'peek.js': js_text, ...} written under OEBPS/js/ (may be {})
    cover_bytes: raw cover image bytes (any common format; the type is
                 sniffed and the manifest labelled to match), or None
    meta: {'title', 'creators': [...], 'languages': [...], 'description',
           'publisher'}
    uid: a stable string used as the book's urn:uuid identifier
    """
    tmp = tempfile.mkdtemp(prefix='epubw_')
    try:
        for d in ('META-INF', 'OEBPS/text', 'OEBPS/css', 'OEBPS/js', 'OEBPS/images'):
            os.makedirs(os.path.join(tmp, d))

        with open(os.path.join(tmp, 'mimetype'), 'w') as f:
            f.write('application/epub+zip')
        with open(os.path.join(tmp, 'META-INF', 'container.xml'), 'w') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                    '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                    'media-type="application/oebps-package+xml"/></rootfiles></container>\n')

        for fn, text in css_files.items():
            with open(os.path.join(tmp, 'OEBPS/css', fn), 'w') as f:
                f.write(text)
        for fn, text in js_files.items():
            with open(os.path.join(tmp, 'OEBPS/js', fn), 'w') as f:
                f.write(text)

        has_cover = bool(cover_bytes)
        cover_ext, cover_mime = sniff_cover_type(cover_bytes or b'')
        cover_name = 'cover.%s' % cover_ext
        if has_cover:
            with open(os.path.join(tmp, 'OEBPS/images', cover_name), 'wb') as f:
                f.write(cover_bytes)
            # NB: concatenation, not %-formatting -- the inline CSS contains
            # literal percent signs (max-width:100%) that would break it.
            cover_page = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
                '<head><meta charset="utf-8"/><title>Cover</title>\n'
                '<style type="text/css">body{margin:0;padding:0;text-align:center;}'
                'img{max-width:100%;max-height:100%;}</style></head>\n'
                '<body epub:type="cover"><div><img src="../images/' + cover_name +
                '" alt="cover"/></div></body></html>\n')
            with open(os.path.join(tmp, 'OEBPS/text/cover.xhtml'), 'w') as f:
                f.write(cover_page)

        spine = ([('cover', 'Cover')] if has_cover else []) + [(c[0], c[1]) for c in chapters]
        for cid, _title, xhtml, _props in chapters:
            with open(os.path.join(tmp, 'OEBPS/text/%s.xhtml' % cid), 'w') as f:
                f.write(xhtml)

        # ---- nav ------------------------------------------------------- #
        nav = ['<?xml version="1.0" encoding="utf-8"?>', '<!DOCTYPE html>',
               '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">',
               '<head><meta charset="utf-8"/><title>Table of Contents</title></head><body>',
               '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>']
        for cid, title in spine:
            nav.append('<li><a href="text/%s.xhtml">%s</a></li>' % (cid, _esc(title)))
        nav.append('</ol></nav></body></html>')
        with open(os.path.join(tmp, 'OEBPS/nav.xhtml'), 'w') as f:
            f.write('\n'.join(nav))

        # ---- ncx (EPUB2 compat) ----------------------------------------- #
        ncx = ['<?xml version="1.0" encoding="utf-8"?>',
               '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">',
               '<head><meta name="dtb:uid" content="urn:uuid:%s"/></head>' % uid,
               '<docTitle><text>%s</text></docTitle><navMap>' % _esc(meta.get('title', ''))]
        for i, (cid, title) in enumerate(spine, 1):
            ncx.append('<navPoint id="np%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
                       '<content src="text/%s.xhtml"/></navPoint>' % (i, i, _esc(title), cid))
        ncx.append('</navMap></ncx>')
        with open(os.path.join(tmp, 'OEBPS/toc.ncx'), 'w') as f:
            f.write('\n'.join(ncx))

        # ---- opf --------------------------------------------------------- #
        opf = ['<?xml version="1.0" encoding="utf-8"?>',
               '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">',
               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">',
               '<dc:identifier id="bookid">urn:uuid:%s</dc:identifier>' % uid,
               '<dc:title>%s</dc:title>' % _esc(meta.get('title', '')),
               ]
        for c in meta.get('creators') or []:
            opf.append('<dc:creator>%s</dc:creator>' % _esc(c))
        for lang in meta.get('languages') or ['und']:
            opf.append('<dc:language>%s</dc:language>' % _esc(lang))
        if meta.get('publisher'):
            opf.append('<dc:publisher>%s</dc:publisher>' % _esc(meta['publisher']))
        if meta.get('description'):
            opf.append('<dc:description>%s</dc:description>' % _esc(meta['description']))
        opf.append('<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>')
        if has_cover:
            opf.append('<meta name="cover" content="cover-image"/>')
        opf.append('</metadata><manifest>')
        opf.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
        opf.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
        for fn in css_files:
            opf.append('<item id="css-%s" href="css/%s" media-type="text/css"/>' % (fn, fn))
        for fn in js_files:
            opf.append('<item id="js-%s" href="js/%s" media-type="text/javascript"/>' % (fn, fn))
        if has_cover:
            opf.append('<item id="cover-image" href="images/%s" media-type="%s" properties="cover-image"/>'
                       % (cover_name, cover_mime))
            opf.append('<item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml"/>')
        for cid, _title, _xhtml, props in chapters:
            propattr = (' properties="%s"' % ' '.join(props)) if props else ''
            opf.append('<item id="%s" href="text/%s.xhtml" media-type="application/xhtml+xml"%s/>'
                       % (cid, cid, propattr))
        opf.append('</manifest><spine toc="ncx">')
        for cid, _title in spine:
            opf.append('<itemref idref="%s"/>' % cid)
        opf.append('</spine></package>')
        with open(os.path.join(tmp, 'OEBPS/content.opf'), 'w') as f:
            f.write('\n'.join(opf))

        # ---- zip --------------------------------------------------------- #
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or '.', exist_ok=True)
        if os.path.exists(out_path):
            os.remove(out_path)
        zf = zipfile.ZipFile(out_path, 'w')
        zi = zipfile.ZipInfo('mimetype')
        zi.compress_type = zipfile.ZIP_STORED
        zf.writestr(zi, 'application/epub+zip')
        for root, dirs, files in os.walk(tmp):
            dirs.sort()
            for fn in sorted(files):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, tmp)
                if rel == 'mimetype':
                    continue
                zf.write(full, rel, zipfile.ZIP_DEFLATED)
        zf.close()
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
