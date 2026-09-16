#!/usr/bin/env python3
"""Book-agnostic block extraction, Gale-Church paragraph alignment, and
heading-based chapter splitting. None of this file knows what book it's
looking at -- that's the whole point."""
import html as _html
import math
import re
import sys
from array import array

from lxml import etree

from .errors import UserFacing

XH = '{http://www.w3.org/1999/xhtml}'

BLOCKS = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote'}
CONTAINERS = {'div', 'body', 'section', 'ol', 'ul', 'aside', 'figure', 'nav',
              'article', 'header', 'footer', 'main'}
INLINE_KEEP = {'i', 'em', 'b', 'strong', 'sup', 'sub', 'u', 'small', 'cite'}


def _local(tag):
    if not isinstance(tag, str):
        return None
    return tag.split('}')[-1].lower()


def _esc(s):
    return _html.escape(s, quote=False)


def _inner(el):
    out = []
    if el.text:
        out.append(_esc(el.text))
    for ch in el:
        t = _local(ch.tag)
        if t is None:
            if ch.tail:
                out.append(_esc(ch.tail))
            continue
        if t == 'br':
            out.append('<br/>')
        elif t in INLINE_KEEP:
            body = _inner(ch)
            out.append('<%s>%s</%s>' % (t, body, t) if body.strip() else body)
        else:
            out.append(_inner(ch))
        if ch.tail:
            out.append(_esc(ch.tail))
    return ''.join(out)


def _plain(frag):
    return re.sub(r'<[^>]+>', '', frag)


def parse_blocks(path, lang=None):
    """Return [(tag, inner_html, lang)] in document order. lang is whatever
    the caller says this whole document's language is (a book-level default);
    per-element lang/xml:lang attributes override it when present, so mixed-
    language source documents still come out tagged correctly for split.py."""
    parser = etree.XMLParser(recover=True, resolve_entities=False, huge_tree=True)
    root = etree.parse(path, parser).getroot()
    body = root.find(XH + 'body')
    if body is None:
        body = root.find('body')
    if body is None:
        return []
    blocks = []

    def elem_lang(el, inherited):
        for attr in ('{http://www.w3.org/XML/1998/namespace}lang', 'lang'):
            v = el.get(attr)
            if v:
                return v
        return inherited

    def walk(el, cur_lang):
        for ch in el:
            t = _local(ch.tag)
            if t is None:
                continue
            if ch.get('data-nocontent') == '1':
                continue   # UI chrome (toolbar/header) we render ourselves -- never book content
            ch_lang = elem_lang(ch, cur_lang)
            if t == 'blockquote':
                if any(_local(g.tag) in BLOCKS for g in ch):
                    walk(ch, ch_lang)
                else:
                    _emit('p', ch, ch_lang)
            elif t in BLOCKS:
                _emit(t, ch, ch_lang)
            elif t in CONTAINERS:
                walk(ch, ch_lang)

    def _emit(tag, el, el_lang):
        frag = _inner(el).strip()
        txt = _plain(frag).replace('　', ' ').strip()
        if not txt:
            return
        blocks.append((tag, frag, el_lang))

    walk(body, elem_lang(body, lang))
    return blocks


# --------------------------------------------------------------------------- #
# Gale-Church alignment (length-based dynamic programming)
# --------------------------------------------------------------------------- #

def _norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


PRIOR = {(1, 1): 0.89, (1, 0): 0.0099, (0, 1): 0.0099,
         (2, 1): 0.089, (1, 2): 0.089, (2, 2): 0.011}
PRIOR_COST = {k: -100.0 * math.log(v) for k, v in PRIOR.items()}

HEAD_BONUS = 900.0
HEAD_PENALTY = 900.0


def _len_cost(x, y, c, s2=6.8):
    mean = y * c
    if mean <= 0:
        mean = 1.0
    z = abs((x - mean) / math.sqrt(mean * s2))
    p = 2.0 * (1.0 - _norm_cdf(z))
    return -100.0 * math.log(max(p, 1e-30))


def _align_banded(a_blocks, b_blocks, band):
    """One pass of the DP, restricted to a corridor around the diagonal.

    Returns (beads, touched_edge). The flag says whether the chosen path ever
    ran up against the corridor wall, which is the signal that the corridor was
    too narrow to contain the real answer.
    """
    n, m = len(a_blocks), len(b_blocks)
    a_len, b_len, a_head, b_head, c = _prep(a_blocks, b_blocks)

    # centre the corridor on the diagonal, scaled by the two lengths
    ratio = (m / n) if n else 0.0
    lo, hi = [], []
    for i in range(n + 1):
        mid = int(round(i * ratio))
        lo.append(max(0, mid - band))
        hi.append(min(m, mid + band))
    lo[n] = min(lo[n], m)
    hi[n] = m
    hi[0] = max(hi[0], 0)

    INF = float('inf')
    width = [hi[i] - lo[i] + 1 for i in range(n + 1)]

    # Storage, and why it looks like this. A dict per row costs something like
    # a hundred bytes a cell, which for The Count of Monte Cristo -- 14512
    # paragraphs against 4214, so a corridor of 33.7 million cells -- works out
    # at over 3 GB, and the corridor alone was still enough to get this process
    # OOM-killed on a 300 MB budget.
    #
    # Two things make that fit. Back-pointers are the only part that has to
    # survive the whole sweep, and one byte holds an index into STEPS, so the
    # predecessor is recovered by subtraction rather than stored. Costs are
    # needed no further back than two rows, because no step is taller than
    # that, so three rows revolve and the rest is thrown away. Same corridor,
    # same arithmetic, same answer; 33.7 million cells now cost 34 MB.
    unset = 255
    back = [bytearray(b'\xff' * w) for w in width]
    ring = [None, None, None]
    for k in range(min(3, n + 1)):
        ring[k % 3] = array('d', [INF]) * width[k]
    ring[0][0] = 0.0                       # lo[0] is 0, so offset 0 is column 0

    for i in range(n + 1):
        cur = ring[i % 3]
        loi = lo[i]
        for off in range(width[i]):
            base = cur[off]
            if base == INF:
                continue
            j = loi + off
            for si in range(len(STEPS)):
                di, dj = STEPS[si]
                ni, nj = i + di, j + dj
                if ni > n or nj > m or not (lo[ni] <= nj <= hi[ni]):
                    continue
                v = base + _step_cost(i, j, di, dj, a_len, b_len, a_head, b_head, c)
                row = ring[ni % 3]
                noff = nj - lo[ni]
                if v < row[noff]:
                    row[noff] = v
                    back[ni][noff] = si
        # row i is spent; its slot becomes row i+3
        ring[i % 3] = (array('d', [INF]) * width[i + 3]) if i + 3 <= n else None

    if (n or m) and back[n][m - lo[n]] == unset:
        return None, True

    beads, i, j, touched = [], n, m, False
    while (i, j) != (0, 0):
        if j <= lo[i] or j >= hi[i]:
            # sitting on the wall: the corridor may have cut off a better route
            if not (j == 0 and lo[i] == 0) and not (j == m and hi[i] == m):
                touched = True
        si = back[i][j - lo[i]]
        if si == unset:
            return None, True
        di, dj = STEPS[si]
        pi, pj = i - di, j - dj
        beads.append((a_blocks[pi:i], b_blocks[pj:j]))
        i, j = pi, pj
    beads.reverse()
    return beads, touched


def align(a_blocks, b_blocks):
    """a_blocks/b_blocks: [(tag, html, lang)]. Returns list of (a_slice, b_slice)
    where each slice is a list of blocks from the respective side.

    The DP runs in a corridor around the diagonal rather than over the whole
    n x m lattice. On a real pair -- Around the World in Eighty Days at 1666
    against 2109 paragraphs -- the full matrix cost 420 MB, which is what kept
    getting this process OOM-killed on a small host. The corridor widens and
    the pass repeats whenever the chosen path touches its wall, so a book whose
    two editions really do drift apart still gets the right answer; it just
    pays for the width it needs.
    """
    n, m = len(a_blocks), len(b_blocks)
    if not n or not m:
        return [(list(a_blocks), list(b_blocks))] if (n or m) else []

    band = max(64, int(0.08 * max(n, m)))

    # A breadcrumb, and a ceiling.
    #
    # The corridor holds one byte a cell, so its cost is n * (2 * band + 1)
    # and band grows with the book: The Count of Monte Cristo, at 14512
    # paragraphs against 4214, needs 34 MB, and a pair twice that needs rather
    # more than four times as much. Past some size the host dies, and a job
    # killed by the kernel writes no failure record, leaves no report, and
    # tells its reader nothing -- one did exactly that, and there is no way to
    # know now what book it was.
    #
    # So the size goes to the log before the expensive part rather than after,
    # where a kill cannot erase it, and a job too large to survive is refused
    # while there is still someone to refuse it to.
    sys.stderr.write('align: %d x %d blocks, corridor %.0f MB\n'
                     % (n, m, _corridor(n, band) / 1048576.0))
    sys.stderr.flush()
    if _corridor(n, band) > MAX_CORRIDOR_BYTES:
        raise UserFacing('err.too_big', n, m)

    while True:
        beads, touched = _align_banded(a_blocks, b_blocks, band)
        if beads is not None and not touched:
            return beads
        if band >= m:
            # already the full lattice; whatever came back is the true optimum
            return beads if beads is not None else [(list(a_blocks), list(b_blocks))]

        # Checking the opening width and then doubling past it, which is what
        # this did, is no limit at all: widening runs until band >= m, and the
        # corridor at that point IS the full lattice -- 800 MB for a pair of
        # 20000 -- reached by re-running the whole DP at every width along the
        # way. A job died that way after fourteen minutes, and because the
        # kernel did the killing it left no record of what book it was.
        #
        # So the ceiling applies to the width about to be tried. When the next
        # one will not fit, the widest that does is what the reader gets: an
        # alignment computed in a corridor narrower than the drift really
        # wants, which is worse than the true optimum and far better than no
        # book at all. The pairings it gets wrong are the ones pressed against
        # the wall, and those come back with small margins, so they are
        # already marked for a second look.
        wider = min(band * 2, m)
        if _corridor(n, wider) > MAX_CORRIDOR_BYTES:
            sys.stderr.write('align: corridor capped at %d; the path wanted more room\n' % band)
            sys.stderr.flush()
            return beads if beads is not None else [(list(a_blocks), list(b_blocks))]
        band = wider


# --------------------------------------------------------------------------- #
# how much to trust each pairing
#
# Running the aligner backwards and comparing, which is the obvious version of
# this idea, finds nothing: the step costs are symmetric and the DP is a global
# optimum, so reversing the lattice returns the very same path. Measured on a
# real pair with an extra paragraph spliced into one side -- identical output,
# both directions.
#
# What the two directions are actually good for is a margin. Cost-to-here plus
# cost-from-here gives the best total through any point in the lattice, so for
# each paragraph the chosen pairing can be compared against the best available
# alternative. A wide gap means the aligner had a clear winner; a narrow one
# means it nearly went elsewhere, and that is the region worth a second look --
# by a person, or by an agent that only needs to examine the doubtful parts
# rather than re-reading the whole book.
#
# Both passes run in a band around the optimal path. A full second matrix would
# double the memory of the alignment, which for a long book is already the
# largest thing in the process, and alternatives far from the path are not the
# ones being asked about.
#
# What this cannot do: catch a pairing that is wrong but unambiguous. The
# margin says how sure the *length model* was, and the length model is content
# whenever the numbers line up. Reorder several paragraphs that happen to be
# about the same length and the aligner pairs them confidently and incorrectly,
# with no dip in margin at all -- there is a test pinning exactly that case.
# Finding those needs something that reads the text: a semantic model, or a
# person. This narrows down where they have to look; it does not replace them.
# --------------------------------------------------------------------------- #

def _prep(a_blocks, b_blocks):
    a_len = [len(_plain(b[1])) for b in a_blocks]
    b_len = [len(_plain(b[1])) for b in b_blocks]
    a_head = [b[0].startswith('h') for b in a_blocks]
    b_head = [b[0].startswith('h') for b in b_blocks]
    c = (sum(a_len) or 1) / (sum(b_len) or 1)
    return a_len, b_len, a_head, b_head, c


def _step_cost(i, j, di, dj, a_len, b_len, a_head, b_head, c):
    """Cost of consuming di source blocks against dj target blocks at (i, j)."""
    x = sum(a_len[i:i + di])
    y = sum(b_len[j:j + dj])
    cost = PRIOR_COST[(di, dj)]
    if di and dj:
        cost += _len_cost(x, y, c)
        ah = any(a_head[i:i + di])
        bh = any(b_head[j:j + dj])
        if ah and bh:
            cost -= HEAD_BONUS
        elif ah != bh:
            cost += HEAD_PENALTY
    else:
        cost += 0.55 * (x if di else y * c)
        if (di and any(a_head[i:i + di])) or (dj and any(b_head[j:j + dj])):
            cost += 200.0
    return cost


STEPS = [(1, 1), (1, 0), (0, 1), (2, 1), (1, 2), (2, 2)]

#: What one alignment may spend on its corridor. Chosen against the deploy
#: host's 300 MB: Monte Cristo fits in 34 MB and the whole job peaks at 67, so
#: this leaves room for a book several times longer while still refusing the
#: ones that would take the process down.
MAX_CORRIDOR_BYTES = 160 * 1024 * 1024


def _corridor(n, band):
    #: Bytes the back-pointers occupy at this width -- one per cell.
    return n * (2 * band + 1)


def _path_points(beads):
    """The lattice points the optimal path passes through."""
    pts, i, j = [(0, 0)], 0, 0
    for a_part, b_part in beads:
        i += len(a_part)
        j += len(b_part)
        pts.append((i, j))
    return pts


def confidence(a_blocks, b_blocks, beads, band=40):
    """Margin, in cost units, between each pairing and the next-best option.

    Returns a list the same length as `beads`. A small number means the
    aligner nearly chose differently there.
    """
    n, m = len(a_blocks), len(b_blocks)
    if not beads or not n or not m:
        return [float('inf')] * len(beads)
    a_len, b_len, a_head, b_head, c = _prep(a_blocks, b_blocks)
    pts = _path_points(beads)

    # The band: for each i, the range of j worth considering. It has to
    # contain the whole optimal path, because the margin is measured against
    # it -- an alternative cannot be compared with an optimum that is not
    # there.
    #
    # A row is not a single point. Where one side has far less text than the
    # other -- a picture book against a prose translation -- the path runs
    # sideways along a single row for as far as it needs to, and taking that
    # row's first j as its centre leaves the rest of the run outside. On a
    # real pair that ran 69 columns along the final row, 40 of which were
    # covered, and the write of the endpoint at (n, m) landed past the end of
    # its array: two users, one IndexError, no margins at all.
    #
    # So each row is bracketed by where the path enters and leaves it, and
    # the band is added on either side of that. Rows the path never touches
    # carry the last bracket forward.
    first, final = {}, {}
    for i, j in pts:
        first.setdefault(i, j)
        final[i] = j
    lo, hi = [], []
    enter = leave = 0
    for i in range(n + 1):
        enter = first.get(i, leave)
        leave = final.get(i, leave)
        lo.append(max(0, enter - band))
        hi.append(min(m, leave + band))

    INF = float('inf')
    width = [hi[i] - lo[i] + 1 for i in range(n + 1)]

    # Flat rows rather than dicts, for the reason given in _align_banded: both
    # passes have to survive to the end here, so on a long book the dict
    # version was the largest thing left in the process after the corridor was
    # fixed. Two arrays of n x 81 doubles is 19 MB where the dicts were 240.
    #
    # Both passes walk j in a fixed order so that a same-row step -- (0, 1),
    # skipping a target block -- lands on a cell that is already final. An
    # earlier version relaxed out of a snapshot of the row, which silently
    # capped those chains at one step, inflated the forward costs, and produced
    # margins of minus a hundred thousand: an "alternative" cheaper than the
    # optimum, which is arithmetically impossible and was the tell.
    fwd = [array('d', [INF]) * w for w in width]
    fwd[0][0 - lo[0]] = 0.0
    for i in range(n + 1):
        row, loi = fwd[i], lo[i]
        for off in range(width[i]):
            base = row[off]
            if base == INF:
                continue
            j = loi + off
            for di, dj in STEPS:
                ni, nj = i + di, j + dj
                if ni > n or nj > m or not (lo[ni] <= nj <= hi[ni]):
                    continue
                v = base + _step_cost(i, j, di, dj, a_len, b_len, a_head, b_head, c)
                nrow, noff = fwd[ni], nj - lo[ni]
                if v < nrow[noff]:
                    nrow[noff] = v

    bwd = [array('d', [INF]) * w for w in width]
    bwd[n][m - lo[n]] = 0.0
    for i in range(n, -1, -1):
        row, loi = bwd[i], lo[i]
        for off in range(width[i] - 1, -1, -1):
            j = loi + off
            best = row[off]
            for di, dj in STEPS:
                ni, nj = i + di, j + dj
                if ni > n or nj > m or not (lo[ni] <= nj <= hi[ni]):
                    continue
                rest = bwd[ni][nj - lo[ni]]
                if rest == INF:
                    continue
                v = rest + _step_cost(i, j, di, dj, a_len, b_len, a_head, b_head, c)
                if v < best:
                    best = v
            row[off] = best

    best_total = fwd[n][m - lo[n]]
    out = []
    for k in range(len(beads)):
        i, j = pts[k + 1]
        alt = INF
        frow, brow, loi = fwd[i], bwd[i], lo[i]
        for off in range(width[i]):
            if loi + off == j:
                continue
            f, b = frow[off], brow[off]
            if f != INF and b != INF and f + b < alt:
                alt = f + b
        out.append(INF if alt == INF or best_total == INF else alt - best_total)
    return out


def doubtful(margins, ratio=0.25, floor=8.0):
    """Indices of the pairings the aligner was least sure about.

    The test is relative to the book's own margins, not an absolute number of
    cost units. Cost scales with paragraph length, language pair and how freely
    the translation was written, so a threshold tuned on one book flags
    everything in the next. Measured on one pair: a clean merge sat at a median
    margin of 990 with a minimum of 681, splicing an extra paragraph into one
    side pulled the minimum to 177, and shuffling three paragraphs pulled it to
    60. Against the median those separate cleanly; against a fixed number they
    do not.
    """
    finite = sorted(m for m in margins if m != float('inf'))
    if not finite:
        return []
    median = finite[len(finite) // 2]
    cutoff = max(median * ratio, floor)
    return [k for k, mgn in enumerate(margins) if mgn < cutoff]


# --------------------------------------------------------------------------- #
# heading-based chapter splitting -- replaces any book-specific chapter table
# --------------------------------------------------------------------------- #

def _heading_level(tag):
    if tag and len(tag) == 2 and tag[0] == 'h' and tag[1].isdigit():
        return int(tag[1])
    return None


def pick_chapter_level(beads):
    """Find the heading level to cut chapters on: the numerically smallest
    (= most major) heading level that appears more than once across the
    whole book. Returns None if there are no headings at all (caller then
    emits the whole book as one chapter -- always safe, never crashes)."""
    counts = {}
    for a_bs, b_bs in beads:
        for side in (a_bs, b_bs):
            for tag, _frag, _lang in side:
                lvl = _heading_level(tag)
                if lvl is not None:
                    counts[lvl] = counts.get(lvl, 0) + 1
    repeated = sorted(lvl for lvl, n in counts.items() if n > 1)
    if repeated:
        return repeated[0]
    return min(counts) if counts else None


def split_into_chapters(beads, level):
    """Cut `beads` into a list of (title_a, title_b, bead_slice) chapters at
    every bead containing a heading of `level` on either side. Content before
    the first such heading becomes its own leading chapter (title=None,None)
    if non-empty -- so front matter is never silently dropped."""
    if level is None:
        return [(None, None, beads)] if beads else []

    chapters = []
    cur = []
    cur_title_a = cur_title_b = None
    started = False

    def flush():
        if cur:
            chapters.append((cur_title_a, cur_title_b, list(cur)))

    for a_bs, b_bs in beads:
        is_cut = any(_heading_level(t) == level for t, _f, _l in a_bs) or \
                 any(_heading_level(t) == level for t, _f, _l in b_bs)
        if is_cut and started:
            flush()
            cur = []
            cur_title_a = cur_title_b = None
        if is_cut or not started:
            started = True
        if is_cut:
            ta = next((f for t, f, _l in a_bs if _heading_level(t) == level), None)
            tb = next((f for t, f, _l in b_bs if _heading_level(t) == level), None)
            cur_title_a, cur_title_b = ta, tb
        cur.append((a_bs, b_bs))
    flush()
    return chapters


def pick_level_single(blocks):
    """Same idea as pick_chapter_level but for one flat block list (used by
    split.py, which only ever has one side)."""
    counts = {}
    for tag, _frag, _lang in blocks:
        lvl = _heading_level(tag)
        if lvl is not None:
            counts[lvl] = counts.get(lvl, 0) + 1
    repeated = sorted(lvl for lvl, n in counts.items() if n > 1)
    if repeated:
        return repeated[0]
    return min(counts) if counts else None


def split_single(blocks, level):
    """Cut a flat [(tag, frag, lang)] list into [(title, [blocks])] chapters
    at every block whose heading level == level."""
    if level is None:
        return [(None, blocks)] if blocks else []
    chapters, cur, cur_title, started = [], [], None, False

    def flush():
        if cur:
            chapters.append((cur_title, list(cur)))

    for tag, frag, lang in blocks:
        is_cut = _heading_level(tag) == level
        if is_cut and started:
            flush()
            cur = []
        if is_cut or not started:
            started = True
        if is_cut:
            cur_title = frag
        cur.append((tag, frag, lang))
    flush()
    return chapters
