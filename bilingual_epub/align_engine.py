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


def align(a_blocks, b_blocks):
    """a_blocks/b_blocks: [(tag, html, lang)]. Returns list of (a_slice, b_slice)
    where each slice is a list of blocks from the respective side."""
    n, m = len(a_blocks), len(b_blocks)
    a_len = [len(_plain(b[1])) for b in a_blocks]
    b_len = [len(_plain(b[1])) for b in b_blocks]
    a_head = [b[0].startswith('h') for b in a_blocks]
    b_head = [b[0].startswith('h') for b in b_blocks]

    tot_a, tot_b = sum(a_len) or 1, sum(b_len) or 1
    c = tot_a / tot_b

    INF = float('inf')
    D = [[INF] * (m + 1) for _ in range(n + 1)]
    B = [[None] * (m + 1) for _ in range(n + 1)]
    D[0][0] = 0.0

    steps = [(1, 1), (1, 0), (0, 1), (2, 1), (1, 2), (2, 2)]
    for i in range(n + 1):
        Di = D[i]
        for j in range(m + 1):
            if Di[j] == INF:
                continue
            base = Di[j]
            for di, dj in steps:
                ni, nj = i + di, j + dj
                if ni > n or nj > m:
                    continue
                x = sum(a_len[i:ni])
                y = sum(b_len[j:nj])
                cost = PRIOR_COST[(di, dj)]
                if di and dj:
                    cost += _len_cost(x, y, c)
                    ah = any(a_head[i:ni])
                    bh = any(b_head[j:nj])
                    if ah and bh:
                        cost -= HEAD_BONUS
                    elif ah != bh:
                        cost += HEAD_PENALTY
                else:
                    dropped = x if di else y * c
                    cost += 0.55 * dropped
                    if (di and any(a_head[i:ni])) or (dj and any(b_head[j:nj])):
                        cost += 200.0
                if base + cost < D[ni][nj]:
                    D[ni][nj] = base + cost
                    B[ni][nj] = (i, j)

    beads, i, j = [], n, m
    while (i, j) != (0, 0):
        pi, pj = B[i][j]
        beads.append((a_blocks[pi:i], b_blocks[pj:j]))
        i, j = pi, pj
    beads.reverse()
    return beads


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
