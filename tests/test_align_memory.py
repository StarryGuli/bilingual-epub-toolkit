"""What the alignment is allowed to cost.

This file exists because the same class of bug shipped twice. First the DP
ran over the whole n x m lattice; that was fixed by restricting it to a
corridor. Then the corridor itself, held as a dict per row at roughly a
hundred bytes a cell, was still enough to be OOM-killed on a long book --
The Count of Monte Cristo needs 33.7 million cells, which came to over 3 GB.

Both times the tests passed, because correctness tests use small inputs and
small inputs fit anywhere. So the budget is asserted directly.
"""
import tracemalloc

import pytest

from bilingual_epub import align_engine as ae


def synth(n, seed=0):
    """Paragraphs of varying length, deterministic, no book required."""
    out = []
    x = seed or 1
    for i in range(n):
        x = (x * 1103515245 + 12345) % 2147483648
        out.append(('p', 'Sentence %d. %s' % (i, 'word ' * (8 + x % 60)), 'x'))
    return out


def peak_mb(fn):
    tracemalloc.start()
    try:
        result = fn()
        _cur, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, peak / (1024.0 * 1024.0)


@pytest.mark.slow
def test_alignment_memory_stays_within_a_small_host():
    """3000 x 3000 is a fat book; the corridor is 3000 x 481 = 1.4M cells.

    Dicts cost ~100 bytes a cell there, so the version this replaced needed
    about 140 MB for the same work. The ceiling below is generous enough not
    to be flaky and tight enough that a return to per-cell objects fails it.
    """
    a, b = synth(3000, seed=1), synth(3000, seed=2)
    beads, mb = peak_mb(lambda: ae.align(a, b))
    assert beads, 'alignment produced nothing'
    assert mb < 40, 'alignment used %.0f MB; the corridor is meant to be flat' % mb


@pytest.mark.slow
def test_confidence_memory_stays_within_a_small_host():
    """Both directions have to be kept here, so this is the other half of the
    budget -- and on a long book it became the larger half once the corridor
    was fixed."""
    a, b = synth(2000, seed=3), synth(2000, seed=4)
    beads = ae.align(a, b)
    margins, mb = peak_mb(lambda: ae.confidence(a, b, beads))
    assert len(margins) == len(beads)
    assert mb < 20, 'confidence used %.0f MB' % mb


def test_memory_grows_with_the_corridor_not_the_square():
    """Doubling the book must not quadruple the cost.

    The corridor width itself scales with n, so the true growth is not linear;
    what this rules out is the full lattice, where 2x the input is 4x the
    memory. Anything at or under ~3x is corridor-shaped.
    """
    small = synth(700, seed=5), synth(700, seed=6)
    big = synth(1400, seed=5), synth(1400, seed=6)
    _s, mb_small = peak_mb(lambda: ae.align(*small))
    _b, mb_big = peak_mb(lambda: ae.align(*big))
    assert mb_small > 0.05, 'measurement too small to mean anything'
    assert mb_big / mb_small < 3.2, \
        'doubling the book multiplied memory by %.1f' % (mb_big / mb_small)
