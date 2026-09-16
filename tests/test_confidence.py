"""How much the aligner trusts each pairing.

The obvious version of this -- align forwards, align backwards, compare -- is
a no-op here, and the first test pins that down so nobody spends an afternoon
rediscovering it. The step costs are symmetric and the DP is a global optimum,
so reversing the lattice returns the same path.
"""
from bilingual_epub import align_engine as ae


def blocks(texts, heads=()):
    return [('h1' if i in heads else 'p', t, 'x') for i, t in enumerate(texts)]


# Uniform-length paragraphs: length carries almost no information here.
EN = ['Chapter One',
      'Vellmark had four hundred lamps, and Ida lit every one of them.',
      'She began at the harbour, where the salt had eaten the iron posts.',
      'Nobody had asked her to take the job, and she did not mind that.',
      'It took her three hours a night, every night, for nine long years.',
      'The cartographer stayed eleven days and never finished his map.']
FR = ['Chapitre Premier',
      'Vellmark comptait quatre cents réverbères, et Ida les allumait tous.',
      'Elle commençait au port, où le sel avait rongé les poteaux de fer.',
      'Personne ne lui avait demandé de prendre ce travail, cela lui allait.',
      'Cela lui prenait trois heures par nuit, chaque nuit, pendant neuf ans.',
      'Le cartographe resta onze jours et ne termina jamais sa carte.']

# Lengths that actually vary, which is what a real book looks like.
EN_VARIED = ['Chapter One',
             'It rained.',
             'She began at the harbour, where the salt had eaten the iron posts '
             'until they flaked like pastry, and she finished at the observatory.',
             'Nobody had asked.',
             'It took her three hours a night. She did not consider this a '
             'burden, in the way that people who love their work rarely do.',
             'The town slept.']
FR_VARIED = ['Chapitre Premier',
             'Il pleuvait.',
             'Elle commencait au port, ou le sel avait ronge les poteaux de fer '
             "jusqu'a les faire s'ecailler, et finissait a l'observatoire.",
             "Personne n'avait demande.",
             'Cela lui prenait trois heures par nuit. Elle ny voyait pas un '
             'fardeau, comme le font rarement les gens qui aiment leur travail.',
             'La ville dormait.']


def test_running_it_backwards_finds_nothing():
    """Pinned deliberately: this is why confidence is a margin, not a diff."""
    a, b = blocks(EN, heads={0}), blocks(FR, heads={0})
    fwd = ae.align(a, b)
    rev = ae.align(list(reversed(a)), list(reversed(b)))
    back = [(list(reversed(x)), list(reversed(y))) for x, y in reversed(rev)]
    shape = [(len(x), len(y)) for x, y in fwd]
    assert shape == [(len(x), len(y)) for x, y in back]


def test_a_clean_pair_is_confident_everywhere():
    a, b = blocks(EN, heads={0}), blocks(FR, heads={0})
    beads = ae.align(a, b)
    margins = ae.confidence(a, b, beads)
    assert len(margins) == len(beads)
    assert ae.doubtful(margins) == []


def test_shuffled_paragraphs_are_flagged_when_lengths_differ():
    a = blocks(EN_VARIED, heads={0})
    mixed = list(FR_VARIED)
    mixed[1], mixed[2], mixed[3] = mixed[3], mixed[1], mixed[2]
    b = blocks(mixed, heads={0})
    beads = ae.align(a, b)
    assert ae.doubtful(ae.confidence(a, b, beads)), \
        'reordering paragraphs of unlike length should shake the aligner'


def test_a_confidently_wrong_pairing_is_not_flagged():
    """The limitation, pinned on purpose.

    Every paragraph here is about the same length, so after reordering the
    one-to-one pairing is still comfortably the cheapest: the aligner pairs
    them wrongly and stays sure of itself. The margin measures ambiguity, not
    correctness, and cannot see this. Catching it needs something that reads
    the words.
    """
    a = blocks(EN, heads={0})
    mixed = list(FR)
    mixed[2], mixed[3], mixed[4] = mixed[4], mixed[2], mixed[3]
    b = blocks(mixed, heads={0})
    beads = ae.align(a, b)
    margins = ae.confidence(a, b, beads)
    assert [len(x) for x, _y in beads] == [1] * 6, 'still a tidy 1:1'
    assert ae.doubtful(margins) == [], 'documented blind spot, not a regression'
    assert min(m for m in margins if m != float('inf')) > 500


def test_a_clear_deletion_is_not_flagged():
    """Confidence measures ambiguity, not difference. Dropping a paragraph is
    unambiguous, so it must not be reported as doubtful."""
    a = blocks(EN, heads={0})
    b = blocks(FR[:3] + FR[4:], heads={0})
    beads = ae.align(a, b)
    assert ae.doubtful(ae.confidence(a, b, beads)) == []


def test_threshold_is_relative_to_the_book():
    """A fixed cost threshold flags everything in one book and nothing in the
    next, because cost scales with paragraph length."""
    assert ae.doubtful([1000.0, 1000.0, 1000.0]) == []
    assert ae.doubtful([1000.0, 1000.0, 10.0]) == [2]
    # the same small number among small numbers is not remarkable
    assert ae.doubtful([12.0, 11.0, 10.0]) == []


def test_confidence_survives_degenerate_input():
    assert ae.confidence([], [], []) == []
    a = blocks(['only one'])
    beads = ae.align(a, [])
    assert len(ae.confidence(a, [], beads)) == len(beads)


def test_merge_reports_an_unsure_column(en_epub, fr_epub, tmp_path):
    from bilingual_epub import merge_bilingual
    out = str(tmp_path / 'bi.epub')
    _o, stats = merge_bilingual(en_epub, fr_epub, out)
    assert all(len(row) == 8 for row in stats), 'stats gained an unsure column'
    assert all(isinstance(row[7], int) for row in stats)


# --------------------------------------------------------------------------- #
# one side with far less text than the other
#
# From two live failures on the same pair: a picture-heavy book whose B side
# held seven text documents against the A side's forty. The path runs sideways
# along a row for as far as it needs to, and the band was centred on where it
# entered that row rather than spanning it, so the write of the endpoint at
# (n, m) landed past the end of its array.
# --------------------------------------------------------------------------- #

def lopsided(n_shared=8, n_extra=200):
    shared = [('p', 'Line %d %s' % (i, 'w' * (3 + i % 25)), 'x')
              for i in range(n_shared)]
    extra = [('p', 'Untranslated note %d.' % i, 'x') for i in range(n_extra)]
    return shared, shared + extra


def test_confidence_survives_a_long_run_along_one_row():
    a, b = lopsided()
    beads = ae.align(a, b)
    margins = ae.confidence(a, b, beads)
    assert len(margins) == len(beads)


def test_the_band_contains_the_whole_path():
    """The invariant behind the crash: a margin compares the optimum against
    its alternatives, so the optimum has to be inside the window."""
    a, b = lopsided()
    beads = ae.align(a, b)
    pts = ae._path_points(beads)
    n, m = len(a), len(b)

    band = 40
    first, final = {}, {}
    for i, j in pts:
        first.setdefault(i, j)
        final[i] = j
    enter = leave = 0
    lo, hi = [], []
    for i in range(n + 1):
        enter = first.get(i, leave)
        leave = final.get(i, leave)
        lo.append(max(0, enter - band))
        hi.append(min(m, leave + band))

    for i, j in pts:
        assert lo[i] <= j <= hi[i], 'path point (%d, %d) is outside the band' % (i, j)
    assert hi[n] == m, 'the endpoint must be reachable'
    assert lo[0] == 0, 'the origin must be reachable'


def test_a_lopsided_pair_still_merges(tmp_path):
    """End to end, because the crash reached users through merge()."""
    a, b = lopsided(n_shared=6, n_extra=150)
    beads = ae.align(a, b)
    assert ae.confidence(a, b, beads)
