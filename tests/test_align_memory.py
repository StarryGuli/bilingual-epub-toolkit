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


@pytest.mark.slow
def test_the_corridor_costs_a_few_bytes_a_cell():
    """The one number that matters, stated directly.

    Growth rate is the wrong thing to assert: the corridor widens with the
    book, so its cells go up fourfold when the book doubles -- exactly like
    the full lattice it replaced. The two are not told apart by how fast they
    grow but by what a cell costs. A dict entry runs to about 200 bytes here;
    a back-pointer byte plus three revolving rows of cost is single digits.
    """
    n = 3000
    a, b = synth(n, seed=7), synth(n, seed=8)
    _beads, mb = peak_mb(lambda: ae.align(a, b))

    band = max(64, int(0.08 * n))       # mirrors align()'s opening width
    cells = n * (2 * band + 1)
    per_cell = mb * 1024 * 1024 / cells
    assert per_cell < 20, \
        '%.0f bytes a cell over %.1fM cells; the corridor is holding objects' \
        % (per_cell, cells / 1e6)


def test_a_job_too_large_is_refused_rather_than_fatal():
    """A kernel kill writes no record, sends no reply and leaves no report.

    One did exactly that on the hosted instance, and there is no way to know
    now which book it was. Refusing in advance is the only point at which
    there is still someone to tell.
    """
    from bilingual_epub.errors import UserFacing

    huge = ae.MAX_CORRIDOR_BYTES
    n = int((huge / 0.16) ** 0.5) + 5000     # comfortably past the ceiling
    a = [('p', 'x', 'l')] * n
    b = [('p', 'x', 'l')] * n
    with pytest.raises(UserFacing) as exc:
        ae.align(a, b)
    text = str(exc.value)
    assert str(n) in text, 'the reader is not told how large their book is'
    assert 'pip install' in text, 'no route offered for a book this size'


def test_a_normal_book_is_nowhere_near_the_ceiling():
    """The ceiling must not be reachable by anything ordinary. Monte Cristo,
    at 14512 paragraphs against 4214, needs about 34 MB."""
    n, m = 14512, 4214
    band = max(64, int(0.08 * max(n, m)))
    assert n * (2 * band + 1) < ae.MAX_CORRIDOR_BYTES / 4, \
        'the longest book tested should sit well under the limit'


def test_the_size_is_logged_before_the_expensive_part(capsys):
    """Written to stderr, which the journal keeps, so the next kill is
    attributable to a book rather than a mystery."""
    a, b = synth(200, seed=11), synth(200, seed=12)
    ae.align(a, b)
    err = capsys.readouterr().err
    assert 'align: 200 x 200 blocks' in err, err
