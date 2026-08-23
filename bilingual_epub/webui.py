#!/usr/bin/env python3
"""Local web UI for the bilingual EPUB toolkit -- stdlib only, no framework.

Three tools: merge (2 monolingual -> 1 bilingual), split (1 bilingual -> N
monolingual), remerge (1 existing bilingual -> new bilingual, new options).

Files can be dropped straight onto the page. Because a browser never reveals
a real filesystem path, dropped files are uploaded to this local server and
written to a temp directory; the alternative is to type an absolute path,
which avoids the copy and is better for very large books.

    bilingual-epub-web            # then open http://127.0.0.1:8799
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import merge as merge_mod
from . import split as split_mod
from .i18n import get_lang, set_lang, t

HOST, PORT = '127.0.0.1', 8799
MAX_UPLOAD = 200 * 1024 * 1024      # generous; these are books, not videos

# --------------------------------------------------------------------------- #
# Static assets. Kept as plain constants and injected with str.replace() rather
# than %-formatting or .format(): the CSS is full of literal % and { }, both of
# which those two mechanisms would choke on.
# --------------------------------------------------------------------------- #

CSS = r"""
*, *::before, *::after { box-sizing: border-box; }

:root {
  --bg: #fbf9f6;
  --panel: #ffffff;
  --ink: #23201c;
  --ink-soft: #6b635a;
  --line: #e6e0d8;
  --accent: #8a5a2b;
  --accent-soft: #f3e9dd;
  --ok: #2f6b45;
  --ok-soft: #e6f2ea;
  --err: #a33028;
  --err-soft: #fbeae8;
  --radius: 12px;
  --shadow: 0 1px 2px rgba(35,32,28,.05), 0 8px 24px rgba(35,32,28,.06);
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #16151a;
    --panel: #1f1e24;
    --ink: #ece8e3;
    --ink-soft: #a49c92;
    --line: #33313a;
    --accent: #d9a066;
    --accent-soft: #2b2118;
    --ok: #7fc79b;
    --ok-soft: #1b2a20;
    --err: #f0918a;
    --err-soft: #2e1c1a;
    --shadow: 0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35);
  }
}

html { -webkit-text-size-adjust: 100%; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
        "Hiragino Sans GB", "Microsoft Yahei", sans-serif;
}

.wrap { max-width: 860px; margin: 0 auto; padding: 2.5rem 1.25rem 5rem; }

/* ---- masthead ---------------------------------------------------------- */
header { margin-bottom: 1.75rem; }

.topline { display: flex; align-items: flex-start; justify-content: space-between;
           gap: 1rem; flex-wrap: wrap; }
.lang-switch {
  flex: none; margin-top: .35rem; padding: .3rem .7rem;
  border: 1px solid var(--line); border-radius: 999px;
  color: var(--ink-soft); text-decoration: none;
  font-size: .8rem; font-weight: 500;
  transition: border-color .16s ease, color .16s ease;
}
.lang-switch:hover { border-color: var(--accent); color: var(--accent); }

.brand {
  display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap;
  margin: 0 0 .35rem;
  font-size: 1.5rem; font-weight: 600; letter-spacing: -.01em;
}
.brand .mark {
  font-family: Georgia, "Songti SC", serif;
  font-size: 1.75rem; line-height: 1; color: var(--accent);
}
.tagline { margin: 0; color: var(--ink-soft); font-size: .95rem; }

.local-note {
  display: inline-flex; align-items: center; gap: .4rem;
  margin-top: .9rem; padding: .35rem .7rem;
  background: var(--accent-soft); color: var(--accent);
  border-radius: 999px; font-size: .8rem; font-weight: 500;
}
.local-note .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: currentColor; flex: none;
}

/* ---- tabs -------------------------------------------------------------- */
.tabs { display: flex; gap: .25rem; position: relative; margin: 1.75rem 0 0;
        border-bottom: 1px solid var(--line); overflow-x: auto;
        scrollbar-width: none; }
.tabs::-webkit-scrollbar { display: none; }
.tab {
  appearance: none; border: 0; background: none; cursor: pointer;
  padding: .6rem .9rem; margin-bottom: -1px;
  color: var(--ink-soft); font: inherit; font-size: .93rem; font-weight: 500;
  border-bottom: 2px solid transparent; white-space: nowrap;
  transition: color .18s ease, border-color .18s ease;
}
.tab:hover { color: var(--ink); }
.tab[aria-selected="true"] { color: var(--accent); border-bottom-color: var(--accent); }
.tab:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; border-radius: 4px; }

/* ---- panels ------------------------------------------------------------ */
.panel { display: none; animation: rise .28s ease both; }
.panel.on { display: block; }
@keyframes rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

.lead { color: var(--ink-soft); font-size: .93rem; margin: 1.4rem 0 0; }

form { margin-top: 1.4rem; }

.field { margin-bottom: 1.15rem; }
label { display: block; margin-bottom: .4rem; font-size: .88rem; font-weight: 600; }
.hint { display: block; margin-top: .3rem; color: var(--ink-soft);
        font-size: .8rem; font-weight: 400; }

input[type=text], select {
  width: 100%; padding: .6rem .7rem;
  background: var(--panel); color: var(--ink);
  border: 1px solid var(--line); border-radius: 8px;
  font: inherit; font-size: .92rem;
  transition: border-color .16s ease, box-shadow .16s ease;
}
input[type=text]:focus, select:focus {
  outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
select { appearance: none; cursor: pointer;
         background-image: linear-gradient(45deg, transparent 50%, var(--ink-soft) 50%),
                           linear-gradient(135deg, var(--ink-soft) 50%, transparent 50%);
         background-position: right 1rem center, right .75rem center;
         background-size: 5px 5px, 5px 5px; background-repeat: no-repeat;
         padding-right: 2rem; }

.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media (max-width: 620px) { .grid { grid-template-columns: 1fr; } }

/* ---- drop zone --------------------------------------------------------- */
.drop {
  position: relative;
  border: 1.5px dashed var(--line); border-radius: var(--radius);
  background: var(--panel);
  padding: 1.1rem; text-align: center; cursor: pointer;
  transition: border-color .18s ease, background .18s ease, transform .18s ease;
}
.drop:hover { border-color: var(--accent); }
.drop.over { border-color: var(--accent); background: var(--accent-soft);
             transform: scale(1.012); }
.drop.filled { border-style: solid; border-color: var(--accent); text-align: left; }
.drop input[type=file] { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.drop .ico { font-size: 1.3rem; line-height: 1; display: block; margin-bottom: .3rem; }
.drop .main { display: block; font-size: .9rem; font-weight: 500; }
.drop .sub  { display: block; font-size: .78rem; color: var(--ink-soft);
              margin-top: .15rem; }
.drop .clear {
  position: absolute; top: .5rem; right: .5rem; z-index: 2;
  border: 0; background: none; cursor: pointer; color: var(--ink-soft);
  font-size: 1rem; line-height: 1; padding: .2rem .35rem; border-radius: 5px;
}
.drop .clear:hover { background: var(--line); color: var(--ink); }

.or { display: flex; align-items: center; gap: .6rem;
      margin: .55rem 0; color: var(--ink-soft); font-size: .76rem; }
.or::before, .or::after { content: ""; flex: 1; height: 1px; background: var(--line); }

/* ---- live blur preview ------------------------------------------------- */
.preview {
  margin-top: .5rem; padding: .9rem 1rem;
  background: var(--panel); border: 1px solid var(--line);
  border-radius: var(--radius);
}
.preview .cap { font-size: .74rem; color: var(--ink-soft);
                text-transform: uppercase; letter-spacing: .06em; margin-bottom: .5rem; }
.preview p { margin: .2rem 0; font-size: .88rem; }
.preview .a { color: var(--ink); }
.preview .b { color: var(--ink); transition: filter .2s ease, opacity .2s ease; }
.preview.blur-b .b { filter: blur(var(--blur, .25em)); }
.preview.blur-a .a { filter: blur(var(--blur, .25em)); }

/* ---- button ------------------------------------------------------------ */
.go {
  appearance: none; border: 0; cursor: pointer;
  width: 100%; margin-top: .4rem; padding: .75rem 1.5rem;
  background: var(--accent); color: #fff;
  border-radius: 9px; font: inherit; font-size: .95rem; font-weight: 600;
  transition: filter .16s ease, transform .08s ease;
}
.go:hover:not(:disabled) { filter: brightness(1.08); }
.go:active:not(:disabled) { transform: translateY(1px); }
.go:disabled { opacity: .6; cursor: progress; }

.spinner {
  display: none; width: 14px; height: 14px; margin-right: .5rem;
  vertical-align: -2px;
  border: 2px solid rgba(255,255,255,.4); border-top-color: #fff;
  border-radius: 50%; animation: spin .7s linear infinite;
}
.go.busy .spinner { display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ---- result ------------------------------------------------------------ */
.result { margin-top: 1.4rem; animation: rise .3s ease both; }
.result:empty { display: none; }
.card { padding: 1rem 1.1rem; border-radius: var(--radius);
        border: 1px solid var(--line); background: var(--panel); }
.card.good { border-color: var(--ok); background: var(--ok-soft); }
.card.bad  { border-color: var(--err); background: var(--err-soft); }
.card h3 { margin: 0 0 .5rem; font-size: .95rem; }
.card.good h3 { color: var(--ok); }
.card.bad  h3 { color: var(--err); }

table.stats { width: 100%; border-collapse: collapse; margin: .6rem 0;
              font-size: .82rem; font-variant-numeric: tabular-nums; }
table.stats th, table.stats td { padding: .3rem .5rem; text-align: right;
                                 border-bottom: 1px solid var(--line); }
table.stats th:first-child, table.stats td:first-child { text-align: left; }
table.stats th { color: var(--ink-soft); font-weight: 500; }
.scroller { overflow-x: auto; }

pre { margin: .6rem 0 0; padding: .8rem; overflow-x: auto;
      background: var(--bg); border: 1px solid var(--line);
      border-radius: 8px; font-size: .78rem; line-height: 1.5;
      white-space: pre-wrap; word-break: break-word; }

.dl { display: inline-flex; align-items: center; gap: .4rem;
      margin: .6rem .4rem 0 0; padding: .55rem 1.1rem;
      background: var(--ok); color: #fff; border-radius: 8px;
      text-decoration: none; font-size: .88rem; font-weight: 600;
      transition: filter .16s ease; }
.dl:hover { filter: brightness(1.08); }

footer { margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid var(--line);
         color: var(--ink-soft); font-size: .8rem; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important;
                           transition-duration: .01ms !important; }
}
"""

JS = r"""
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

/* ---- tabs ---- */
$$('.tab').forEach(btn => btn.addEventListener('click', () => {
  $$('.tab').forEach(b => b.setAttribute('aria-selected', String(b === btn)));
  $$('.panel').forEach(p => p.classList.toggle('on', p.id === 'panel-' + btn.dataset.tab));
  history.replaceState(null, '', '#' + btn.dataset.tab);
}));
if (location.hash) {
  const t = $('.tab[data-tab="' + location.hash.slice(1) + '"]');
  if (t) t.click();
}

/* ---- drop zones ---- */
function wireDrop(zone) {
  const input = $('input[type=file]', zone);
  const main  = $('.main', zone);
  const sub   = $('.sub', zone);
  const clear = $('.clear', zone);
  const base  = main.textContent;
  const baseSub = sub.textContent;

  const show = f => {
    if (f) {
      zone.classList.add('filled');
      main.textContent = f.name;
      sub.textContent = (f.size / 1048576).toFixed(1) + ' MB \u00b7 ' + L.uploaded;
      clear.hidden = false;
    } else {
      zone.classList.remove('filled');
      main.textContent = base;
      sub.textContent = baseSub;
      clear.hidden = true;
    }
  };

  input.addEventListener('change', () => show(input.files[0]));
  clear.addEventListener('click', e => {
    e.preventDefault(); e.stopPropagation();
    input.value = ''; show(null);
  });

  ['dragenter', 'dragover'].forEach(ev =>
    zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add('over'); }));
  ['dragleave', 'drop'].forEach(ev =>
    zone.addEventListener(ev, e => {
      if (ev === 'dragleave' && zone.contains(e.relatedTarget)) return;
      zone.classList.remove('over');
    }));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (!f) return;
    const dt = new DataTransfer();
    dt.items.add(f);
    input.files = dt.files;
    show(f);
  });
}
$$('.drop').forEach(wireDrop);

/* the whole window is a drop target, so a near-miss doesn't navigate away
   and replace the page with the raw EPUB */
['dragover', 'drop'].forEach(ev =>
  window.addEventListener(ev, e => { if (!e.target.closest('.drop')) e.preventDefault(); }));

/* ---- live blur preview ---- */
function wirePreview(form) {
  const prev = $('.preview', form);
  if (!prev) return;
  const amount = $('input[name=blur]', form);
  const side = $('select[name=blur_side]', form);
  const sync = () => {
    const v = (amount.value || '').trim() || '0.25em';
    prev.style.setProperty('--blur', v);
    prev.classList.toggle('blur-b', side.value === 'b');
    prev.classList.toggle('blur-a', side.value === 'a');
  };
  amount.addEventListener('input', sync);
  side.addEventListener('change', sync);
  sync();
}
$$('form').forEach(wirePreview);

/* ---- submit ---- */
function statsTable(rows) {
  if (!rows || !rows.length) return '';
  const head = [L.chapter, L.a, L.b, '1:1', 'n:m', L.aOnly, L.bOnly];
  const th = head.map(h => '<th>' + h + '</th>').join('');
  const tr = rows.map(r => '<tr>' + r.map(c => '<td>' + c + '</td>').join('') + '</tr>').join('');
  return '<div class="scroller"><table class="stats"><thead><tr>' + th +
         '</tr></thead><tbody>' + tr + '</tbody></table></div>';
}

const esc = s => String(s).replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

$$('form').forEach(form => form.addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('.go', form);
  const out = $('.result', form.closest('.panel'));
  btn.disabled = true; btn.classList.add('busy');
  out.innerHTML = '';

  try {
    const res = await fetch(form.action, { method: 'POST', body: new FormData(form) });
    const data = await res.json();
    if (data.ok) {
      const links = (data.files || []).map(f =>
        '<a class="dl" href="/download?id=' + encodeURIComponent(f.id) + '" download>↓ ' +
        esc(f.name) + '</a>').join('');
      out.innerHTML = '<div class="card good"><h3>✓ ' + esc(data.title) + '</h3>' +
        (data.note ? '<p>' + esc(data.note) + '</p>' : '') +
        statsTable(data.stats) +
        (data.log ? '<pre>' + esc(data.log) + '</pre>' : '') +
        links + '</div>';
    } else {
      out.innerHTML = '<div class="card bad"><h3>' + esc(L.failed) + '</h3><pre>' +
        esc(data.error) + '</pre></div>';
    }
  } catch (err) {
    out.innerHTML = '<div class="card bad"><h3>' + esc(L.reqFailed) + '</h3><pre>' +
      esc(err) + '</pre></div>';
  } finally {
    btn.disabled = false; btn.classList.remove('busy');
    out.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}));
"""

def _drop(name, main, sub):
    return (
        '<div class="drop">'
        '<button type="button" class="clear" hidden aria-label="' + t('web.clear') + '">&times;</button>'
        '<input type="file" name="' + name + '" accept=".epub,application/epub+zip">'
        '<span class="ico">\U0001F4D5</span>'
        '<span class="main">' + main + '</span>'
        '<span class="sub">' + sub + '</span>'
        '</div>')


def _file_field(label, file_name, path_name, placeholder, drop_label=None):
    return (
        '<div class="field"><label>' + label + '</label>'
        + _drop(file_name, drop_label or t('web.drop'), t('web.drop.sub'))
        + '<div class="or">' + t('web.drop.or_path') + '</div>'
        '<input type="text" name="' + path_name + '" placeholder="' + placeholder + '">'
        '</div>')


def _blur_controls():
    return (
        '<div class="grid">'
        '<div class="field"><label>' + t('web.blur.which') + '</label>'
        '<select name="blur_side">'
        '<option value="b" selected>' + t('web.blur.b') + '</option>'
        '<option value="a">' + t('web.blur.a') + '</option>'
        '<option value="none">' + t('web.blur.none') + '</option>'
        '</select></div>'
        '<div class="field"><label>' + t('web.blur.amount') + '</label>'
        '<input type="text" name="blur" value="0.25em">'
        '<span class="hint">' + t('web.blur.hint') + '</span></div>'
        '</div>'
        '<div class="preview blur-b">'
        '<div class="cap">' + t('web.preview') + '</div>'
        '<p class="a">It was a bright cold day in the invented town.</p>'
        '<p class="b">C\u2019\u00e9tait une journ\u00e9e froide et lumineuse dans la ville invent\u00e9e.</p>'
        '</div>')


def _merge_panel():
    return (
        '<div class="panel on" id="panel-merge">'
        '<p class="lead">' + t('web.merge.lead') + '</p>'
        '<form action="/api/merge">'
        '<div class="grid">'
        + _file_field(t('web.side.a'), 'a_file', 'a_path', '/path/to/english.epub')
        + _file_field(t('web.side.b'), 'b_file', 'b_path', '/path/to/other-language.epub')
        + '</div>'
        + _blur_controls() +
        '<div class="grid">'
        '<div class="field"><label>' + t('web.cc.label') + '</label>'
        '<select name="convert_side">'
        '<option value="">' + t('web.cc.none') + '</option>'
        '<option value="a">' + t('web.cc.a') + '</option>'
        '<option value="b">' + t('web.cc.b') + '</option>'
        '</select><span class="hint">' + t('web.cc.hint') + '</span></div>'
        '<div class="field"><label>' + t('web.cc.cfg') + '</label>'
        '<input type="text" name="convert" value="none" placeholder="tw2sp / s2t">'
        '<span class="hint">' + t('web.cc.cfg_hint') + '</span></div>'
        '</div>'
        '<div class="field"><label>' + t('web.title') + '</label>'
        '<input type="text" name="title" placeholder="' + t('web.title.ph') + '"></div>'
        '<button class="go" type="submit"><span class="spinner"></span>'
        + t('web.go.merge') + '</button>'
        '</form><div class="result"></div></div>')


def _split_panel():
    return (
        '<div class="panel" id="panel-split">'
        '<p class="lead">' + t('web.split.lead') + '</p>'
        '<form action="/api/split">'
        + _file_field(t('web.src'), 'in_file', 'in_path',
                      '/path/to/bilingual.epub', t('web.drop.bi'))
        + '<div class="field"><label>' + t('web.langs') + '</label>'
        '<input type="text" name="langs" placeholder="en,fr">'
        '<span class="hint">' + t('web.langs.hint') + '</span></div>'
        '<button class="go" type="submit"><span class="spinner"></span>'
        + t('web.go.split') + '</button>'
        '</form><div class="result"></div></div>')


def _remerge_panel():
    return (
        '<div class="panel" id="panel-remerge">'
        '<p class="lead">' + t('web.remerge.lead') + '</p>'
        '<form action="/api/remerge">'
        + _file_field(t('web.src.bi'), 'in_file', 'in_path',
                      '/path/to/bilingual.epub', t('web.drop.bi'))
        + '<div class="grid">'
        '<div class="field"><label>' + t('web.alang') + '</label>'
        '<input type="text" name="a_lang" placeholder="en">'
        '<span class="hint">' + t('web.alang.hint') + '</span></div>'
        '<div class="field"><label>' + t('web.blang') + '</label>'
        '<input type="text" name="b_lang" placeholder="fr">'
        '<span class="hint">' + t('web.blang.hint') + '</span></div>'
        '</div>'
        + _blur_controls() +
        '<button class="go" type="submit"><span class="spinner"></span>'
        + t('web.go.remerge') + '</button>'
        '</form><div class="result"></div></div>')


PAGE = (
    '<!doctype html><html lang="__HTMLLANG__"><head>'
    '<meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<meta name="color-scheme" content="light dark">'
    '<title>Bilingual EPUB Toolkit</title>'
    '<style>__CSS__</style></head><body><div class="wrap">'
    '<header>'
    '<div class="topline">'
    '<h1 class="brand"><span class="mark">A | \u6587</span> Bilingual EPUB Toolkit</h1>'
    '<a class="lang-switch" href="?lang=__OTHERLANG__">__SWITCH__</a>'
    '</div>'
    '<p class="tagline">__TAGLINE__</p>'
    '<span class="local-note"><span class="dot"></span>__LOCAL__</span>'
    '</header>'
    '<div class="tabs" role="tablist">'
    '<button class="tab" data-tab="merge" role="tab" aria-selected="true">__T_MERGE__</button>'
    '<button class="tab" data-tab="split" role="tab" aria-selected="false">__T_SPLIT__</button>'
    '<button class="tab" data-tab="remerge" role="tab" aria-selected="false">__T_REMERGE__</button>'
    '</div>'
    '__MERGE__' '__SPLIT__' '__REMERGE__'
    '<footer>__FOOTER__</footer>'
    '</div><script>const L=__LABELS__;</script><script>__JS__</script></body></html>')


def render_page():
    """Render the whole page in the currently selected language."""
    lang = get_lang()
    labels = json.dumps({
        'chapter': t('web.res.chapter'), 'a': t('web.res.a'), 'b': t('web.res.b'),
        'aOnly': t('web.res.a_only'), 'bOnly': t('web.res.b_only'),
        'failed': t('web.res.failed'), 'reqFailed': t('web.res.reqfail'),
        'uploaded': t('web.uploaded'),
    }, ensure_ascii=False)
    return (PAGE
            .replace('__CSS__', CSS)
            .replace('__HTMLLANG__', 'zh-CN' if lang == 'zh' else 'en')
            .replace('__OTHERLANG__', 'en' if lang == 'zh' else 'zh')
            .replace('__SWITCH__', t('web.switch'))
            .replace('__TAGLINE__', t('app.tagline'))
            .replace('__LOCAL__', t('app.local_only'))
            .replace('__T_MERGE__', t('web.tab.merge'))
            .replace('__T_SPLIT__', t('web.tab.split'))
            .replace('__T_REMERGE__', t('web.tab.remerge'))
            .replace('__FOOTER__', t('web.footer'))
            .replace('__MERGE__', _merge_panel())
            .replace('__SPLIT__', _split_panel())
            .replace('__REMERGE__', _remerge_panel())
            .replace('__LABELS__', labels)
            .replace('__JS__', JS))


# --------------------------------------------------------------------------- #
# multipart/form-data parsing
#
# The stdlib used to cover this with `cgi.FieldStorage`, but cgi was removed in
# Python 3.13, and this project deliberately has no third-party dependency for
# the UI. The parser below handles exactly what this page sends: a flat form of
# text fields plus optional file parts.
# --------------------------------------------------------------------------- #

_DISPOSITION = re.compile(r'(\w+)="([^"]*)"')


def parse_multipart(body, boundary):
    """-> {field_name: str} for text parts, {field_name: (filename, bytes)} for files."""
    fields, files = {}, {}
    sep = b'--' + boundary
    for chunk in body.split(sep):
        if not chunk or chunk in (b'--\r\n', b'--', b'\r\n'):
            continue
        chunk = chunk[2:] if chunk.startswith(b'\r\n') else chunk
        head, _, data = chunk.partition(b'\r\n\r\n')
        if not _:
            continue
        if data.endswith(b'\r\n'):
            data = data[:-2]
        disp = ''
        for line in head.decode('utf-8', 'replace').split('\r\n'):
            if line.lower().startswith('content-disposition:'):
                disp = line
                break
        attrs = dict(_DISPOSITION.findall(disp))
        name = attrs.get('name')
        if not name:
            continue
        if 'filename' in attrs:
            if attrs['filename'] and data:
                files[name] = (attrs['filename'], data)
        else:
            fields[name] = data.decode('utf-8', 'replace')
    return fields, files


class Handler(BaseHTTPRequestHandler):
    server_version = 'BilingualEpubToolkit'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    # ---- plumbing ------------------------------------------------------- #
    def _send(self, body, status=200, ctype='text/html; charset=utf-8', headers=()):
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload, status=200):
        self._send(json.dumps(payload, ensure_ascii=False),
                   status=status, ctype='application/json; charset=utf-8')

    def _offer(self, path):
        """Register a built file for download and return its handle."""
        token = str(len(self.server.offered) + 1)
        self.server.offered[token] = path
        return {'id': token, 'name': os.path.basename(path)}

    def _source(self, fields, files, file_key, path_key, label):
        """A dropped upload wins over a typed path; one of the two is required."""
        if file_key in files:
            name, blob = files[file_key]
            safe = os.path.basename(name) or 'upload.epub'
            # one directory per upload rather than a name prefix, so the
            # original filename survives into the split/merge output names
            slot = tempfile.mkdtemp(dir=self.server.uploads)
            dest = os.path.join(slot, safe)
            with open(dest, 'wb') as f:
                f.write(blob)
            return dest
        typed = (fields.get(path_key) or '').strip()
        if typed:
            if not os.path.exists(typed):
                raise SystemExit(t('web.no_such', label, typed))
            return typed
        raise SystemExit(t('web.need_file', label))

    def _out_path(self, stem):
        return os.path.join(self.server.outputs, stem)

    # ---- GET ------------------------------------------------------------ #
    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path == '/':
            # ?lang=en|zh switches the page language for the rest of the session
            want = urllib.parse.parse_qs(p.query).get('lang', [''])[0]
            if want in ('en', 'zh'):
                set_lang(want)
            self._send(render_page())
        elif p.path == '/download':
            token = urllib.parse.parse_qs(p.query).get('id', [''])[0]
            path = self.server.offered.get(token)
            if not path or not os.path.exists(path):
                self._send('not found', status=404, ctype='text/plain; charset=utf-8')
                return
            with open(path, 'rb') as f:
                data = f.read()
            self._send(data, ctype='application/epub+zip', headers=[
                ('Content-Disposition',
                 'attachment; filename="%s"' % os.path.basename(path))])
        else:
            self._send('not found', status=404, ctype='text/plain; charset=utf-8')

    # ---- POST ----------------------------------------------------------- #
    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path
        if route not in ('/api/merge', '/api/split', '/api/remerge'):
            self._json({'ok': False, 'error': 'unknown endpoint'}, status=404)
            return

        ctype = self.headers.get('Content-Type', '')
        length = int(self.headers.get('Content-Length', 0) or 0)
        if length > MAX_UPLOAD:
            self._json({'ok': False,
                        'error': t('web.too_big', MAX_UPLOAD // 1048576)}, status=413)
            return
        body = self.rfile.read(length) if length else b''
        if 'multipart/form-data' in ctype and 'boundary=' in ctype:
            boundary = ctype.split('boundary=', 1)[1].strip().strip('"').encode()
            fields, files = parse_multipart(body, boundary)
        else:
            fields = {k: v[0] for k, v in
                      urllib.parse.parse_qs(body.decode('utf-8', 'replace')).items()}
            files = {}

        buf = io.StringIO()
        real_stdout, sys.stdout = sys.stdout, buf
        try:
            payload = getattr(self, '_do_' + route.rsplit('/', 1)[1])(fields, files)
            payload['log'] = buf.getvalue().strip()
            payload['ok'] = True
        except SystemExit as e:
            payload = {'ok': False, 'error': str(e)}
        except Exception:
            payload = {'ok': False, 'error': traceback.format_exc()}
        finally:
            sys.stdout = real_stdout
        self._json(payload)

    # ---- the three operations ------------------------------------------- #
    def _do_merge(self, fields, files):
        a = self._source(fields, files, 'a_file', 'a_path', t('web.side.a'))
        b = self._source(fields, files, 'b_file', 'b_path', t('web.side.b'))
        out = self._out_path('bilingual.epub')
        out, stats = merge_mod.merge_bilingual(
            a_epub=a, b_epub=b, out_path=out,
            blur=(fields.get('blur') or '0.25em').strip() or '0.25em',
            blur_side=fields.get('blur_side', 'b'),
            convert_side=(fields.get('convert_side') or '').strip() or None,
            cc_config=(fields.get('convert') or 'none').strip() or 'none',
            title=(fields.get('title') or '').strip() or None)
        return {'title': t('web.ok.merge'), 'stats': [list(r) for r in stats],
                'files': [self._offer(out)]}

    def _do_split(self, fields, files):
        src = self._source(fields, files, 'in_file', 'in_path', t('web.src'))
        langs = [s.strip() for s in (fields.get('langs') or '').split(',') if s.strip()]
        results = split_mod.split_by_lang(src, self.server.outputs, langs=langs or None)
        return {'title': t('web.ok.split', len(results), ', '.join(sorted(results))),
                'files': [self._offer(p) for p in results.values()]}

    def _do_remerge(self, fields, files):
        src = self._source(fields, files, 'in_file', 'in_path', t('web.src.bi'))
        tmp = tempfile.mkdtemp(prefix='remerge_')
        try:
            parts = split_mod.split_by_lang(src, os.path.join(tmp, 'parts'), workdir=tmp)
            found = sorted(parts)
            a_lang = (fields.get('a_lang') or '').strip() or (found[0] if found else None)
            b_lang = (fields.get('b_lang') or '').strip() or (
                found[1] if len(found) > 1 else None)
            if not a_lang or not b_lang or a_lang not in parts or b_lang not in parts:
                raise SystemExit(t('web.pick_from', ', '.join(found)))
            out = self._out_path('remerged.epub')
            out, stats = merge_mod.merge_bilingual(
                a_epub=parts[a_lang], b_epub=parts[b_lang], out_path=out,
                blur=(fields.get('blur') or '0.25em').strip() or '0.25em',
                blur_side=fields.get('blur_side', 'b'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return {'title': t('web.ok.remerge'),
                'note': t('web.found_langs', ', '.join(found), a_lang, b_lang),
                'stats': [list(r) for r in stats], 'files': [self._offer(out)]}


def main():
    import argparse
    import threading
    import webbrowser

    ap = argparse.ArgumentParser(prog='bilingual-epub-web', description=t('cli.web_desc'))
    ap.add_argument('--port', type=int, default=PORT, help=t('cli.web_port', PORT))
    ap.add_argument('--no-browser', action='store_true', help=t('cli.web_nobrowser'))
    ap.add_argument('--lang', choices=['en', 'zh'], default=None,
                    help='interface language / 界面语言')
    args = ap.parse_args()
    if args.lang:
        set_lang(args.lang)

    # walk forward if the port is taken, so "one is already running" does not
    # surface as a bare Address already in use
    srv, port = None, args.port
    for candidate in range(args.port, args.port + 20):
        try:
            srv = HTTPServer((HOST, candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if srv is None:
        print(t('web.busy_ports', args.port, args.port + 19), file=sys.stderr)
        return 1
    if port != args.port:
        print(t('web.moved_port', args.port, port))

    workdir = tempfile.mkdtemp(prefix='bilingual_web_')
    srv.uploads = os.path.join(workdir, 'uploads')
    srv.outputs = os.path.join(workdir, 'outputs')
    os.makedirs(srv.uploads)
    os.makedirs(srv.outputs)
    srv.offered = {}

    url = 'http://%s:%d' % (HOST, port)
    print('\n  \U0001F4D6  %s' % t('app.name'))
    print('  %s' % url)
    print(t('web.open_hint'))
    print(t('web.stop_hint'))

    if not args.no_browser:
        # wait until the server is really listening before opening a browser,
        # otherwise it can race ahead and hit a connection error
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print(t('web.stopped'))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
