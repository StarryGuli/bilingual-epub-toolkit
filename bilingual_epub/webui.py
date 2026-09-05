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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import diagnostics, guard, multipart, samples
from . import merge as merge_mod
from . import split as split_mod
from .i18n import get_lang, set_lang, t

HOST, PORT = '127.0.0.1', 8799
MAX_UPLOAD = 200 * 1024 * 1024      # generous; these are books, not videos
MAX_FORM_BODY = 1 << 20             # urlencoded bodies are never large here

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

.wrap { max-width: 1280px; margin: 0 auto; padding: 2.5rem 1.5rem 5rem; }
@media (max-width: 900px) { .wrap { padding: 2rem 1.15rem 4rem; } }

/* On a wide screen the form takes the left and the preview sits beside it
   instead of leaving half the monitor empty; below 1040px they stack. */
.panel-body { display: grid; grid-template-columns: minmax(0, 1fr); gap: 2rem; }
@media (min-width: 1040px) {
  .panel-body { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
                align-items: start; gap: 2.5rem; }
  .side { position: sticky; top: 1.5rem; }
}

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
.tagline { margin: 0; max-width: 62ch; color: var(--ink-soft); font-size: .95rem; }

.host { font-variant-numeric: tabular-nums; opacity: .75; }

/* ---- on/off switch ----------------------------------------------------- */
.switch-row { margin-bottom: 1rem; }
.switch { display: flex; align-items: flex-start; gap: .65rem;
          margin: 0; cursor: pointer; font-weight: 400; }
.switch input { position: absolute; opacity: 0; width: 0; height: 0; }
.switch .track {
  flex: none; margin-top: .12rem; width: 38px; height: 22px; border-radius: 999px;
  background: var(--line); position: relative;
  transition: background .18s ease;
}
.switch .knob {
  position: absolute; top: 3px; left: 3px; width: 16px; height: 16px;
  border-radius: 50%; background: var(--panel);
  box-shadow: 0 1px 2px rgba(0,0,0,.25);
  transition: transform .18s ease;
}
.switch input:checked + .track { background: var(--accent); }
.switch input:checked + .track .knob { transform: translateX(16px); }
.switch input:focus-visible + .track { box-shadow: 0 0 0 3px var(--accent-soft); }
.switch-text b { display: block; font-size: .88rem; font-weight: 600; }
.switch-text .hint { margin-top: .1rem; }

/* collapsed when tap-to-reveal is off */
.blur-opts { transition: opacity .18s ease; }
.blur-opts[hidden] { display: none; }

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

.lead { max-width: 68ch; color: var(--ink-soft); font-size: .93rem; margin: 1.4rem 0 0; }

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

/* ---- live before/after preview ----------------------------------------- */
.cap { font-size: .74rem; color: var(--ink-soft); font-weight: 600;
       text-transform: uppercase; letter-spacing: .07em; }
.pv-note { margin: .35rem 0 .9rem; color: var(--ink-soft); font-size: .8rem;
           line-height: 1.5; }

.pv-pair { display: grid; grid-template-columns: 1fr 1fr; gap: .7rem; }
@media (max-width: 460px) { .pv-pair { grid-template-columns: 1fr; } }

.book {
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 10px; padding: .7rem .8rem; min-width: 0;
}
.book-h {
  display: flex; align-items: center; gap: .4rem;
  margin-bottom: .5rem; padding-bottom: .45rem;
  border-bottom: 1px solid var(--line);
  font-size: .73rem; font-weight: 600; color: var(--ink-soft);
}
.book-h .tag {
  padding: .05rem .35rem; border-radius: 4px;
  background: var(--accent-soft); color: var(--accent);
  font-size: .66rem; letter-spacing: .04em;
}
.book-n { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.book-dl {
  flex: none; padding: .1rem .45rem; border-radius: 5px;
  background: var(--ok-soft); color: var(--ok);
  text-decoration: none; font-size: .68rem; font-weight: 600;
  transition: filter .16s ease;
}
.book-dl:hover { filter: brightness(.94); }
.book p { margin: .3rem 0; font-size: .8rem; line-height: 1.55; }
.book.out { border-color: var(--accent); }
.book.out p { font-size: .84rem; }

.pv-flow {
  display: flex; align-items: center; gap: .6rem;
  margin: .8rem 0; color: var(--ink-soft); font-size: .76rem; font-weight: 600;
}
.pv-flow::before, .pv-flow::after { content: ""; flex: 1; height: 1px; background: var(--line); }
.pv-flow .op {
  padding: .2rem .6rem; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent);
}

.preview .a { color: var(--ink); }
.preview .b { color: var(--ink); transition: filter .22s ease; }
.preview.blur-b .b, .preview.blur-a .a { filter: blur(var(--blur, .25em)); }
/* the blurred side is clickable here for the same reason it is in the book */
.preview.blur-b .b, .preview.blur-a .a { cursor: pointer; }
.preview .revealed { filter: none !important; }
.pv-tap { margin-top: .6rem; color: var(--ink-soft); font-size: .74rem; text-align: center; }

/* ---- button ------------------------------------------------------------ */
.cf-turnstile { margin: 1rem 0 .2rem; min-height: 1px; }

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

.report-open {
  appearance: none; border: 1px solid var(--line); background: var(--panel);
  color: var(--ink-soft); cursor: pointer; margin-top: .8rem;
  padding: .45rem .9rem; border-radius: 8px; font: inherit; font-size: .82rem;
  transition: border-color .16s ease, color .16s ease;
}
.report-open:hover { border-color: var(--accent); color: var(--accent); }
.report-box {
  margin-top: .9rem; padding: .95rem 1rem;
  background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  animation: rise .24s ease both;
}
.report-box h4 { margin: 0 0 .5rem; font-size: .9rem; }
.report-box p { margin: 0 0 .6rem; font-size: .8rem; line-height: 1.6; color: var(--ink-soft); }
.report-box label.opt {
  display: flex; gap: .5rem; align-items: flex-start; margin: .7rem 0 .3rem;
  font-size: .84rem; font-weight: 600; cursor: pointer;
}
.report-box label.opt input { margin-top: .2rem; flex: none; }
.report-box textarea {
  width: 100%; min-height: 3.4rem; margin-top: .5rem; padding: .5rem .6rem;
  background: var(--bg); color: var(--ink);
  border: 1px solid var(--line); border-radius: 7px; font: inherit; font-size: .84rem;
  resize: vertical;
}
.report-box .acts { display: flex; gap: .5rem; margin-top: .7rem; }
.report-box button {
  appearance: none; cursor: pointer; padding: .5rem 1rem; border-radius: 7px;
  font: inherit; font-size: .84rem; font-weight: 600; border: 1px solid var(--line);
  background: var(--panel); color: var(--ink-soft);
}
.report-box button.send { background: var(--accent); border-color: var(--accent); color: #fff; }
.report-done { margin-top: .8rem; font-size: .84rem; color: var(--ok); font-weight: 600; }

.dl { display: inline-flex; align-items: center; gap: .4rem;
      margin: .6rem .4rem 0 0; padding: .55rem 1.1rem;
      background: var(--ok); color: #fff; border-radius: 8px;
      text-decoration: none; font-size: .88rem; font-weight: 600;
      transition: filter .16s ease; }
.dl:hover { filter: brightness(1.08); }

.agent { margin: 0 0 1rem; padding: .8rem 1rem; border-radius: var(--radius);
         background: var(--accent-soft); color: var(--ink); line-height: 1.6; }
.agent code { font-size: .92em; background: var(--panel); padding: .1rem .3rem;
              border-radius: 4px; }
.agent a { color: var(--accent); font-weight: 600; }

footer { margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid var(--line);
         color: var(--ink-soft); font-size: .8rem; }

/* phone/tablet landscape: the viewport is short, so give the masthead less of it */
@media (max-height: 520px) and (orientation: landscape) {
  .wrap { padding-top: 1.1rem; }
  header { margin-bottom: 1rem; }
  .brand { font-size: 1.25rem; }
  .tagline, .local-note { display: none; }
}

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
  const amount = $('input[name=blur]', form);
  const side = $('select[name=blur_side]', form);
  const on = $('input[name=tap_reveal]', form);
  const opts = $('.blur-opts', form);
  if (!amount || !side) return;

  const sync = () => {
    const enabled = !on || on.checked;
    if (opts) opts.hidden = !enabled;
    if (!prev) return;
    prev.style.setProperty('--blur', (amount.value || '').trim() || '0.25em');
    prev.classList.toggle('blur-b', enabled && side.value === 'b');
    prev.classList.toggle('blur-a', enabled && side.value === 'a');
    if (!enabled) $$('.revealed', prev).forEach(el => el.classList.remove('revealed'));
  };
  amount.addEventListener('input', sync);
  side.addEventListener('change', sync);
  if (on) on.addEventListener('change', sync);
  sync();
}
$$('form').forEach(wirePreview);

/* Click a blurred line to reveal it, the way the generated book works.
   Clicking the blurred side of the preview is the whole point of the effect,
   so the preview has to actually do it and not just look like it would. */
$$('.preview').forEach(pv => pv.addEventListener('click', e => {
  const line = e.target.closest('p.a, p.b');
  if (!line || !pv.contains(line)) return;
  const hidden = (pv.classList.contains('blur-b') && line.classList.contains('b')) ||
                 (pv.classList.contains('blur-a') && line.classList.contains('a'));
  if (!hidden && !line.classList.contains('revealed')) return;
  line.classList.toggle('revealed');
}));

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

/* ---- reporting a failure ---- */
/* The panel spells out what leaves the machine before anything does, and the
   book itself is a separate, unticked choice -- someone should be able to help
   fix a parser bug without handing over what they are reading. */
function reportUI() {
  if (!L.canReport) return '';
  return '<button type="button" class="report-open">' + esc(L.reportBtn) + '</button>';
}

document.addEventListener('click', async e => {
  const open = e.target.closest('.report-open');
  if (open) {
    open.outerHTML =
      '<div class="report-box">' +
        '<h4>' + esc(L.reportHead) + '</h4>' +
        '<p>' + esc(L.reportWhat) + '</p>' +
        '<label class="opt"><input type="checkbox" class="rp-attach">' +
          '<span>' + esc(L.reportAttach) + '</span></label>' +
        '<p>' + esc(L.reportWhy) + '</p>' +
        '<textarea class="rp-note" placeholder="' + esc(L.reportNote) + '"></textarea>' +
        '<div class="acts">' +
          '<button type="button" class="send rp-send">' + esc(L.reportSend) + '</button>' +
          '<button type="button" class="rp-cancel">' + esc(L.reportCancel) + '</button>' +
        '</div>' +
      '</div>';
    return;
  }

  if (e.target.closest('.rp-cancel')) {
    const box = e.target.closest('.report-box');
    box.outerHTML = '<button type="button" class="report-open">' +
                    esc(L.reportBtn) + '</button>';
    return;
  }

  const send = e.target.closest('.rp-send');
  if (!send) return;
  const box = send.closest('.report-box');
  send.disabled = true;
  try {
    const res = await fetch('/api/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        page_token: L.pageToken,
        attach: $('.rp-attach', box).checked,
        note: $('.rp-note', box).value,
      }),
    });
    const data = await res.json();
    if (data.ok) {
      let msg = L.reportOk.replace('%s', data.id);
      if (data.wanted_attach && !data.attached) msg += ' ' + L.reportNoFiles;
      box.outerHTML = '<p class="report-done">✓ ' + esc(msg) + '</p>';
    } else {
      box.outerHTML = '<p class="report-done" style="color:var(--err)">' +
                      esc(data.error) + '</p>';
    }
  } catch (err) {
    send.disabled = false;
  }
});

$$('form').forEach(form => form.addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('.go', form);
  const out = $('.result', form.closest('.panel'));
  btn.disabled = true; btn.classList.add('busy');
  out.innerHTML = '';

  try {
    // Check the size here rather than discovering it after a long mobile
    // upload: the gateway rejects an oversized body mid-transfer, which the
    // browser reports as a failed fetch rather than as "too large".
    const tooBig = [...form.querySelectorAll('input[type=file]')]
      .map(i => i.files[0]).filter(Boolean)
      .find(f => f.size > L.maxUpload * 1048576);
    if (tooBig) {
      out.innerHTML = '<div class="card bad"><h3>' + esc(L.failed) + '</h3><p>' +
        esc(L.tooBigJs.replace('%s', tooBig.name)
                      .replace('%s', (tooBig.size / 1048576).toFixed(1))
                      .replace('%s', L.maxUpload)) + '</p></div>';
      return;
    }

    const res = await fetch(form.action, { method: 'POST', body: new FormData(form) });

    // Never assume the body is JSON. A gateway that refuses the request --
    // 413 for an oversized upload, 502/504 when the backend is slow -- answers
    // with its own HTML page, and parsing that produced the unreadable
    // "invalid HTML" error people were actually seeing.
    const ctype = res.headers.get('content-type') || '';
    if (!ctype.includes('application/json')) {
      let msg;
      if (res.status === 413) msg = L.rejectedJs.replace('%s', res.status);
      else if (res.status === 502 || res.status === 503 || res.status === 504)
        msg = L.gatewayJs.replace('%s', res.status);
      else msg = L.rejectedJs.replace('%s', res.status);
      out.innerHTML = '<div class="card bad"><h3>' + esc(L.failed) + '</h3><p>' +
        esc(msg) + '</p></div>';
      return;
    }

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
        esc(data.error) + '</pre>' + reportUI() + '</div>';
    }
  } catch (err) {
    const dropped = (err instanceof TypeError);   // fetch's network failure
    out.innerHTML = '<div class="card bad"><h3>' + esc(L.reqFailed) + '</h3><p>' +
      esc(dropped ? L.droppedJs : String(err)) + '</p></div>';
  } finally {
    btn.disabled = false; btn.classList.remove('busy');
    // a Turnstile token is single-use: without resetting, a second submit
    // replays a spent one and is rejected
    if (window.turnstile) { try { turnstile.reset(); } catch (e) { /* not rendered */ } }
    out.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}));
"""

class Config:
    """How this server is exposed.

    Local mode is the default and behaves as it always has: bound to loopback,
    one trusted user, a path field that can open anything that user could open
    anyway. Public mode is for putting it on a host other people can reach, and
    tightens every one of those assumptions.
    """

    def __init__(self, public=False, max_upload=None, ttl=1800.0, turnstile=None):
        self.public = public
        # off unless a key pair is configured; see guard.Turnstile
        self.turnstile = turnstile or guard.Turnstile()
        # a public host processes strangers' files on someone else's disk, so
        # the ceiling is much lower than what a local user should be allowed
        self.max_upload = max_upload or (40 * 1024 * 1024 if public
                                         else 200 * 1024 * 1024)
        self.ttl = ttl
        # reading an arbitrary server path is the whole point locally and an
        # arbitrary-file-read hole in public
        self.allow_paths = not public


def build_demo(workdir):
    """Produce the books the preview offers for download.

    The preview used to be typographic mock-up: it showed what the output looks
    like but you could not open it. These are the real thing, built by the same
    code path the buttons on this page use, so every card in the preview is a
    file you can download and read.
    """
    demo_dir = os.path.join(workdir, 'demo')
    os.makedirs(demo_dir)
    quiet, sys.stdout = sys.stdout, io.StringIO()
    try:
        src = samples.build_samples(demo_dir)
        merged = os.path.join(demo_dir, 'bilingual.epub')
        merge_mod.merge_bilingual(a_epub=src['en'], b_epub=src['fr'], out_path=merged)
        parts = split_mod.split_by_lang(merged, os.path.join(demo_dir, 'split'))
        remerged = os.path.join(demo_dir, 'remerged.epub')
        merge_mod.merge_bilingual(a_epub=parts['en'], b_epub=parts['fr'],
                                  out_path=remerged, blur_side='a', blur='0.4em')
    finally:
        sys.stdout = quiet
    offered = {'demo-en': src['en'], 'demo-fr': src['fr'],
               'demo-bi': merged, 'demo-remerged': remerged}
    for lang, path in parts.items():
        offered['demo-split-' + lang] = path
    return offered


def _drop(name, main, sub):
    return (
        '<div class="drop">'
        '<button type="button" class="clear" hidden aria-label="' + t('web.clear') + '">&times;</button>'
        '<input type="file" name="' + name + '" accept=".epub,application/epub+zip">'
        '<span class="ico">\U0001F4D5</span>'
        '<span class="main">' + main + '</span>'
        '<span class="sub">' + sub + '</span>'
        '</div>')


def _file_field(label, file_name, path_name, placeholder, drop_label=None,
                cfg=None):
    tail = ''
    if cfg is None or cfg.allow_paths:
        tail = ('<div class="or">' + t('web.drop.or_path') + '</div>'
                '<input type="text" name="' + path_name + '" placeholder="'
                + placeholder + '">')
    return (
        '<div class="field"><label>' + label + '</label>'
        + _drop(file_name, drop_label or t('web.drop'), t('web.drop.sub'))
        + tail + '</div>')


# Real lines from the sample books in examples/, so the preview shows exactly
# what the documented one-command demo produces.
PV_EN = ['Vellmark had four hundred lamps, and Ida lit every one of them.',
         'Nobody had asked her to take the job.']
PV_FR = ['Vellmark comptait quatre cents r\u00e9verb\u00e8res, et Ida les allumait tous.',
         'Personne ne lui avait demand\u00e9 de prendre ce travail.']


def _book(name, tag, paras, cls='', para_cls='', dl=None):
    body = ''.join('<p class="%s">%s</p>' % (para_cls, p) for p in paras)
    link = ('<a class="book-dl" href="/download?id=' + dl + '" download>'
            + t('web.pv.download') + '</a>') if dl else ''
    return ('<div class="book ' + cls + '"><div class="book-h">'
            '<span class="tag">' + tag + '</span><span class="book-n">' + name
            + '</span>' + link + '</div>' + body + '</div>')


def _flow(op):
    return '<div class="pv-flow"><span class="op">' + op + '</span></div>'


def _blur_controls():
    """Whether to hide a side at all is its own switch.

    It used to be the third entry in a select called "which side to blur",
    so someone who simply wanted plain facing text had to go looking for it
    inside a question that presumes the answer.
    """
    return (
        '<input type="hidden" name="has_switch" value="1">'
        '<div class="field switch-row">'
        '<label class="switch">'
        '<input type="checkbox" name="tap_reveal" value="1" checked>'
        '<span class="track"><span class="knob"></span></span>'
        '<span class="switch-text"><b>' + t('web.tap.enable') + '</b>'
        '<span class="hint">' + t('web.tap.help') + '</span></span>'
        '</label></div>'
        '<div class="grid blur-opts">'
        '<div class="field"><label>' + t('web.blur.which') + '</label>'
        '<select name="blur_side">'
        '<option value="b" selected>' + t('web.blur.b') + '</option>'
        '<option value="a">' + t('web.blur.a') + '</option>'
        '</select></div>'
        '<div class="field"><label>' + t('web.blur.amount') + '</label>'
        '<input type="text" name="blur" value="0.25em">'
        '<span class="hint">' + t('web.blur.hint') + '</span></div>'
        '</div>')


def _merge_preview():
    """Two source books in, one facing-text book out -- the b side reacts live
    to the blur controls."""
    interleaved = []
    for en, fr in zip(PV_EN, PV_FR):
        interleaved.append('<p class="a">' + en + '</p>')
        interleaved.append('<p class="b">' + fr + '</p>')
    return (
        '<aside class="side">'
        '<div class="cap">' + t('web.pv.sources') + '</div>'
        '<p class="pv-note">' + t('web.pv.real') + '</p>'
        '<div class="pv-pair">'
        + _book('sample-en.epub', 'EN', PV_EN, dl='demo-en')
        + _book('sample-fr.epub', 'FR', PV_FR, dl='demo-fr')
        + '</div>'
        + _flow(t('web.pv.merge')) +
        '<div class="cap">' + t('web.pv.result') + '</div>'
        '<div class="book out preview blur-b" style="margin-top:.5rem">'
        '<div class="book-h"><span class="tag">EN + FR</span>'
        '<span class="book-n">bilingual.epub</span>'
        '<a class="book-dl" href="/download?id=demo-bi" download>'
        + t('web.pv.download') + '</a></div>'
        + ''.join(interleaved) +
        '</div>'
        '<p class="pv-tap">' + t('web.pv.tap') + '</p>'
        '</aside>')


def _split_preview():
    """One bilingual book in, one book per language out."""
    mixed = []
    for en, fr in zip(PV_EN, PV_FR):
        mixed.append('<p class="a">' + en + '</p>')
        mixed.append('<p class="b">' + fr + '</p>')
    return (
        '<aside class="side">'
        '<div class="cap">' + t('web.pv.sources') + '</div>'
        '<p class="pv-note">' + t('web.pv.real') + '</p>'
        '<div class="book"><div class="book-h">'
        '<span class="tag">EN + FR</span><span class="book-n">bilingual.epub</span>'
        '<a class="book-dl" href="/download?id=demo-bi" download>'
        + t('web.pv.download') + '</a></div>'
        + ''.join(mixed) +
        '</div>'
        + _flow(t('web.pv.split')) +
        '<div class="cap">' + t('web.pv.result') + '</div>'
        '<div class="pv-pair" style="margin-top:.5rem">'
        + _book('bilingual.en.epub', 'EN', PV_EN, cls='out', dl='demo-split-en')
        + _book('bilingual.fr.epub', 'FR', PV_FR, cls='out', dl='demo-split-fr')
        + '</div>'
        '</aside>')


def _remerge_preview():
    """One bilingual book in, the same book restyled out."""
    rows = []
    for en, fr in zip(PV_EN, PV_FR):
        rows.append('<p class="a">' + en + '</p>')
        rows.append('<p class="b">' + fr + '</p>')
    plain = []
    for en, fr in zip(PV_EN, PV_FR):
        plain.append('<p>' + en + '</p>')
        plain.append('<p>' + fr + '</p>')
    return (
        '<aside class="side">'
        '<div class="cap">' + t('web.pv.sources') + '</div>'
        '<p class="pv-note">' + t('web.pv.real') + '</p>'
        '<div class="book"><div class="book-h">'
        '<span class="tag">EN + FR</span><span class="book-n">bilingual.epub</span>'
        '<a class="book-dl" href="/download?id=demo-bi" download>'
        + t('web.pv.download') + '</a></div>'
        + ''.join(plain) +
        '</div>'
        + _flow(t('web.pv.remerge')) +
        '<div class="cap">' + t('web.pv.result') + '</div>'
        '<div class="book out preview blur-b" style="margin-top:.5rem">'
        '<div class="book-h"><span class="tag">EN + FR</span>'
        '<span class="book-n">remerged.epub</span>'
        '<a class="book-dl" href="/download?id=demo-remerged" download>'
        + t('web.pv.download') + '</a></div>'
        + ''.join(rows) +
        '</div>'
        '<p class="pv-tap">' + t('web.pv.tap') + '</p>'
        '</aside>')


def _merge_panel(cfg, page_token):
    return (
        '<div class="panel on" id="panel-merge">'
        '<p class="lead">' + t('web.merge.lead') + '</p>'
        '<form action="/api/merge">'
        '<input type="hidden" name="page_token" value="' + page_token + '">'
        '<div class="panel-body"><div class="main-col">'
        '<div class="grid">'
        + _file_field(t('web.side.a'), 'a_file', 'a_path', '/path/to/english.epub', cfg=cfg)
        + _file_field(t('web.side.b'), 'b_file', 'b_path', '/path/to/other-language.epub', cfg=cfg)
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
        + cfg.turnstile.widget_html() +
        '<button class="go" type="submit"><span class="spinner"></span>'
        + t('web.go.merge') + '</button>'
        '</div>' + _merge_preview() + '</div></form>'
        '<div class="result"></div></div>')


def _split_panel(cfg, page_token):
    return (
        '<div class="panel" id="panel-split">'
        '<p class="lead">' + t('web.split.lead') + '</p>'
        '<form action="/api/split">'
        '<input type="hidden" name="page_token" value="' + page_token + '">'
        '<div class="panel-body"><div class="main-col">'
        + _file_field(t('web.src'), 'in_file', 'in_path',
                      '/path/to/bilingual.epub', t('web.drop.bi'), cfg=cfg)
        + '<div class="field"><label>' + t('web.langs') + '</label>'
        '<input type="text" name="langs" placeholder="en,fr">'
        '<span class="hint">' + t('web.langs.hint') + '</span></div>'
        + cfg.turnstile.widget_html() +
        '<button class="go" type="submit"><span class="spinner"></span>'
        + t('web.go.split') + '</button>'
        '</div>' + _split_preview() + '</div></form>'
        '<div class="result"></div></div>')


def _remerge_panel(cfg, page_token):
    return (
        '<div class="panel" id="panel-remerge">'
        '<p class="lead">' + t('web.remerge.lead') + '</p>'
        '<form action="/api/remerge">'
        '<input type="hidden" name="page_token" value="' + page_token + '">'
        '<div class="panel-body"><div class="main-col">'
        + _file_field(t('web.src.bi'), 'in_file', 'in_path',
                      '/path/to/bilingual.epub', t('web.drop.bi'), cfg=cfg)
        + '<div class="grid">'
        '<div class="field"><label>' + t('web.alang') + '</label>'
        '<input type="text" name="a_lang" placeholder="en">'
        '<span class="hint">' + t('web.alang.hint') + '</span></div>'
        '<div class="field"><label>' + t('web.blang') + '</label>'
        '<input type="text" name="b_lang" placeholder="fr">'
        '<span class="hint">' + t('web.blang.hint') + '</span></div>'
        '</div>'
        + _blur_controls()
        + cfg.turnstile.widget_html() +
        '<button class="go" type="submit"><span class="spinner"></span>'
        + t('web.go.remerge') + '</button>'
        '</div>' + _remerge_preview() + '</div></form>'
        '<div class="result"></div></div>')


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
    '</header>'
    '<div class="tabs" role="tablist">'
    '<button class="tab" data-tab="merge" role="tab" aria-selected="true">__T_MERGE__</button>'
    '<button class="tab" data-tab="split" role="tab" aria-selected="false">__T_SPLIT__</button>'
    '<button class="tab" data-tab="remerge" role="tab" aria-selected="false">__T_REMERGE__</button>'
    '</div>'
    '__MERGE__' '__SPLIT__' '__REMERGE__'
    '<footer><p class="agent">__AGENT__</p>'
    '__FOOTER__ <span class="host">__LOCAL__</span></footer>'
    '</div>__CFSCRIPT__<script>const L=__LABELS__;</script>'
    '<script>__JS__</script></body></html>')


def render_page(cfg=None, page_token='', reports_on=False):
    """Render the whole page in the currently selected language."""
    cfg = cfg or Config()
    lang = get_lang()
    labels = json.dumps({
        'chapter': t('web.res.chapter'), 'a': t('web.res.a'), 'b': t('web.res.b'),
        'aOnly': t('web.res.a_only'), 'bOnly': t('web.res.b_only'),
        'failed': t('web.res.failed'), 'reqFailed': t('web.res.reqfail'),
        'uploaded': t('web.uploaded'),
        # the browser needs the ceiling so it can refuse before uploading
        'maxUpload': cfg.max_upload // 1048576,
        'canReport': bool(reports_on),
        'reportBtn': t('web.report.btn'), 'reportHead': t('web.report.head'),
        'reportWhat': t('web.report.what'), 'reportAttach': t('web.report.attach'),
        'reportWhy': t('web.report.why'), 'reportNote': t('web.report.note'),
        'reportSend': t('web.report.send'), 'reportCancel': t('web.report.cancel'),
        'reportOk': t('web.report.ok'), 'reportNoFiles': t('web.report.nofiles'),
        'pageToken': page_token,
        'tooBigJs': t('web.js.too_big'), 'rejectedJs': t('web.js.rejected'),
        'gatewayJs': t('web.js.gateway'), 'droppedJs': t('web.js.dropped'),
    }, ensure_ascii=False)
    return (PAGE
            .replace('__CSS__', CSS)
            .replace('__HTMLLANG__', 'zh-CN' if lang == 'zh' else 'en')
            .replace('__OTHERLANG__', 'en' if lang == 'zh' else 'zh')
            .replace('__SWITCH__', t('web.switch'))
            .replace('__TAGLINE__', t('app.tagline'))
            .replace('__T_MERGE__', t('web.tab.merge'))
            .replace('__T_SPLIT__', t('web.tab.split'))
            .replace('__T_REMERGE__', t('web.tab.remerge'))
            .replace('__AGENT__', t('web.agent_note'))
            .replace('__FOOTER__', t('web.footer') +
                     (' ' + t('web.public_note') if cfg.public else ''))
            .replace('__LOCAL__', t('app.local_only'))
            .replace('__MERGE__', _merge_panel(cfg, page_token))
            .replace('__SPLIT__', _split_panel(cfg, page_token))
            .replace('__REMERGE__', _remerge_panel(cfg, page_token))
            .replace('__CFSCRIPT__', cfg.turnstile.script_tag())
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


def _blur_side(fields):
    """An unchecked tap-to-reveal switch wins over whichever side is selected.

    Browsers omit unchecked checkboxes entirely, so its absence is the signal --
    but only for requests that actually carry the switch, which is why the
    marker field is checked first. That keeps a bare API call working.
    """
    if fields.get('has_switch') or 'tap_reveal' in fields:
        return fields.get('blur_side', 'b') if fields.get('tap_reveal') else 'none'
    return fields.get('blur_side', 'b')


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
        """Register a built file against the requesting session.

        The handle is random, not a counter: sequential ids are harmless when
        the only client is you on localhost, but they let anyone who can reach
        the server walk the numbers and collect everybody's books. Scoping to
        the session is the other half -- guessing a handle is not enough, it
        has to be your handle.
        """
        token = self.server.sessions.register(self._sid(), path)
        if token is None:
            raise SystemExit(t('web.quota'))
        return {'id': token, 'name': os.path.basename(path)}

    def _source(self, fields, files, file_key, path_key, label):
        """A dropped upload wins over a typed path; one of the two is required."""
        if file_key in files:
            # already streamed to its own directory under the session, with the
            # client's filename preserved so split/merge output names read well
            _client_name, dest = files[file_key]
            self._inputs.append(dest)
            return dest
        typed = (fields.get(path_key) or '').strip()
        if typed:
            if not self.server.cfg.allow_paths:
                # on a public host this would read any file the server can
                # reach, so it is refused outright rather than sanitised
                raise SystemExit(t('web.no_paths'))
            if not os.path.exists(typed):
                raise SystemExit(t('web.no_such', label, typed))
            self._inputs.append(typed)
            return typed
        raise SystemExit(t('web.need_file', label))

    def _out_path(self, stem):
        sess = self.server.sessions.get(self._sid())
        return os.path.join(sess['dir'] if sess else self.server.outputs, stem)

    # ---- GET ------------------------------------------------------------ #
    def _log_failure(self, route, error):
        report = {
            'endpoint': route,
            'error_type': type(error).__name__,
            'error': diagnostics.scrub(str(error))[:800],
            'inputs': [diagnostics.fingerprint(p) for p in self._inputs],
            'public': self.server.cfg.public,
        }
        if not isinstance(error, SystemExit):
            report['traceback'] = diagnostics.scrub(traceback.format_exc())[-3000:]
        path = getattr(self.server, 'error_log', None)
        if path:
            diagnostics.record(path, route, error, self._inputs,
                               {'public': self.server.cfg.public})
        # hold it against the session so "report this" has something to send,
        # along with the files themselves in case the user offers them
        sess = self.server.sessions.get(self._sid())
        if sess is not None:
            sess['last_failure'] = (report, list(self._inputs))
        return report

    def _do_report(self):
        """Take a failure report the user chose to send.

        No second Turnstile check: this session already passed one to run the
        job that failed, and asking again to report a bug is a good way to not
        hear about bugs. Files can only come from that session's own failed
        attempt, so this cannot be used as a general upload endpoint.
        """
        sess = self.server.sessions.get(self._sid())
        if sess is None:
            self._json({'ok': False, 'error': t('web.no_session')}, status=403)
            return
        length = int(self.headers.get('Content-Length', 0) or 0)
        if length > 64 * 1024:
            self._json({'ok': False, 'error': t('web.stale_page')}, status=413)
            return
        try:
            body = json.loads(self.rfile.read(length).decode('utf-8'))
        except ValueError:
            self._json({'ok': False, 'error': t('web.stale_page')}, status=400)
            return
        if body.get('page_token') != sess['page_token']:
            self._json({'ok': False, 'error': t('web.stale_page')}, status=403)
            return

        held = sess.get('last_failure')
        if not held:
            self._json({'ok': False, 'error': t('web.report.gone')}, status=409)
            return
        report, files = held
        report = dict(report, note=str(body.get('note') or '')[:2000],
                      user_agent=self.headers.get('User-Agent', '')[:300])

        attach = bool(body.get('attach'))
        available = [p for p in files if p and os.path.exists(p)]
        rid = diagnostics.save_report(self.server.reports_dir, report,
                                      available if attach else ())
        self._json({'ok': True, 'id': rid,
                    'attached': bool(attach and available),
                    'wanted_attach': attach})

    def _sid(self):
        raw = self.headers.get('Cookie', '')
        for part in raw.split(';'):
            name, _, value = part.strip().partition('=')
            if name == 'bes':
                return value
        return ''

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path == '/':
            # ?lang=en|zh switches the page language for the rest of the session
            want = urllib.parse.parse_qs(p.query).get('lang', [''])[0]
            if want in ('en', 'zh'):
                set_lang(want)
            sess = self.server.sessions.get(self._sid())
            headers = []
            if sess is None:
                sid = self.server.sessions.issue()
                sess = self.server.sessions.get(sid)
                headers.append(('Set-Cookie',
                                'bes=%s; Path=/; HttpOnly; SameSite=Strict' % sid))
            self._send(render_page(self.server.cfg, sess['page_token'],
                                   reports_on=bool(self.server.reports_dir)),
                       headers=headers)
        elif p.path == '/skill':
            # the agent route: hand over the instructions so someone's own
            # coding agent can drive this tool on their own subscription
            here = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(here, 'skill', 'SKILL.md'), 'rb') as f:
                data = f.read()
            self._send(data, ctype='text/markdown; charset=utf-8', headers=[
                ('Content-Disposition', 'attachment; filename="SKILL.md"')])
        elif p.path == '/download':
            token = urllib.parse.parse_qs(p.query).get('id', [''])[0]
            # demo books belong to everyone; anything else only to its session
            path = self.server.offered.get(token)
            if path is None:
                path = self.server.sessions.resolve(self._sid(), token)
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
        if route == '/api/report':
            self._do_report()
            return
        if route not in ('/api/merge', '/api/split', '/api/remerge'):
            self._json({'ok': False, 'error': 'unknown endpoint'}, status=404)
            return

        cfg = self.server.cfg
        self._inputs = []
        sess = self.server.sessions.get(self._sid())
        if sess is None:
            # every POST has to come from a page this server handed out
            self._json({'ok': False, 'error': t('web.no_session')}, status=403)
            return
        ok, wait = self.server.limiter.check(self.client_address[0])
        if not ok:
            self._json({'ok': False, 'error': t('web.slow_down', int(wait) + 1)},
                       status=429)
            return

        ctype = self.headers.get('Content-Type', '')
        length = int(self.headers.get('Content-Length', 0) or 0)
        if length > cfg.max_upload * 2 + (4 << 20):
            self._json({'ok': False,
                        'error': t('web.too_big', cfg.max_upload // 1048576)},
                       status=413)
            return

        # Stream straight to disk. Reading the body into memory and splitting it
        # is what got this process OOM-killed nine times.
        scratch = sess['dir']
        if 'multipart/form-data' in ctype and 'boundary=' in ctype:
            boundary = ctype.split('boundary=', 1)[1].strip().strip('"').encode()
            try:
                fields, parts = multipart.parse(self.rfile, boundary, length,
                                                scratch)
            except multipart.TooLarge:
                self._json({'ok': False,
                            'error': t('web.too_big', cfg.max_upload // 1048576)},
                           status=413)
                return
            files = {}
            for name, (client_name, path) in parts.items():
                if os.path.getsize(path) > cfg.max_upload:
                    self._json({'ok': False,
                                'error': t('web.too_big',
                                           cfg.max_upload // 1048576)}, status=413)
                    return
                files[name] = (client_name, path)
        else:
            body = self.rfile.read(min(length, MAX_FORM_BODY))
            fields = {k: v[0] for k, v in
                      urllib.parse.parse_qs(body.decode('utf-8', 'replace')).items()}
            files = {}

        if fields.get('page_token') != sess['page_token']:
            self._json({'ok': False, 'error': t('web.stale_page')}, status=403)
            return

        ok, why = cfg.turnstile.verify(
            fields.get('cf-turnstile-response', ''), self.client_address[0])
        if not ok:
            msg = {'missing': t('web.cf_missing'),
                   'unreachable': t('web.cf_down')}.get(why, t('web.cf_failed'))
            self._json({'ok': False, 'error': msg}, status=403)
            return

        buf = io.StringIO()
        real_stdout, sys.stdout = sys.stdout, buf
        # aligning a book is CPU-bound; a few in parallel will bury a small host
        with self.server.slots:
            try:
                payload = getattr(self, '_do_' + route.rsplit('/', 1)[1])(fields, files)
                payload['log'] = buf.getvalue().strip()
                payload['ok'] = True
            except SystemExit as e:
                # these carry a message written for a person to read -- but not
                # the server-side path they happened to mention, which is a
                # temp directory and a session id the reader has no use for
                payload = {'ok': False, 'error': diagnostics.scrub(str(e))}
                self._log_failure(route, e)
            except Exception as e:
                # an unexpected failure: log it here, but do not ship the
                # traceback to the browser -- it carries absolute server paths
                traceback.print_exc(file=sys.stderr)
                payload = {'ok': False, 'error': t('web.crashed')}
                self._log_failure(route, e)
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
            blur_side=_blur_side(fields),
            convert_side=(fields.get('convert_side') or '').strip() or None,
            cc_config=(fields.get('convert') or 'none').strip() or 'none',
            title=(fields.get('title') or '').strip() or None)
        return {'title': t('web.ok.merge'), 'stats': [list(r) for r in stats],
                'files': [self._offer(out)]}

    def _do_split(self, fields, files):
        src = self._source(fields, files, 'in_file', 'in_path', t('web.src'))
        langs = [s.strip() for s in (fields.get('langs') or '').split(',') if s.strip()]
        sess = self.server.sessions.get(self._sid())
        out_dir = sess['dir'] if sess else self.server.outputs
        results = split_mod.split_by_lang(src, out_dir, langs=langs or None)
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
                blur_side=_blur_side(fields))
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
    ap.add_argument('--public', action='store_true',
                    help='serve on a public interface: refuse server-side paths, '
                         'isolate visitors, rate-limit, and expire uploads')
    ap.add_argument('--host', default=None,
                    help='bind address (default 127.0.0.1, or 0.0.0.0 with --public)')
    ap.add_argument('--reports-dir', default=None, metavar='PATH',
                    help='where user-submitted failure reports are kept '
                         '(enables the "report this failure" button)')
    ap.add_argument('--error-log', default=None, metavar='PATH',
                    help='append a JSON line describing each failed job '
                         '(structure and traceback only, never book text)')
    ap.add_argument('--ttl', type=float, default=1800.0,
                    help='seconds an idle session keeps its files (default 1800)')
    ap.add_argument('--turnstile-sitekey', default=None,
                    help='Cloudflare Turnstile site key (or TURNSTILE_SITEKEY)')
    ap.add_argument('--turnstile-secret', default=None,
                    help='Cloudflare Turnstile secret (or TURNSTILE_SECRET)')
    args = ap.parse_args()
    if args.lang:
        set_lang(args.lang)

    # walk forward if the port is taken, so "one is already running" does not
    # surface as a bare Address already in use
    cfg = Config(public=args.public, ttl=args.ttl,
                 turnstile=guard.Turnstile(args.turnstile_sitekey,
                                           args.turnstile_secret))
    host = args.host or ('0.0.0.0' if args.public else HOST)  # noqa: S104

    srv, port = None, args.port
    for candidate in range(args.port, args.port + 20):
        try:
            srv = ThreadingHTTPServer((host, candidate), Handler)
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
    srv.cfg = cfg
    srv.error_log = args.error_log
    srv.reports_dir = args.reports_dir or os.path.join(workdir, 'reports')
    if not os.path.isdir(srv.reports_dir):
        os.makedirs(srv.reports_dir)
    srv.offered = build_demo(workdir)
    srv.sessions = guard.Sessions(os.path.join(workdir, 'sessions'), ttl=args.ttl)
    srv.limiter = guard.RateLimit()
    srv.slots = threading.BoundedSemaphore(1)
    reaper = guard.Reaper(srv.sessions, srv.limiter)
    reaper.start()

    url = 'http://%s:%d' % ('127.0.0.1' if host in ('0.0.0.0', '') else host, port)  # noqa: S104
    print('\n  \U0001F4D6  %s' % t('app.name'))
    print('  %s' % url)
    print(t('web.open_hint'))
    print(t('web.stop_hint'))

    if args.error_log:
        print('  failures logged to %s (file structure only, no book text)'
              % args.error_log)
    if args.reports_dir:
        print('  user-submitted reports go to %s' % args.reports_dir)
    if args.public:
        print('  public mode: server-side paths refused, one scratch area per '
              'visitor, rate limited, uploads expire after %d min.'
              % (args.ttl // 60))
        if cfg.turnstile.enabled:
            print('  Turnstile is on: every job is verified with Cloudflare '
                  'before it runs.\n')
        else:
            print('  Turnstile is OFF -- cookies and rate limits only, which a '
                  'headless browser walks straight through.')
            print('  Set --turnstile-sitekey/--turnstile-secret (or the '
                  'TURNSTILE_* env vars) to turn it on.\n')

    if not args.no_browser and not args.public:
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
