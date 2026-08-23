"""Synthetic EPUB fixtures.

Deliberately generated rather than checked in as real books: this project
processes copyrighted material, and no real book content belongs in the
repository. These fixtures are standards-compliant EPUB3 files (full
container.xml + OPF + spine) built from invented text.
"""
import zipfile

import pytest

CONTAINER = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>'''

OPF = '''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">urn:uuid:test-{lang}</dc:identifier>
<dc:title>{title}</dc:title>
<dc:creator>{author}</dc:creator>
<dc:language>{lang}</dc:language>
{covermeta}
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
{items}
</manifest>
<spine>
{spine}
</spine>
</package>'''

XHTML = '''<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body>
{content}
</body></html>'''


PNG_BYTES = (b'\x89PNG\r\n\x1a\n'
             b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00'
             b'\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xcf\xc0\x00\x00\x03\x01'
             b'\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82')


def build_epub(path, lang, title, author, chapters, has_cover=False,
               cover_fmt='jpg'):
    """chapters: [(heading, [paragraph, ...])]

    cover_fmt picks the cover's real format ('jpg' or 'png') so the writer's
    media-type handling can be exercised for something other than JPEG.
    """
    items, spine, files = [], [], {}
    if has_cover:
        name, mime, blob = {
            'jpg': ('cover.jpg', 'image/jpeg', b'\xff\xd8\xff\xe0fakejpeg'),
            'png': ('cover.png', 'image/png', PNG_BYTES),
        }[cover_fmt]
        items.append('<item id="cover-image" href="images/%s" '
                     'media-type="%s" properties="cover-image"/>' % (name, mime))
        files['images/' + name] = blob
    for i, (heading, paras) in enumerate(chapters, 1):
        cid = 'c%d' % i
        content = '<h1>%s</h1>\n' % heading + '\n'.join('<p>%s</p>' % p for p in paras)
        files['text/%s.xhtml' % cid] = XHTML.format(content=content).encode('utf-8')
        items.append('<item id="%s" href="text/%s.xhtml" '
                     'media-type="application/xhtml+xml"/>' % (cid, cid))
        spine.append('<itemref idref="%s"/>' % cid)
    files['nav.xhtml'] = (
        b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        b'<body><nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops">'
        b'<ol><li><a href="text/c1.xhtml">1</a></li></ol></nav></body></html>')

    opf = OPF.format(lang=lang, title=title, author=author,
                     covermeta='<meta name="cover" content="cover-image"/>' if has_cover else '',
                     items='\n'.join(items), spine='\n'.join(spine))
    with zipfile.ZipFile(path, 'w') as zf:
        zi = zipfile.ZipInfo('mimetype')
        zi.compress_type = zipfile.ZIP_STORED
        zf.writestr(zi, 'application/epub+zip')
        zf.writestr('META-INF/container.xml', CONTAINER)
        zf.writestr('OEBPS/content.opf', opf)
        for rel, data in files.items():
            zf.writestr('OEBPS/%s' % rel, data)
    return str(path)


EN_CHAPTERS = [
    ('Chapter One: The Beginning', [
        'It was a bright cold day in the invented town.',
        'Nobody had ever seen a stranger like this before.',
        'The clock on the square struck an odd number.',
    ]),
    ('Chapter Two: Complications', [
        'Trouble arrived, as it always does, without an invitation.',
        'Three friends argued about what to do next.',
    ]),
    ('Chapter Three: Resolution', [
        'In the end, everyone agreed it had been a strange week.',
        'The town went back to sleep.',
    ]),
]

FR_CHAPTERS = [
    ('Chapitre Un : Le Début', [
        "C'était une journée froide et lumineuse dans la ville inventée.",
        "Personne n'avait jamais vu un étranger comme celui-ci auparavant.",
        "L'horloge sur la place sonna un nombre étrange.",
    ]),
    ('Chapitre Deux : Complications', [
        "Les ennuis sont arrivés, comme toujours, sans invitation.",
        "Trois amis se disputèrent sur la suite à donner.",
    ]),
    ('Chapitre Trois : Résolution', [
        "Finalement, tout le monde convint que ç'avait été une semaine étrange.",
        "La ville se rendormit.",
    ]),
]


@pytest.fixture
def en_epub(tmp_path):
    return build_epub(tmp_path / 'en.epub', 'en', 'The Invented Town',
                      'A. N. Other', EN_CHAPTERS, has_cover=True)


@pytest.fixture
def fr_epub(tmp_path):
    return build_epub(tmp_path / 'fr.epub', 'fr', 'La Ville Inventée',
                      'A. N. Other (trad.)', FR_CHAPTERS, has_cover=False)


@pytest.fixture
def zh_hant_epub(tmp_path):
    """Traditional Chinese, for exercising the opencc conversion path."""
    return build_epub(tmp_path / 'zh.epub', 'zh-Hant', '發明的小鎮', '譯者', [
        ('第一章：開始', ['資訊與網路軟體。', '這是一個測試段落。']),
    ])


@pytest.fixture
def en_epub_png_cover(tmp_path):
    """Same book, but the cover really is a PNG."""
    return build_epub(tmp_path / 'en_png.epub', 'en', 'The Invented Town',
                      'A. N. Other', EN_CHAPTERS, has_cover=True, cover_fmt='png')
