"""The sample books, and the code that builds them.

This lives in the package rather than in examples/ because the wheel does not
ship examples/ -- the local web UI offers the demo books as real downloads, so
it has to be able to produce them wherever the toolkit was installed from.

The text is original, written for this project: an invented short story, not a
real book, released under the same Apache-2.0 licence as the code. It exists so
`merge` can be tried immediately without first having to find and legally
obtain two editions of the same book.

The two versions are deliberately a clean translation pair -- same paragraph
count, same order -- because that is the shape the aligner is built for. To see
how it behaves on a messier pair, delete or duplicate a paragraph on one side
and rebuild.
"""
import os
import struct
import zipfile
import zlib

TITLE_EN = 'The Lamplighter of Vellmark'
TITLE_FR = 'L’Allumeuse de Réverbères de Vellmark'
AUTHOR_EN = 'A Sample Book'
AUTHOR_FR = 'Un Livre d’Exemple'

CHAPTERS_EN = [
    ('Chapter One: The Last Lamp', [
        'Vellmark had four hundred lamps, and Ida lit every one of them.',
        'She began at the harbour, where the salt had eaten the iron posts '
        'until they flaked like pastry, and she finished at the observatory '
        'on the hill, long after the town had gone to bed.',
        'Nobody had asked her to take the job. The previous lamplighter had '
        'simply stopped coming one autumn, and the dark had crept inward '
        'street by street until Ida borrowed his pole and pushed it back.',
        'It took her three hours a night. She did not consider this a burden, '
        'in the way that people who love their work rarely do.',
    ]),
    ('Chapter Two: The Cartographer', [
        'In November a cartographer arrived to redraw the municipal map, and '
        'he could not make Vellmark fit on his paper.',
        'The trouble was the lamps. He had marked each one, and the marks '
        'formed a shape that no street plan explained: a long spiral, '
        'tightening as it climbed the hill.',
        '"You light them in this order?" he asked her.',
        '"I light them in the order they were built," Ida said. "I did not '
        'choose it. I only walk it."',
        'The cartographer stayed eleven days. He never did finish the map.',
    ]),
    ('Chapter Three: What the Spiral Was For', [
        'The oldest lamp stood outside the observatory door, and it was the '
        'only one Ida had never been able to light.',
        'Its glass was intact and its wick was dry and willing, but the flame '
        'would not hold; it guttered out the moment she withdrew the pole, '
        'every night, for nine years.',
        'On the last evening of the year she tried once more, and this time '
        'the flame caught and stood up straight and burned.',
        'Ida looked back down the hill at the spiral she had walked, four '
        'hundred lights turning slowly in the dark like something patient '
        'finally opening an eye.',
        'She did not know what it was for. She lit it again the next night '
        'anyway, and the night after that.',
    ]),
]

CHAPTERS_FR = [
    ('Chapitre Premier : La Dernière Lanterne', [
        'Vellmark comptait quatre cents réverbères, et Ida les allumait tous.',
        'Elle commençait au port, où le sel avait rongé les poteaux de fer '
        'jusqu’à les faire s’écailler comme de la pâte feuilletée, et elle '
        'finissait à l’observatoire sur la colline, bien après que la ville '
        'se fut endormie.',
        'Personne ne lui avait demandé de prendre ce travail. L’allumeur '
        'précédent avait simplement cessé de venir, un automne, et '
        'l’obscurité avait gagné rue après rue jusqu’à ce qu’Ida emprunte sa '
        'perche et la repousse.',
        'Cela lui prenait trois heures par nuit. Elle n’y voyait pas un '
        'fardeau, comme le font rarement les gens qui aiment leur travail.',
    ]),
    ('Chapitre Deux : Le Cartographe', [
        'En novembre, un cartographe arriva pour redessiner le plan municipal, '
        'et il ne parvint pas à faire tenir Vellmark sur son papier.',
        'Le problème venait des réverbères. Il les avait tous marqués, et les '
        'marques formaient une figure qu’aucun plan de rues n’expliquait : une '
        'longue spirale, se resserrant à mesure qu’elle montait la colline.',
        '« Vous les allumez dans cet ordre ? » lui demanda-t-il.',
        '« Je les allume dans l’ordre où ils ont été construits, dit Ida. Je '
        'ne l’ai pas choisi. Je ne fais que le parcourir. »',
        'Le cartographe resta onze jours. Il ne termina jamais sa carte.',
    ]),
    ('Chapitre Trois : À Quoi Servait la Spirale', [
        'Le plus ancien réverbère se dressait devant la porte de '
        'l’observatoire, et c’était le seul qu’Ida n’avait jamais réussi à '
        'allumer.',
        'Son verre était intact et sa mèche était sèche et consentante, mais '
        'la flamme ne tenait pas ; elle s’éteignait dès qu’Ida retirait la '
        'perche, chaque nuit, pendant neuf ans.',
        'Le dernier soir de l’année, elle essaya encore une fois, et cette '
        'fois la flamme prit, se dressa bien droite, et brûla.',
        'Ida se retourna vers le bas de la colline, vers la spirale qu’elle '
        'avait parcourue, quatre cents lumières tournant lentement dans le '
        'noir comme une chose patiente ouvrant enfin un œil.',
        'Elle ne savait pas à quoi cela servait. Elle l’alluma de nouveau la '
        'nuit suivante, et la nuit d’après.',
    ]),
]


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


def build_samples(dest_dir):
    """Write sample-en.epub and sample-fr.epub into dest_dir.

    Returns {'en': path, 'fr': path}.
    """
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    return {
        'en': build(os.path.join(dest_dir, 'sample-en.epub'), 'en',
                    TITLE_EN, AUTHOR_EN, CHAPTERS_EN, cover_rgb=(28, 42, 66)),
        'fr': build(os.path.join(dest_dir, 'sample-fr.epub'), 'fr',
                    TITLE_FR, AUTHOR_FR, CHAPTERS_FR),
    }


#: First two paragraphs of each side, for the web UI's before/after preview.
#: Taken from the same text the books are built from, so the page shows exactly
#: what the documented demo command produces.
PREVIEW_EN = CHAPTERS_EN[0][1][:2]
PREVIEW_FR = CHAPTERS_FR[0][1][:2]
