#!/usr/bin/env python3
"""Local web UI for merge.py/split.py -- stdlib only, no framework.

Three tabs: merge (2 monolingual -> 1 bilingual), split (1 bilingual -> N
monolingual), remerge (1 existing bilingual -> new bilingual w/ new options).

    python3 webui.py            # then open http://127.0.0.1:8799
"""
import html
import io
import os
import shutil
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import merge as merge_mod
from . import split as split_mod

HOST, PORT = '127.0.0.1', 8799

STYLE = """
  body { font-family: -apple-system, "PingFang SC", sans-serif; max-width: 760px;
         margin: 3em auto; padding: 0 1.5em; color: #222; line-height: 1.6; }
  h1 { font-size: 1.3em; } h2 { font-size: 1.05em; margin-top: 2.2em; }
  .warn { background: #fff6e5; border: 1px solid #f0d18a; border-radius: 8px;
          padding: .8em 1em; font-size: .92em; }
  .tabs { display: flex; gap: .5em; margin: 1.4em 0; }
  .tabs a { padding: .4em 1em; border-radius: 6px; text-decoration: none;
            color: #333; background: #eee; font-size: .9em; }
  .tabs a.active { background: #2563eb; color: #fff; }
  label { display: block; margin: 1.1em 0 .3em; font-weight: 600; font-size: .92em; }
  input[type=text] { width: 100%; box-sizing: border-box; padding: .5em .6em;
         font-size: .95em; border: 1px solid #ccc; border-radius: 6px; }
  .row { display: flex; gap: 1em; } .row > div { flex: 1; }
  button { margin-top: 1.6em; padding: .6em 1.6em; font-size: .95em;
            border: 0; border-radius: 6px; background: #2563eb; color: #fff; cursor: pointer; }
  button:hover { background: #1d4ed8; }
  pre { background: #f5f5f5; padding: 1em; border-radius: 8px; overflow-x: auto; font-size: .82em; }
  .ok { color: #15803d; } .err { color: #b91c1c; white-space: pre-wrap; }
  a.dl { display: inline-block; margin: .4em .4em 0 0; padding: .5em 1.2em;
          background: #15803d; color: #fff; border-radius: 6px; text-decoration: none; }
"""

INTRO = """<p class="warn">只在本机 127.0.0.1 监听，不出本机；路径要填这台机器上真实存在的文件。
支持任意标准 EPUB（不只是某一本特定的书）——原理是照着 EPUB 的 OPF/spine 自动认章节结构，
不是靠某本书的手写文件名表。DRM 加密的 EPUB 读不了。</p>"""

TABS = ['merge', 'split', 'remerge']


def tabs_html(active):
    return '<div class="tabs">' + ''.join(
        '<a href="/%s" class="%s">%s</a>' % (t, 'active' if t == active else '', t) for t in TABS
    ) + '</div>'


MERGE_FORM = """
<h1>合并：两本单语 EPUB → 一本双语 EPUB</h1>
{tabs}{intro}
<form method="post" action="/merge">
  <label>A 侧 EPUB 路径 (默认不模糊)</label>
  <input type="text" name="a" value="{a}" placeholder="/path/to/english.epub">
  <label>B 侧 EPUB 路径 (默认模糊)</label>
  <input type="text" name="b" value="{b}" placeholder="/path/to/other-language.epub">
  <label>输出 EPUB 路径</label>
  <input type="text" name="out" value="{out}">
  <div class="row">
    <div><label>模糊哪一侧</label>
      <select name="blur_side"><option value="b" {sel_b}>B</option><option value="a" {sel_a}>A</option><option value="none" {sel_n}>不模糊</option></select></div>
    <div><label>模糊程度</label><input type="text" name="blur" value="{blur}"></div>
  </div>
  <div class="row">
    <div><label>opencc 转换哪一侧 (留空=不转换)</label><input type="text" name="convert_side" value="{convert_side}" placeholder="a 或 b"></div>
    <div><label>opencc 配置</label><input type="text" name="convert" value="{convert}" placeholder="tw2sp / s2t / none"></div>
  </div>
  <label>书名覆盖 (留空=自动拼接两侧书名)</label>
  <input type="text" name="title" value="{title}">
  <button type="submit">合并</button>
</form>
{result}
"""

SPLIT_FORM = """
<h1>拆分：一本双语/多语 EPUB → 每种语言各一本单语 EPUB</h1>
{tabs}{intro}
<form method="post" action="/split">
  <label>源 EPUB 路径</label>
  <input type="text" name="input" value="{input}">
  <label>输出目录</label>
  <input type="text" name="out_dir" value="{out_dir}">
  <label>只拆这些语言 (逗号分隔，留空=拆出全部发现的语言)</label>
  <input type="text" name="langs" value="{langs}" placeholder="en,fr">
  <button type="submit">拆分</button>
</form>
{result}
"""

REMERGE_FORM = """
<h1>重新合并：已有双语 EPUB → 换参数生成新双语 EPUB</h1>
{tabs}{intro}
<p style="font-size:.9em;color:#555">用途：手头有一本别处来的双语书想换成这个工具的点按显示风格，
或者同一本双语书想换一下模糊程度/换糊哪一侧——不用手动先拆再合，这里一步做完。</p>
<form method="post" action="/remerge">
  <label>源双语 EPUB 路径</label>
  <input type="text" name="input" value="{input}">
  <label>输出 EPUB 路径</label>
  <input type="text" name="out" value="{out}">
  <div class="row">
    <div><label>A 侧语言代码 (留空=自动取第一个发现的)</label><input type="text" name="a_lang" value="{a_lang}" placeholder="en"></div>
    <div><label>B 侧语言代码 (留空=自动取第二个，会被模糊)</label><input type="text" name="b_lang" value="{b_lang}" placeholder="fr"></div>
  </div>
  <div class="row">
    <div><label>模糊哪一侧</label>
      <select name="blur_side"><option value="b" {sel_b}>B</option><option value="a" {sel_a}>A</option><option value="none" {sel_n}>不模糊</option></select></div>
    <div><label>模糊程度</label><input type="text" name="blur" value="{blur}"></div>
  </div>
  <button type="submit">重新合并</button>
</form>
{result}
"""

PAGE = "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>Bilingual EPUB Toolkit</title><style>%s</style></head><body>%s</body></html>"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    def _send(self, body, status=200, ctype='text/html; charset=utf-8'):
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _form(self):
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length).decode('utf-8')
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}

    def _dl_link(self, path):
        return '<a class="dl" href="/download?file=%s">下载 %s</a>' % (
            urllib.parse.quote(path), html.escape(os.path.basename(path)))

    # ---- GET ------------------------------------------------------------ #
    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path in ('/', '/merge'):
            self._send(PAGE % (STYLE, MERGE_FORM.format(
                tabs=tabs_html('merge'), intro=INTRO, a='', b='', out='',
                sel_a='', sel_b='selected', sel_n='', blur='0.25em',
                convert_side='', convert='none', title='', result='')))
        elif p.path == '/split':
            self._send(PAGE % (STYLE, SPLIT_FORM.format(
                tabs=tabs_html('split'), intro=INTRO, input='', out_dir='', langs='', result='')))
        elif p.path == '/remerge':
            self._send(PAGE % (STYLE, REMERGE_FORM.format(
                tabs=tabs_html('remerge'), intro=INTRO, input='', out='',
                a_lang='', b_lang='', sel_a='', sel_b='selected', sel_n='', blur='0.25em', result='')))
        elif p.path == '/download':
            qs = urllib.parse.parse_qs(p.query)
            path = qs.get('file', [''])[0]
            allowed = getattr(self.server, 'served_files', set())
            if not path or path not in allowed or not os.path.exists(path):
                self._send('not found', status=404, ctype='text/plain')
                return
            with open(path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/epub+zip')
            self.send_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(path))
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._send('not found', status=404, ctype='text/plain')

    # ---- POST ------------------------------------------------------------ #
    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        form = self._form()
        buf = io.StringIO()
        real_stdout, sys.stdout = sys.stdout, buf
        try:
            if p == '/merge':
                out, stats = merge_mod.merge_bilingual(
                    a_epub=form.get('a', '').strip(), b_epub=form.get('b', '').strip(),
                    out_path=form.get('out', '').strip(),
                    blur=form.get('blur', '0.25em').strip() or '0.25em',
                    blur_side=form.get('blur_side', 'b'),
                    convert_side=(form.get('convert_side') or '').strip() or None,
                    cc_config=(form.get('convert') or 'none').strip() or 'none',
                    title=(form.get('title') or '').strip() or None)
                self._register(out)
                result = self._ok(buf, out)
                tpl, ctx = 'merge', dict(form)
            elif p == '/split':
                results = split_mod.split_by_lang(
                    form.get('input', '').strip(), form.get('out_dir', '').strip(),
                    langs=[s.strip() for s in form.get('langs', '').split(',') if s.strip()] or None)
                links = ' '.join(self._dl_link(pth) for pth in results.values())
                result = '<p class="ok">✅ 拆出 %d 种语言</p><pre>%s</pre>%s' % (
                    len(results), html.escape('\n'.join('%s -> %s' % kv for kv in results.items())), links)
                for pth in results.values():
                    self._register(pth)
                tpl, ctx = 'split', dict(form)
            elif p == '/remerge':
                import tempfile as _t
                tmp = _t.mkdtemp(prefix='remerge_')
                parts = split_mod.split_by_lang(form.get('input', '').strip(), os.path.join(tmp, 'parts'), workdir=tmp)
                langs = sorted(parts)
                a_lang = (form.get('a_lang') or '').strip() or (langs[0] if langs else None)
                b_lang = (form.get('b_lang') or '').strip() or (langs[1] if len(langs) > 1 else None)
                if not a_lang or not b_lang or a_lang not in parts or b_lang not in parts:
                    raise SystemExit('这本书里找到的语言是: %s；a/b 语言代码必须从里面选。' % ', '.join(langs))
                out, stats = merge_mod.merge_bilingual(
                    a_epub=parts[a_lang], b_epub=parts[b_lang], out_path=form.get('out', '').strip(),
                    blur=form.get('blur', '0.25em').strip() or '0.25em',
                    blur_side=form.get('blur_side', 'b'))
                shutil.rmtree(tmp, ignore_errors=True)
                self._register(out)
                result = self._ok(buf, out, extra='发现语言: %s（a=%s, b=%s）' % (', '.join(langs), a_lang, b_lang))
                tpl, ctx = 'remerge', dict(form)
            else:
                self._send('not found', status=404, ctype='text/plain')
                return
        except SystemExit as e:
            result = '<p class="err">❌ %s</p>' % html.escape(str(e))
            tpl = p.strip('/')
            ctx = dict(form)
        except Exception:
            result = '<p class="err">❌ %s</p>' % html.escape(traceback.format_exc())
            tpl = p.strip('/')
            ctx = dict(form)
        finally:
            sys.stdout = real_stdout

        if tpl == 'merge':
            bs = ctx.get('blur_side', 'b')
            self._send(PAGE % (STYLE, MERGE_FORM.format(
                tabs=tabs_html('merge'), intro=INTRO, a=ctx.get('a', ''), b=ctx.get('b', ''),
                out=ctx.get('out', ''), sel_a='selected' if bs == 'a' else '',
                sel_b='selected' if bs == 'b' else '', sel_n='selected' if bs == 'none' else '',
                blur=ctx.get('blur', '0.25em'), convert_side=ctx.get('convert_side', ''),
                convert=ctx.get('convert', 'none'), title=ctx.get('title', ''), result=result)))
        elif tpl == 'split':
            self._send(PAGE % (STYLE, SPLIT_FORM.format(
                tabs=tabs_html('split'), intro=INTRO, input=ctx.get('input', ''),
                out_dir=ctx.get('out_dir', ''), langs=ctx.get('langs', ''), result=result)))
        else:
            bs = ctx.get('blur_side', 'b')
            self._send(PAGE % (STYLE, REMERGE_FORM.format(
                tabs=tabs_html('remerge'), intro=INTRO, input=ctx.get('input', ''), out=ctx.get('out', ''),
                a_lang=ctx.get('a_lang', ''), b_lang=ctx.get('b_lang', ''),
                sel_a='selected' if bs == 'a' else '', sel_b='selected' if bs == 'b' else '',
                sel_n='selected' if bs == 'none' else '', blur=ctx.get('blur', '0.25em'), result=result)))

    def _register(self, path):
        self.server.served_files.add(path)

    def _ok(self, buf, out, extra=''):
        stats_txt = html.escape(buf.getvalue())
        extra_html = ('<p>%s</p>' % html.escape(extra)) if extra else ''
        return ('<p class="ok">✅ 构建成功</p>%s<pre>%s</pre>%s'
               % (extra_html, stats_txt, self._dl_link(out)))


def main():
    import argparse
    import threading
    import webbrowser

    ap = argparse.ArgumentParser(description='双语 EPUB 工具箱的本地网页界面')
    ap.add_argument('--port', type=int, default=PORT, help='端口，默认 %d' % PORT)
    ap.add_argument('--no-browser', action='store_true', help='不要自动打开浏览器')
    args = ap.parse_args()

    # 端口被占就往后找，别让"已经有一个在跑"变成一句 Address already in use
    port = args.port
    srv = None
    for candidate in range(args.port, args.port + 20):
        try:
            srv = HTTPServer((HOST, candidate), Handler)
            port = candidate
            break
        except OSError:
            continue
    if srv is None:
        print('端口 %d~%d 全被占用了，用 --port 指定一个别的。' % (args.port, args.port + 19),
              file=sys.stderr)
        return 1
    if port != args.port:
        print('（%d 被占用了，改用 %d）' % (args.port, port))

    srv.served_files = set()
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
    return 0


if __name__ == '__main__':
    sys.exit(main())
