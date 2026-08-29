#!/usr/bin/env python3
"""Regenerate the social/promo images in this directory.

    python3 assets/promo/make_promo.py

Does the whole chain: starts the local web UI, screenshots it with headless
Chrome, crops the pieces the slides embed, writes the slide HTML, and renders
each slide to a 2160x2880 PNG (3:4 at 2x, which is what Xiaohongshu wants).

The HTML is kept next to the PNGs on purpose. The PNG is the output; the HTML
is the source, and without it the images cannot be edited or re-typeset.
"""
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CHROME = ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
PORT = 8942

# --------------------------------------------------------------------------- #
# shared styling
# --------------------------------------------------------------------------- #
BASE = r"""
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1440px}
body{background:#f7f2ea;color:#231f1a;
 font:400 16px/1.6 "PingFang SC","Hiragino Sans GB",-apple-system,sans-serif;
 -webkit-font-smoothing:antialiased;position:relative;overflow:hidden;
 padding:74px 64px;display:flex;flex-direction:column}
body::before{content:"";position:absolute;inset:0;
 background-image:radial-gradient(rgba(138,90,43,.13) 1.5px,transparent 1.5px);
 background-size:26px 26px;opacity:.55}
body::after{content:"";position:absolute;inset:0;pointer-events:none;
 background:radial-gradient(900px 620px at 88% -10%,rgba(212,150,80,.20),transparent 60%),
            radial-gradient(760px 620px at -14% 106%,rgba(138,90,43,.13),transparent 60%)}
.z{position:relative;z-index:2}
.win{background:#fff;border-radius:18px;overflow:hidden;
 box-shadow:0 3px 6px rgba(35,32,28,.07),0 28px 64px rgba(35,32,28,.17);
 border:1px solid #e3dbd0}
.win-bar{height:46px;background:#efe8de;display:flex;align-items:center;
 padding:0 18px;gap:9px;border-bottom:1px solid #e3dbd0}
.dot{width:13px;height:13px;border-radius:50%}
.win-url{margin-left:14px;flex:1;height:26px;border-radius:8px;background:#fbf8f4;
 border:1px solid #e6ded3;font:500 15px/26px "SF Mono",Menlo,monospace;
 color:#8a7a68;padding:0 12px;overflow:hidden;white-space:nowrap}
.win img{display:block;width:100%}
.sticker{position:absolute;z-index:5;background:#8a5a2b;color:#fff;
 font-size:25px;font-weight:700;padding:14px 26px;border-radius:14px;
 box-shadow:0 8px 22px rgba(138,90,43,.34);letter-spacing:.02em}
.sticker.g{background:#2f6b45;box-shadow:0 8px 22px rgba(47,107,69,.3)}
.sticker.w{background:#fff;color:#8a5a2b;border:2px solid #8a5a2b;
 box-shadow:0 8px 20px rgba(35,32,28,.12)}
.num{width:52px;height:52px;border-radius:50%;background:#8a5a2b;color:#fff;
 font:700 27px/52px "PingFang SC",sans-serif;text-align:center;flex:none;
 box-shadow:0 5px 14px rgba(138,90,43,.32)}
.note{position:absolute;z-index:6;background:#fff8e9;border:1.5px solid #e8d5ae;
 border-radius:12px;padding:14px 20px;font-size:23px;font-weight:600;color:#7a5a1e;
 box-shadow:0 8px 20px rgba(35,32,28,.13);max-width:340px;line-height:1.45}
.hl{background:linear-gradient(transparent 56%,rgba(212,150,80,.55) 56%);padding:0 3px}
h1{font-size:80px;line-height:1.16;font-weight:800;letter-spacing:-.025em}
h2{font-size:58px;line-height:1.24;font-weight:800;letter-spacing:-.02em}
.eyebrow{display:inline-flex;align-items:center;gap:10px;background:#8a5a2b;color:#fff;
 font-size:22px;font-weight:700;letter-spacing:.1em;padding:9px 20px;border-radius:999px}
.sub{font-size:26px;line-height:1.7;color:#5f574c}
.grow{flex:1}
.mark{display:flex;align-items:center;gap:12px;font-size:24px;color:#6b6156;font-weight:600}
.mark b{font-family:Georgia,"Songti SC",serif;font-size:30px;color:#8a5a2b;font-weight:400}
.chip{display:inline-block;padding:10px 22px;border-radius:999px;background:#fff;
 border:1.5px solid #e0d5c6;color:#6b5a45;font-size:22px;font-weight:600}
.term{background:#2a2621;border-radius:16px;padding:26px 30px;
 box-shadow:0 4px 8px rgba(35,32,28,.14),0 20px 42px rgba(35,32,28,.2);
 position:relative;z-index:2}
.term-bar{display:flex;gap:8px;margin-bottom:20px}
.term-bar span{width:12px;height:12px;border-radius:50%}
.term p{font:500 21px/1.8 "SF Mono",Menlo,monospace;color:#e6ddd0;white-space:nowrap}
.term .c{color:#7fc79b}
.term .d{color:#9b9186}
"""
PAGE = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<style>%s%s</style></head><body>%s</body></html>')
DOTS = ('<span class="dot" style="background:#e06c5f"></span>'
        '<span class="dot" style="background:#e5b34b"></span>'
        '<span class="dot" style="background:#5fb865"></span>')

EN1, EN2 = 'Vellmark had four hundred lamps,', 'and Ida lit every one of them.'
ZH1, ZH2 = '韦尔马克有四百盏灯，', '伊达把它们一盏一盏点亮。'


def slide(name, css, body):
    path = os.path.join(HERE, name + '.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(PAGE % (BASE, css, body))
    return path


# --------------------------------------------------------------------------- #
# the five slides
# --------------------------------------------------------------------------- #
def write_slides():
    slide('1-cover', """
.hero{position:relative;margin-top:26px}
.win{transform:rotate(-1.6deg);width:84%;margin-left:auto}
h1{margin-top:46px}
""", """
<div class="z"><span class="eyebrow">开源 · 免费 · 自己做</span></div>
<div class="hero z">
  <div class="win">
    <div class="win-bar">%s<div class="win-url">epub.starry-files.duckdns.org</div></div>
    <img src="shot-flow.png">
  </div>
  <div class="sticker" style="top:-26px;right:-16px;transform:rotate(6deg)">两本 → 一本</div>
  <div class="note" style="left:-30px;bottom:196px;transform:rotate(-4deg);max-width:214px;
       font-size:21px;padding:12px 16px">这行糊住了<br>点一下才显示 →</div>
</div>
<h1 class="z">把两本书<br><span class="hl">合成一本对照书</span></h1>
<p class="sub z" style="margin-top:22px">同一本书的英文版 + 中文版，合出一本 EPUB。<br>一段原文一段译文，译文默认糊着。</p>
<div class="grow"></div>
<div class="mark z"><b>A | 文</b> Bilingual EPUB Toolkit</div>
""" % DOTS)

    slide('2-translate', """
.flow{display:flex;align-items:center;gap:22px;margin-top:34px}
.fbox{flex:1;background:#fff;border:1.5px solid #e3dbd0;border-radius:16px;
 padding:24px 22px;box-shadow:0 3px 5px rgba(35,32,28,.05),0 16px 34px rgba(35,32,28,.08)}
.fbox.hi{border-color:#8a5a2b;border-width:2px}
.ft{font-size:21px;font-weight:700;color:#8a5a2b;margin-bottom:12px;letter-spacing:.04em}
.fp{font-size:20px;line-height:1.5;color:#4a443c}
.fp.b{filter:blur(5px)}
.arw{font-size:40px;color:#8a5a2b;font-weight:700;flex:none}
.ways{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:38px}
.way{background:#fff;border:1.5px solid #e3dbd0;border-radius:18px;padding:28px 26px;
 box-shadow:0 3px 5px rgba(35,32,28,.04),0 14px 30px rgba(35,32,28,.07);position:relative}
.way-h{display:flex;align-items:center;gap:14px;margin-bottom:14px}
.way-t{font-size:29px;font-weight:800}
.way-d{font-size:21px;line-height:1.6;color:#5f574c}
.term{margin-top:34px}
""", """
<div class="z"><span class="eyebrow">最常见的问题</span></div>
<h2 class="z" style="margin-top:24px">只有英文原版<br><span class="hl">也能做出来</span></h2>
<div class="flow z">
  <div class="fbox"><div class="ft">你只有这个</div>
    <p class="fp">Vellmark had four hundred lamps, and Ida lit every one of them.</p></div>
  <div class="arw">→</div>
  <div class="fbox hi"><div class="ft">AI 翻完，合出这个</div>
    <p class="fp">Vellmark had four hundred lamps…</p>
    <p class="fp b" style="margin-top:8px">韦尔马克有四百盏灯，伊达把它们一盏一盏点亮。</p></div>
</div>
<div class="ways z">
  <div class="way"><div class="way-h"><div class="num">1</div><div class="way-t">接自己的 API</div></div>
    <div class="way-d">OpenAI、DeepSeek、Kimi、智谱、<br>硅基流动、本地 Ollama⋯⋯<br>用你自己的额度</div></div>
  <div class="way"><div class="way-h"><div class="num">2</div><div class="way-t">交给 Claude Code</div></div>
    <div class="way-d">装个 skill，让你的编码 agent 翻，<br>用你已经在付的订阅，<br><b style="color:#2f6b45">不额外花钱</b></div></div>
</div>
<div class="term z">
  <div class="term-bar"><span style="background:#e06c5f"></span>
    <span style="background:#e5b34b"></span><span style="background:#5fb865"></span></div>
  <p><span class="c">$</span> bilingual-epub skill</p>
  <p class="d">  ✓ 已写出 .claude/skills/bilingual-epub/</p>
  <p class="d" style="margin-top:16px">然后直接跟你的 agent 说：</p>
  <p><span class="c">&gt;</span> 把这本书做成中英对照的</p>
</div>
<div class="grow"></div>
<p class="sub z">机翻的段落跟原文严格一一对应，不会串行——<br>这是它跟「随便扔给翻译软件」最大的区别。</p>
""")

    slide('3-reading', """
.phone{background:#fff;border-radius:34px;border:9px solid #2a2621;
 box-shadow:0 14px 40px rgba(35,32,28,.26);padding:34px 30px}
.phone .en{font-size:26px;line-height:1.6;color:#231f1a}
.phone .zh{font-size:25px;line-height:1.6;color:#231f1a;margin:14px 0 26px}
.phone .zh.b{filter:blur(6px)}
.stage{display:flex;gap:26px;align-items:flex-start;margin-top:30px}
.cap{text-align:center;font-size:23px;font-weight:700;color:#8a5a2b;margin-top:18px}
""", """
<div class="z"><span class="eyebrow">做出来之后</span></div>
<h2 class="z" style="margin-top:24px">先自己读，<span class="hl">读不懂再点</span></h2>
<div class="stage z">
  <div style="flex:1">
    <div class="phone">
      <p class="en">%s %s</p><p class="zh b">%s%s</p>
      <p class="en">Nobody had asked her to take the job.</p>
      <p class="zh b" style="margin-bottom:0">没人要求她接下这份活。</p>
    </div>
    <div class="cap">默认糊着</div>
  </div>
  <div style="font-size:44px;color:#8a5a2b;font-weight:800;padding-top:150px">→</div>
  <div style="flex:1">
    <div class="phone" style="border-color:#8a5a2b">
      <p class="en">%s %s</p><p class="zh">%s%s</p>
      <p class="en">Nobody had asked her to take the job.</p>
      <p class="zh" style="margin-bottom:0">没人要求她接下这份活。</p>
    </div>
    <div class="cap">点一下就显示</div>
  </div>
</div>
<div class="grow"></div>
<p class="sub z">苹果图书、微信读书导入、任意 EPUB 3 阅读器都能看。<br>再点一下收回去，不影响继续硬读。</p>
""" % (EN1, EN2, ZH1, ZH2, EN1, EN2, ZH1, ZH2))

    slide('4-how', """
.win{transform:rotate(1.2deg);margin-top:28px}
.rows{margin-top:40px;display:flex;flex-direction:column;gap:18px}
.r{display:flex;align-items:center;gap:18px;background:#fff;border:1.5px solid #e3dbd0;
 border-radius:16px;padding:22px 24px;box-shadow:0 3px 5px rgba(35,32,28,.04),0 12px 26px rgba(35,32,28,.06)}
.rt{font-size:27px;font-weight:800;flex:none;width:186px}
.rc{font:500 20px/1.4 "SF Mono",Menlo,monospace;color:#5a4a38;background:#f7f2ea;
 border:1px solid #e6ddd0;border-radius:9px;padding:12px 16px;flex:1;
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
""", """
<div class="z"><span class="eyebrow">三种做法</span></div>
<h2 class="z" style="margin-top:24px">挑一个顺手的</h2>
<div class="z" style="position:relative">
  <div class="win">
    <div class="win-bar">%s<div class="win-url">127.0.0.1:8799 · 本地运行</div></div>
    <img src="shot-drop.png">
  </div>
  <div class="sticker w" style="top:-20px;right:-14px;transform:rotate(5deg)">拖进来就行</div>
</div>
<div class="rows z">
  <div class="r"><div class="rt">网页版</div><div class="rc">bilingual-epub-web</div></div>
  <div class="r"><div class="rt">终端向导</div><div class="rc">bilingual-epub-tui</div></div>
  <div class="r"><div class="rt">命令行</div><div class="rc">bilingual-epub merge --a 英文.epub --b 中文.epub</div></div>
</div>
<div class="grow"></div>
<p class="sub z">界面中英双语，跟随系统语言。</p>
""" % DOTS)

    slide('5-links', """
.card{background:#fff;border:2px solid #8a5a2b;border-radius:22px;padding:32px 34px;
 box-shadow:0 4px 8px rgba(35,32,28,.06),0 20px 44px rgba(35,32,28,.12);position:relative}
.card+.card{margin-top:26px}
.card .l{font-size:22px;font-weight:700;color:#8a5a2b;margin-bottom:14px;letter-spacing:.05em}
.card .u{font:700 37px/1.45 "SF Mono",Menlo,monospace;color:#231f1a;word-break:break-all}
.card.alt{border-color:#e3dbd0}
.card.alt .l{color:#6b6156}
.chips{display:flex;gap:13px;flex-wrap:wrap;margin-top:34px}
.inst{margin-top:32px}
.inst .l2{font-size:19px;color:#9b9186;margin-bottom:14px;font-weight:600;letter-spacing:.06em}
.inst p{font:600 21px/1.62 "SF Mono",Menlo,monospace;color:#e6ddd0}
.inst .c{color:#7fc79b}
""", """
<div class="z"><span class="eyebrow">拿去用</span></div>
<h2 class="z" style="margin-top:24px">开源，免费<br><span class="hl">代码全部公开</span></h2>
<div class="z" style="margin-top:40px;position:relative">
  <div class="card"><div class="l">★ GITHUB · 点个 star 呗</div>
    <div class="u">github.com/StarryGuli/<br>bilingual-epub-toolkit</div></div>
  <div class="card alt"><div class="l">不想装？直接在线做（文件 30 分钟自动删）</div>
    <div class="u">epub.starry-files<br>.duckdns.org</div></div>
  <div class="sticker g" style="top:-24px;right:-16px;transform:rotate(7deg)">全部免费</div>
</div>
<div class="chips z">
  <span class="chip">Apache-2.0</span><span class="chip">Python 3.9+</span>
  <span class="chip">中英双语</span><span class="chip">无需注册</span>
</div>
<div class="term inst z">
  <div class="l2">装到本地</div>
  <p><span class="c">$</span> pip install git+https://github.com/<br>&nbsp;&nbsp;&nbsp;StarryGuli/bilingual-epub-toolkit</p>
</div>
<div class="grow"></div>
<p class="sub z" style="margin-bottom:22px">装到本地跑的时候，书不离开你的电脑。</p>
<div class="mark z"><b>A | 文</b> Bilingual EPUB Toolkit</div>
""")


# --------------------------------------------------------------------------- #
# screenshots + rendering
# --------------------------------------------------------------------------- #
def shoot(url, out, w, h):
    subprocess.run([CHROME, '--headless', '--disable-gpu', '--no-sandbox',
                    '--hide-scrollbars', '--force-device-scale-factor=2',
                    # pin the light theme: the slides are designed on warm paper,
                    # and a dark screenshot dropped into them looks like a bug
                    '--blink-settings=preferredColorScheme=1',
                    '--virtual-time-budget=4000', '--window-size=%d,%d' % (w, h),
                    '--screenshot=' + out, url],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def capture_ui():
    """Run the real web UI and crop the two regions the slides embed."""
    env = dict(os.environ, PYTHONPATH=ROOT)
    proc = subprocess.Popen(
        [sys.executable, '-m', 'bilingual_epub.webui', '--no-browser',
         '--port', str(PORT), '--lang', 'zh'],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(5)
        full = os.path.join(HERE, '_full.png')
        shoot('http://127.0.0.1:%d/' % PORT, full, 1400, 1150)
        if not os.path.exists(full):
            raise SystemExit('screenshot failed -- is Chrome at %s ?' % CHROME)
        for name, geom in (('shot-flow.png', '1290x1020+1420+540'),
                           ('shot-drop.png', '1290x760+140+540')):
            subprocess.run(['magick', full, '-crop', geom, '+repage',
                            os.path.join(HERE, name)], check=True)
        os.remove(full)
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def main():
    if not os.path.exists(CHROME):
        raise SystemExit('needs headless Chrome at %s' % CHROME)
    if not shutil.which('magick'):
        raise SystemExit('needs ImageMagick (brew install imagemagick)')
    capture_ui()
    write_slides()
    for name in ('1-cover', '2-translate', '3-reading', '4-how', '5-links'):
        shoot('file://' + os.path.join(HERE, name + '.html'),
              os.path.join(HERE, name + '.png'), 1080, 1440)
        print('  %s.png' % name)
    print('done -> %s' % HERE)


if __name__ == '__main__':
    main()
