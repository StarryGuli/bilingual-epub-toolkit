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
      sub.textContent = (f.size / 1048576).toFixed(1) + ' MB · 会上传到本机服务器';
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
  const head = ['章节', 'A 段', 'B 段', '1:1', 'n:m', '仅 A', '仅 B'];
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
      out.innerHTML = '<div class="card bad"><h3>没能完成</h3><pre>' +
        esc(data.error) + '</pre></div>';
    }
  } catch (err) {
    out.innerHTML = '<div class="card bad"><h3>请求失败</h3><pre>' +
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
        '<button type="button" class="clear" hidden aria-label="清除所选文件">&times;</button>'
        '<input type="file" name="' + name + '" accept=".epub,application/epub+zip">'
        '<span class="ico">📕</span>'
        '<span class="main">' + main + '</span>'
        '<span class="sub">' + sub + '</span>'
        '</div>')


def _blur_controls():
    return (
        '<div class="grid">'
        '<div class="field"><label>模糊哪一侧</label>'
        '<select name="blur_side">'
        '<option value="b" selected>B 侧（译文）</option>'
        '<option value="a">A 侧（原文）</option>'
        '<option value="none">都不模糊</option>'
        '</select></div>'
        '<div class="field"><label>模糊程度</label>'
        '<input type="text" name="blur" value="0.25em">'
        '<span class="hint">CSS 长度，建议用 em，会跟随字号缩放</span></div>'
        '</div>'
        '<div class="preview blur-b">'
        '<div class="cap">效果预览</div>'
        '<p class="a">It was a bright cold day in the invented town.</p>'
        '<p class="b">C’était une journée froide et lumineuse dans la ville inventée.</p>'
        '</div>')


MERGE_PANEL = (
    '<div class="panel on" id="panel-merge">'
    '<p class="lead">两本单语 EPUB 合成一本对照书：A 侧一段，B 侧对应的一段紧跟在下面，'
    '默认糊住，点一下显示。</p>'
    '<form action="/api/merge">'
    '<div class="grid">'
    '<div class="field"><label>A 侧（原文）</label>'
    + _drop('a_file', '拖一本 EPUB 到这里', '或点击选择')
    + '<div class="or">或填本机路径</div>'
    '<input type="text" name="a_path" placeholder="/path/to/english.epub"></div>'
    '<div class="field"><label>B 侧（译文）</label>'
    + _drop('b_file', '拖一本 EPUB 到这里', '或点击选择')
    + '<div class="or">或填本机路径</div>'
    '<input type="text" name="b_path" placeholder="/path/to/other-language.epub"></div>'
    '</div>'
    + _blur_controls() +
    '<div class="grid">'
    '<div class="field"><label>opencc 转换（可选）</label>'
    '<select name="convert_side">'
    '<option value="">不转换</option>'
    '<option value="a">转换 A 侧</option>'
    '<option value="b">转换 B 侧</option>'
    '</select><span class="hint">中文繁简转换，需装 opencc</span></div>'
    '<div class="field"><label>opencc 配置</label>'
    '<input type="text" name="convert" value="none" placeholder="tw2sp / s2t">'
    '<span class="hint">例：tw2sp 繁转简</span></div>'
    '</div>'
    '<div class="field"><label>书名（可选）</label>'
    '<input type="text" name="title" placeholder="留空则自动拼接两侧书名"></div>'
    '<button class="go" type="submit"><span class="spinner"></span>合并成对照书</button>'
    '</form><div class="result"></div></div>')

SPLIT_PANEL = (
    '<div class="panel" id="panel-split">'
    '<p class="lead">把一本双语（或多语）EPUB 按语言拆开，每种语言各出一本单语书。'
    '靠每段的 <code>lang</code> 属性判断归属。</p>'
    '<form action="/api/split">'
    '<div class="field"><label>源 EPUB</label>'
    + _drop('in_file', '拖一本双语 EPUB 到这里', '或点击选择')
    + '<div class="or">或填本机路径</div>'
    '<input type="text" name="in_path" placeholder="/path/to/bilingual.epub"></div>'
    '<div class="field"><label>只拆这些语言（可选）</label>'
    '<input type="text" name="langs" placeholder="en,fr">'
    '<span class="hint">逗号分隔；留空则拆出全部识别到的语言</span></div>'
    '<button class="go" type="submit"><span class="spinner"></span>拆分</button>'
    '</form><div class="result"></div></div>')

REMERGE_PANEL = (
    '<div class="panel" id="panel-remerge">'
    '<p class="lead">已经有一本双语书，想换个模糊程度、换糊哪一侧，或者把别处来的'
    '双语书转成这个工具的点按显示风格——先拆再合，这里一步完成。</p>'
    '<form action="/api/remerge">'
    '<div class="field"><label>源双语 EPUB</label>'
    + _drop('in_file', '拖一本双语 EPUB 到这里', '或点击选择')
    + '<div class="or">或填本机路径</div>'
    '<input type="text" name="in_path" placeholder="/path/to/bilingual.epub"></div>'
    '<div class="grid">'
    '<div class="field"><label>A 侧语言代码</label>'
    '<input type="text" name="a_lang" placeholder="en">'
    '<span class="hint">留空＝取识别到的第一种</span></div>'
    '<div class="field"><label>B 侧语言代码</label>'
    '<input type="text" name="b_lang" placeholder="fr">'
    '<span class="hint">留空＝取第二种</span></div>'
    '</div>'
    + _blur_controls() +
    '<button class="go" type="submit"><span class="spinner"></span>重新合并</button>'
    '</form><div class="result"></div></div>')

PAGE = (
    '<!doctype html><html lang="zh-CN"><head>'
    '<meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<meta name="color-scheme" content="light dark">'
    '<title>Bilingual EPUB Toolkit</title>'
    '<style>__CSS__</style></head><body><div class="wrap">'
    '<header>'
    '<h1 class="brand"><span class="mark">A | 文</span> Bilingual EPUB Toolkit</h1>'
    '<p class="tagline">两本单语书合成一本点按显示的对照书，也能反过来拆开。</p>'
    '<span class="local-note"><span class="dot"></span>只在本机运行，文件不出这台电脑</span>'
    '</header>'
    '<div class="tabs" role="tablist">'
    '<button class="tab" data-tab="merge" role="tab" aria-selected="true">合并</button>'
    '<button class="tab" data-tab="split" role="tab" aria-selected="false">拆分</button>'
    '<button class="tab" data-tab="remerge" role="tab" aria-selected="false">重新合并</button>'
    '</div>'
    '__MERGE__' '__SPLIT__' '__REMERGE__'
    '<footer>任意标准 EPUB 都能处理，DRM 加密的除外。'
    '用完在启动它的终端窗口按 Ctrl+C 停止。</footer>'
    '</div><script>__JS__</script></body></html>')


def render_page():
    return (PAGE
            .replace('__CSS__', CSS)
            .replace('__MERGE__', MERGE_PANEL)
            .replace('__SPLIT__', SPLIT_PANEL)
            .replace('__REMERGE__', REMERGE_PANEL)
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
                raise SystemExit('%s：找不到这个文件 —— %s' % (label, typed))
            return typed
        raise SystemExit('%s：请拖一个 EPUB 进来，或者填一个本机路径。' % label)

    def _out_path(self, stem):
        return os.path.join(self.server.outputs, stem)

    # ---- GET ------------------------------------------------------------ #
    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path == '/':
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
            self._json({'ok': False, 'error': '文件太大了（上限 %d MB）。'
                                              % (MAX_UPLOAD // 1048576)}, status=413)
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
        a = self._source(fields, files, 'a_file', 'a_path', 'A 侧')
        b = self._source(fields, files, 'b_file', 'b_path', 'B 侧')
        out = self._out_path('bilingual.epub')
        out, stats = merge_mod.merge_bilingual(
            a_epub=a, b_epub=b, out_path=out,
            blur=(fields.get('blur') or '0.25em').strip() or '0.25em',
            blur_side=fields.get('blur_side', 'b'),
            convert_side=(fields.get('convert_side') or '').strip() or None,
            cc_config=(fields.get('convert') or 'none').strip() or 'none',
            title=(fields.get('title') or '').strip() or None)
        return {'title': '合并完成', 'stats': [list(r) for r in stats],
                'files': [self._offer(out)]}

    def _do_split(self, fields, files):
        src = self._source(fields, files, 'in_file', 'in_path', '源 EPUB')
        langs = [s.strip() for s in (fields.get('langs') or '').split(',') if s.strip()]
        results = split_mod.split_by_lang(src, self.server.outputs, langs=langs or None)
        return {'title': '拆出 %d 种语言：%s' % (len(results), '、'.join(sorted(results))),
                'files': [self._offer(p) for p in results.values()]}

    def _do_remerge(self, fields, files):
        src = self._source(fields, files, 'in_file', 'in_path', '源双语 EPUB')
        tmp = tempfile.mkdtemp(prefix='remerge_')
        try:
            parts = split_mod.split_by_lang(src, os.path.join(tmp, 'parts'), workdir=tmp)
            found = sorted(parts)
            a_lang = (fields.get('a_lang') or '').strip() or (found[0] if found else None)
            b_lang = (fields.get('b_lang') or '').strip() or (
                found[1] if len(found) > 1 else None)
            if not a_lang or not b_lang or a_lang not in parts or b_lang not in parts:
                raise SystemExit('这本书里识别到的语言是：%s —— A/B 必须从里面选。'
                                 % '、'.join(found))
            out = self._out_path('remerged.epub')
            out, stats = merge_mod.merge_bilingual(
                a_epub=parts[a_lang], b_epub=parts[b_lang], out_path=out,
                blur=(fields.get('blur') or '0.25em').strip() or '0.25em',
                blur_side=fields.get('blur_side', 'b'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return {'title': '重新合并完成',
                'note': '识别到的语言：%s（A=%s，B=%s）' % ('、'.join(found), a_lang, b_lang),
                'stats': [list(r) for r in stats], 'files': [self._offer(out)]}


def main():
    import argparse
    import threading
    import webbrowser

    ap = argparse.ArgumentParser(description='双语 EPUB 工具箱的本地网页界面')
    ap.add_argument('--port', type=int, default=PORT, help='端口，默认 %d' % PORT)
    ap.add_argument('--no-browser', action='store_true', help='不要自动打开浏览器')
    args = ap.parse_args()

    # 端口被占就往后找，别让“已经有一个在跑”变成一句 Address already in use
    srv, port = None, args.port
    for candidate in range(args.port, args.port + 20):
        try:
            srv = HTTPServer((HOST, candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if srv is None:
        print('端口 %d~%d 都被占用了，用 --port 指定一个别的。'
              % (args.port, args.port + 19), file=sys.stderr)
        return 1
    if port != args.port:
        print('（%d 被占用了，改用 %d）' % (args.port, port))

    workdir = tempfile.mkdtemp(prefix='bilingual_web_')
    srv.uploads = os.path.join(workdir, 'uploads')
    srv.outputs = os.path.join(workdir, 'outputs')
    os.makedirs(srv.uploads)
    os.makedirs(srv.outputs)
    srv.offered = {}

    url = 'http://%s:%d' % (HOST, port)
    print('\n  📖  双语 EPUB 工具箱')
    print('  %s' % url)
    print('  浏览器应该会自动打开；没有的话手动把上面这行地址复制进去。')
    print('  用完在这个窗口按 Ctrl+C 关掉。\n')

    if not args.no_browser:
        # 等服务器真正开始监听再开浏览器，否则可能抢在前面吃到连接失败
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止。')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
