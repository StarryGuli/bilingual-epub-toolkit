#!/usr/bin/env python3
"""Book-agnostic block extraction, Gale-Church paragraph alignment, and
heading-based chapter splitting. None of this file knows what book it's
looking at -- that's the whole point."""
import html as _html
import math
import re

from lxml import etree

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
    D = [dict() for _ in range(n + 1)]
    B = [dict() for _ in range(n + 1)]
    D[0][0] = 0.0
    for i in range(n + 1):
        Di = D[i]
        for j in range(lo[i], hi[i] + 1):
            base = Di.get(j)
            if base is None:
                continue
            for di, dj in STEPS:
                ni, nj = i + di, j + dj
                if ni > n or nj > m or not (lo[ni] <= nj <= hi[ni]):
                    continue
                v = base + _step_cost(i, j, di, dj, a_len, b_len, a_head, b_head, c)
                if v < D[ni].get(nj, INF):
                    D[ni][nj] = v
                    B[ni][nj] = (i, j)

    if m not in D[n]:
        return None, True

    beads, i, j, touched = [], n, m, False
    while (i, j) != (0, 0):
        if j <= lo[i] or j >= hi[i]:
            # sitting on the wall: the corridor may have cut off a better route
            if not (j == 0 and lo[i] == 0) and not (j == m and hi[i] == m):
                touched = True
        pi, pj = B[i][j]
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
    while True:
        beads, touched = _align_banded(a_blocks, b_blocks, band)
        if beads is not None and not touched:
            return beads
        if band >= m:
            # already the full lattice; whatever came back is the true optimum
            return beads if beads is not None else [(list(a_blocks), list(b_blocks))]
        band = min(band * 2, m)


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

    # the band: for each i, the range of j worth considering
    on_path = {}
    for i, j in pts:
        on_path.setdefault(i, j)
    last = 0
    centre = []
    for i in range(n + 1):
        last = on_path.get(i, last)
        centre.append(last)
    lo = [max(0, centre[i] - band) for i in range(n + 1)]
    hi = [min(m, centre[i] + band) for i in range(n + 1)]

    INF = float('inf')

    # Both passes walk j in a fixed order so that a same-row step -- (0, 1),
    # skipping a target block -- lands on a cell that is already final. An
    # earlier version relaxed out of a snapshot of the row, which silently
    # capped those chains at one step, inflated the forward costs, and produced
    # margins of minus a hundred thousand: an "alternative" cheaper than the
    # optimum, which is arithmetically impossible and was the tell.
    fwd = [dict() for _ in range(n + 1)]
    fwd[0][0] = 0.0
    for i in range(n + 1):
        for j in range(lo[i], hi[i] + 1):
            base = fwd[i].get(j)
            if base is None:
                continue
            for di, dj in STEPS:
                ni, nj = i + di, j + dj
                if ni > n or nj > m or not (lo[ni] <= nj <= hi[ni]):
                    continue
                v = base + _step_cost(i, j, di, dj, a_len, b_len, a_head, b_head, c)
                if v < fwd[ni].get(nj, INF):
                    fwd[ni][nj] = v

    bwd = [dict() for _ in range(n + 1)]
    bwd[n][m] = 0.0
    for i in range(n, -1, -1):
        for j in range(hi[i], lo[i] - 1, -1):
            best = bwd[i].get(j, INF)
            for di, dj in STEPS:
                ni, nj = i + di, j + dj
                if ni > n or nj > m:
                    continue
                rest = bwd[ni].get(nj)
                if rest is None:
                    continue
                v = rest + _step_cost(i, j, di, dj, a_len, b_len, a_head, b_head, c)
                if v < best:
                    best = v
            if best < INF:
                bwd[i][j] = best

    best_total = fwd[n].get(m, INF)
    out = []
    for k in range(len(beads)):
        i, j = pts[k + 1]
        alt = INF
        for jj in range(lo[i], hi[i] + 1):
            if jj == j:
                continue
            f = fwd[i].get(jj)
            b = bwd[i].get(jj)
            if f is not None and b is not None and f + b < alt:
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
