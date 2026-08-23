"""Original text for the sample books, written for this repository.

Not a real book and not derived from one: this is invented prose, released
under the same Apache-2.0 licence as the code (see LICENSE). It exists so
that `bilingual-epub merge` can be tried immediately, without anyone having
to find and legally obtain two editions of the same real book first.

The two versions are deliberately a genuine translation pair -- same
paragraph count, same order -- because that is the shape the aligner is
designed for. To see how it behaves on a messier pair, delete or duplicate
a paragraph on one side and rebuild.
"""

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
