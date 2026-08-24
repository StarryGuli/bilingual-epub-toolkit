"""Bilingual (English / Chinese) interface strings.

The engine is language-agnostic, but everything a person actually reads --
the terminal wizard, the CLI help, the local web page -- exists in both
English and Chinese. The language is picked once at startup:

1. an explicit ``--lang en|zh``
2. otherwise ``BILINGUAL_EPUB_LANG`` if it is set
3. otherwise the system locale (``LC_ALL`` / ``LC_MESSAGES`` / ``LANG``);
   anything that looks Chinese selects Chinese
4. otherwise English

English is the fallback rather than Chinese so that someone who installs
this from PyPI without any Chinese locale gets an interface they can read.
"""
import os

_LANG = None

#: key -> (english, chinese)
STRINGS = {
    # ---- shared ---------------------------------------------------------
    'app.name':          ('Bilingual EPUB Toolkit', '双语 EPUB 工具箱'),
    'app.tagline':       ('Merge two monolingual EPUBs into one tap-to-reveal '
                          'bilingual book -- or split one back apart.',
                          '两本单语书合成一本点按显示的对照书，也能反过来拆开。'),
    'app.any_epub':      ('Works with any standard EPUB. DRM-protected files '
                          'cannot be read.',
                          '任意标准 EPUB 都能处理，DRM 加密的除外。'),
    'app.local_only':    ('Serving on 127.0.0.1', '监听 127.0.0.1'),

    # ---- prompts / validation -------------------------------------------
    'ui.cancelled':      ('Cancelled.', '已取消。'),
    'ui.required':       ('  This one is required.', '  这项必填。'),
    'ui.not_found':      ('  No such file: %s', '  找不到这个文件：%s'),
    'ui.default':        ('(default)', '(默认)'),
    'ui.pick':           ('Pick [1-%d]: ', '选择 [1-%d]: '),
    'ui.pick_range':     ('  Enter a number from 1 to %d.', '  请输入 1 到 %d 之间的数字。'),
    'ui.working':        ('\nWorking...\n', '\n处理中……\n'),
    'ui.working_long':   ('\nWorking... aligning a long book takes a moment.\n',
                          '\n处理中……大部头的书对齐要花点时间，别急。\n'),
    'ui.done':           ('\nDone: %s (%d KB)', '\n完成：%s（%d KB）'),
    'ui.bye':            ('Bye.', '再见。'),
    'ui.anything_else':  ('\nAnything else?', '\n还要做点别的吗？'),
    'ui.quit_hint':      ('Ctrl-C quits at any time.', 'Ctrl-C 随时退出。'),
    'ui.drag_hint':      ('Tip: drag a file from Finder straight into this '
                          'window and the path fills itself in.\n',
                          '提示：可以直接把文件从访达拖进终端窗口，路径会自动填好。\n'),
    'ui.error':          ('\nError: %s', '\n出错了：%s'),
    'ui.error_detail':   ('For the full traceback, run the CLI: bilingual-epub',
                          '要看完整报错，用命令行版本：bilingual-epub'),

    # ---- menu ------------------------------------------------------------
    'menu.what':         ('\nWhat would you like to do?', '\n要做什么？'),
    'menu.merge':        ('Merge -- two monolingual books into one bilingual book',
                          '合并 —— 两本单语书 → 一本双语书'),
    'menu.merge.help':   ('One paragraph of each, translation blurred until tapped',
                          '一段原文一段译文，译文默认糊住，点一下显示'),
    'menu.split':        ('Split -- one bilingual book into one book per language',
                          '拆分 —— 一本双语书 → 每种语言各一本'),
    'menu.remerge':      ('Remerge -- rebuild an existing bilingual book with new options',
                          '重新合并 —— 已有双语书换个参数/换个风格'),
    'menu.quit':         ('Quit', '退出'),

    # ---- merge -----------------------------------------------------------
    'merge.title':       ('\n=== Merge: two monolingual EPUBs into one bilingual EPUB ===\n',
                          '\n=== 合并：两本单语 EPUB → 一本双语 EPUB ===\n'),
    'merge.a':           ('A-side EPUB (usually the original)', 'A 侧 EPUB（通常是原文）'),
    'merge.b':           ('B-side EPUB (usually the translation)', 'B 侧 EPUB（通常是译文）'),
    'merge.out':         ('Write the result where', '输出到哪'),
    'merge.book_title':  ('Book title (blank = join both original titles)',
                          '书名（回车=自动拼接两本原书名）'),

    # ---- split -----------------------------------------------------------
    'split.title':       ('\n=== Split: one bilingual EPUB into one book per language ===\n',
                          '\n=== 拆分：一本双语 EPUB → 每种语言各一本 ===\n'),
    'split.src':         ('EPUB to split', '要拆的 EPUB'),
    'split.outdir':      ('Output directory', '输出目录'),
    'split.langs':       ('Only these languages? comma-separated, blank = all',
                          '只要某几种语言？逗号分隔，回车=全部拆出'),
    'split.none':        ('Nothing came out -- this book probably does not tag '
                          'language per paragraph (see Known limits in the README).',
                          '没拆出东西 —— 这本书大概没有逐段标注语言（见 README 的已知限制）。'),
    'split.ok':          ('Split into %d languages:', '拆出 %d 种语言：'),

    # ---- remerge ---------------------------------------------------------
    'remerge.title':     ('\n=== Remerge: rebuild an existing bilingual EPUB ===\n',
                          '\n=== 重新合并：已有双语 EPUB → 换参数生成新版 ===\n'),
    'remerge.why':       ('For changing the blur, flipping which side is hidden, or '
                          'converting a bilingual book from elsewhere into this\n'
                          'tool\'s tap-to-reveal style. It splits then merges for you.\n',
                          '用途：手上的双语书想换模糊程度、换糊哪一侧，或把别处来的双语书\n'
                          '收编成这个工具的点按显示风格。内部是先拆再合，你不用手动做两步。\n'),
    'remerge.src':       ('Source bilingual EPUB', '源双语 EPUB'),
    'remerge.peek':      ('\nOpening it up to see which languages are inside...',
                          '\n先拆开看看里面有哪些语言……'),
    'remerge.too_few':   ('Only found %d language (%s); remerging needs at least 2.',
                          '只找到 %d 种语言（%s），重新合并至少要 2 种。'),
    'remerge.too_few_hint': ('Most likely this book does not tag language per '
                             'paragraph -- see Known limits in the README.',
                             '多半是这本书没有逐段标注语言 —— 见 README 的已知限制。'),
    'remerge.found':     ('Found: %s', '找到：%s'),
    'remerge.pick_a':    ('Which language is the A side (the one left unblurred)?',
                          '哪个语言当 A 侧（默认不模糊的那侧）？'),
    'remerge.pick_b':    ('Which language is the B side?', '哪个语言当 B 侧？'),

    # ---- blur options ----------------------------------------------------
    'blur.enable':       ('Hide one side until it is tapped?',
                          '要不要「点一下才显示」的效果？'),
    'blur.enable.help':  ('Off gives plain facing text with nothing hidden.',
                          '关掉就是纯对照排版，什么都不糊。'),
    'blur.which':        ('Which side gets hidden? (the hidden side is the one '
                          'you tap to reveal)',
                          '糊住哪一侧？（糊住的那侧就是"点一下才显示"的）'),
    'blur.b':            ('B side', 'B 侧'),
    'blur.b.help':       ('B is hidden until tapped -- the usual choice: A original, '
                          'B translation',
                          'B 侧默认糊住，点按显示 —— 最常见：A=原文，B=译文'),
    'blur.a':            ('A side', 'A 侧'),
    'blur.a.help':       ('The other way round, A is hidden', '反过来，A 侧糊住'),
    'blur.none':         ('Neither', '都不模糊'),
    'blur.none.help':    ('Plain side-by-side, no tap-to-reveal', '纯左右对照，不做点按效果'),
    'blur.amount':       ('Blur amount (a CSS length; em scales with the font)',
                          '模糊程度（CSS 长度，建议用 em，跟随字号缩放）'),

    # ---- opencc ----------------------------------------------------------
    'cc.ask':            ('\nApply an opencc Chinese conversion (e.g. Traditional '
                          'to Simplified)?',
                          '\n需要做 opencc 中文转换吗（比如繁体转简体）？'),
    'cc.side':           ('Convert which side?', '对哪一侧做转换？'),
    'cc.how':            ('Which conversion?', '转换方式？'),
    'cc.tw2sp':          ('Taiwan Traditional to Simplified, including vocabulary',
                          '台湾繁体 → 简体，连词汇一起转（資訊→信息、網路→网络）'),
    'cc.t2s':            ('Traditional to Simplified, characters only',
                          '繁体 → 简体，只转字形'),
    'cc.s2t':            ('Simplified to Traditional', '简体 → 繁体'),
    'cc.s2tw':           ('Simplified to Taiwan Traditional', '简体 → 台湾繁体'),

    # ---- stats -----------------------------------------------------------
    'stats.chapter':     ('chapter', '章节'),
    'stats.a':           ('A', 'A段'),
    'stats.b':           ('B', 'B段'),
    'stats.a_only':      ('A-only', '仅A'),
    'stats.b_only':      ('B-only', '仅B'),
    'stats.ratio':       ('\nClean 1:1 pairing: %.1f%% (%d / %d)\n%s',
                          '\n1:1 干净配对占比 %.1f%%（%d / %d）\n%s'),
    'stats.ratio_note':  ('This is the alignment quality: the higher it is, the more '
                          'cleanly the two editions correspond paragraph by paragraph.',
                          '对齐质量看这个数：越高说明两个版本的段落越是干净的一一对应。'),

    # ---- CLI help --------------------------------------------------------
    'cli.merge':         ('two monolingual EPUBs -> one bilingual EPUB (tap to reveal)',
                          '两本单语 EPUB → 一本双语 EPUB（点按显示）'),
    'cli.split':         ('one bilingual/multilingual EPUB -> one EPUB per language',
                          '一本双语/多语 EPUB → 每种语言各一本单语 EPUB'),
    'cli.remerge':       ('an existing bilingual EPUB -> a new one with different options',
                          '已有双语 EPUB → 拆开重新合并成新双语 EPUB（换参数/换风格用）'),
    'cli.blur':          ('blur amount as a CSS length; em is recommended. Default 0.25em',
                          '模糊程度（CSS 长度，建议用 em），默认 0.25em'),
    'cli.blur_side':     ('which side to hide. Default b; none = nothing hidden',
                          '糊住哪一侧，默认 b；none=都不糊'),
    'cli.no_blur':       ('plain facing text, nothing hidden -- the same as '
                          '--blur-side none',
                          '纯对照排版，什么都不糊 —— 等同 --blur-side none'),
    'cli.workdir':       ('scratch directory; defaults to a temp dir, cleaned up after',
                          '中间文件目录，默认用系统临时目录，用完自动清理'),
    'cli.toggle_label':  ('text for the show/hide-all button inside the book',
                          '书里"全部显示/隐藏"按钮的文案'),
    'cli.lang':          ('interface language for messages and help',
                          '界面语言'),
    'cli.web_desc':      ('local web interface for the bilingual EPUB toolkit',
                          '双语 EPUB 工具箱的本地网页界面'),
    'cli.web_port':      ('port, default %d', '端口，默认 %d'),
    'cli.web_nobrowser': ('do not open a browser automatically', '不要自动打开浏览器'),
    'cli.a':             ('A-side EPUB (left unblurred by default)',
                          'A 侧 EPUB 路径（默认不模糊）'),
    'cli.b':             ('B-side EPUB (blurred by default)',
                          'B 侧 EPUB 路径（默认模糊）'),
    'cli.out':           ('output EPUB path', '输出 EPUB 路径'),
    'cli.convert_side':  ('run an opencc conversion on this side',
                          '对哪一侧做 opencc 转换（如繁转简）'),
    'cli.convert':       ('opencc config, e.g. tw2sp or s2t. Default none',
                          'opencc 配置，如 tw2sp/s2t，默认 none（不转换）'),
    'cli.title':         ('override the book title; default joins both originals',
                          '覆盖书名，默认拼接两侧原书名'),
    'cli.author':        ('override the author (semicolon-separated); default merges both',
                          '覆盖作者（分号分隔多个），默认合并两侧作者'),
    'cli.in':            ('source EPUB path', '源 EPUB 路径'),
    'cli.out_dir':       ('output directory', '输出目录'),
    'cli.langs':         ('only split out these languages (comma-separated); '
                          'default is every language found',
                          '只拆这些语言（逗号分隔），默认拆出全部发现的语言'),
    'cli.a_lang':        ('which language becomes the A side; default is the first found',
                          '选哪个语言当 A 侧，默认按发现顺序第一个'),
    'cli.b_lang':        ('which language becomes the B side (the blurred one); '
                          'default is the second',
                          '选哪个语言当 B 侧（会被模糊），默认第二个'),
    'cli.wrote':         ('\nwrote %s (%d KB)', '\n已写出 %s（%d KB）'),
    'cli.split_none':    ('Nothing to split out: no language-tagged paragraphs found.',
                          '没有可拆出的内容（读不到任何带语言标记的段落）。'),
    'cli.too_few':       ('Only found %d language (%s); remerging needs at least 2.',
                          '只找到 %d 种语言（%s），重新合并需要至少 2 种。'),
    'cli.pick_from':     ('The languages in this book are %s -- --a-lang/--b-lang '
                          'must come from that list.',
                          '这本书里找到的语言是 %s，--a-lang/--b-lang 得从里面选。'),
    'cli.used':          ('\n(languages found: %s; used a=%s, b=%s)',
                          '\n（拆出的语言：%s；用了 a=%s, b=%s）'),

    # ---- web UI ----------------------------------------------------------
    'web.tab.merge':     ('Merge', '合并'),
    'web.tab.split':     ('Split', '拆分'),
    'web.tab.remerge':   ('Remerge', '重新合并'),
    'web.switch':        ('中文', 'English'),
    'web.merge.lead':    ('Two monolingual EPUBs become one facing-text book: a '
                          'paragraph from A, the matching paragraph from B right '
                          'below it, blurred until you tap it.',
                          '两本单语 EPUB 合成一本对照书：A 侧一段，B 侧对应的一段紧跟在'
                          '下面，默认糊住，点一下显示。'),
    'web.split.lead':    ('Split a bilingual (or multilingual) EPUB by language, one '
                          'book per language. Which paragraph belongs where is read '
                          'from each block\'s lang attribute.',
                          '把一本双语（或多语）EPUB 按语言拆开，每种语言各出一本单语书。'
                          '靠每段的 lang 属性判断归属。'),
    'web.remerge.lead':  ('Already have a bilingual book and want a different blur, '
                          'the other side hidden, or a book from elsewhere restyled '
                          'into this tool\'s tap-to-reveal form? Split then merge, in '
                          'one step.',
                          '已经有一本双语书，想换个模糊程度、换糊哪一侧，或者把别处来的'
                          '双语书转成这个工具的点按显示风格——先拆再合，这里一步完成。'),
    'web.side.a':        ('A side (original)', 'A 侧（原文）'),
    'web.side.b':        ('B side (translation)', 'B 侧（译文）'),
    'web.drop':          ('Drop an EPUB here', '拖一本 EPUB 到这里'),
    'web.drop.sub':      ('or click to choose', '或点击选择'),
    'web.drop.or_path':  ('or give a path on this machine', '或填本机路径'),
    'web.uploaded':      ('will be uploaded to the local server', '会上传到本机服务器'),
    'web.clear':         ('Clear the selected file', '清除所选文件'),
    'web.tap.enable':    ('Tap to reveal', '点按显示'),
    'web.tap.help':      ('Blur one side until the reader taps it. Turn this off '
                          'for plain facing text with nothing hidden.',
                          '把一侧糊住，读者点一下才显示。不需要就关掉，'
                          '出来是纯对照排版。'),
    'web.blur.which':    ('Hide which side', '糊住哪一侧'),
    'web.blur.b':        ('B side (translation)', 'B 侧（译文）'),
    'web.blur.a':        ('A side (original)', 'A 侧（原文）'),
    'web.blur.none':     ('Neither', '都不模糊'),
    'web.blur.amount':   ('Blur amount', '模糊程度'),
    'web.blur.hint':     ('A CSS length; em scales with the font size',
                          'CSS 长度，建议用 em，会跟随字号缩放'),
    'web.preview':       ('Preview', '效果预览'),
    'web.cc.label':      ('opencc conversion (optional)', 'opencc 转换（可选）'),
    'web.cc.none':       ('No conversion', '不转换'),
    'web.cc.a':          ('Convert the A side', '转换 A 侧'),
    'web.cc.b':          ('Convert the B side', '转换 B 侧'),
    'web.cc.hint':       ('Chinese script conversion; needs opencc installed',
                          '中文繁简转换，需装 opencc'),
    'web.cc.cfg':        ('opencc config', 'opencc 配置'),
    'web.cc.cfg_hint':   ('e.g. tw2sp for Traditional to Simplified',
                          '例：tw2sp 繁转简'),
    'web.title':         ('Book title (optional)', '书名（可选）'),
    'web.title.ph':      ('blank = join both original titles', '留空则自动拼接两侧书名'),
    'web.go.merge':      ('Merge into a facing-text book', '合并成对照书'),
    'web.go.split':      ('Split', '拆分'),
    'web.go.remerge':    ('Remerge', '重新合并'),
    'web.src':           ('Source EPUB', '源 EPUB'),
    'web.src.bi':        ('Source bilingual EPUB', '源双语 EPUB'),
    'web.drop.bi':       ('Drop a bilingual EPUB here', '拖一本双语 EPUB 到这里'),
    'web.langs':         ('Only these languages (optional)', '只拆这些语言（可选）'),
    'web.langs.hint':    ('Comma-separated; blank means every language found',
                          '逗号分隔；留空则拆出全部识别到的语言'),
    'web.alang':         ('A-side language code', 'A 侧语言代码'),
    'web.alang.hint':    ('blank = the first one found', '留空＝取识别到的第一种'),
    'web.blang':         ('B-side language code', 'B 侧语言代码'),
    'web.blang.hint':    ('blank = the second one', '留空＝取第二种'),
    'web.footer':        ('Works with any standard EPUB, DRM-protected files aside. '
                          'Press Ctrl+C in the terminal that started it to stop.',
                          '任意标准 EPUB 都能处理，DRM 加密的除外。'
                          '用完在启动它的终端窗口按 Ctrl+C 停止。'),
    # result rendering (used by the page's JS)
    'web.res.chapter':   ('chapter', '章节'),
    'web.res.a':         ('A', 'A 段'),
    'web.res.b':         ('B', 'B 段'),
    'web.res.a_only':    ('A only', '仅 A'),
    'web.res.b_only':    ('B only', '仅 B'),
    'web.res.failed':    ('Could not finish', '没能完成'),
    'web.res.reqfail':   ('Request failed', '请求失败'),
    # server-side operation results
    'web.ok.merge':      ('Merged', '合并完成'),
    'web.ok.remerge':    ('Remerged', '重新合并完成'),
    'web.ok.split':      ('Split into %d languages: %s', '拆出 %d 种语言：%s'),
    'web.found_langs':   ('Languages found: %s (A=%s, B=%s)',
                          '识别到的语言：%s（A=%s，B=%s）'),
    'web.need_file':     ('%s: drop an EPUB in, or give a path on this machine.',
                          '%s：请拖一个 EPUB 进来，或者填一个本机路径。'),
    'web.no_such':       ('%s: no such file -- %s', '%s：找不到这个文件 —— %s'),
    'web.too_big':       ('That file is too large (limit %d MB).',
                          '文件太大了（上限 %d MB）。'),
    'web.pick_from':     ('The languages in this book are %s -- A and B must come '
                          'from that list.',
                          '这本书里识别到的语言是：%s —— A/B 必须从里面选。'),
    'web.pv.sources':    ('goes in', '放进去的'),
    'web.pv.result':     ('comes out', '出来的'),
    'web.pv.merge':      ('merge', '合并'),
    'web.pv.split':      ('split', '拆分'),
    'web.pv.remerge':    ('remerge', '重新合并'),
    'web.pv.tap':        ('click a blurred line to reveal it — the finished book '
                          'behaves the same way',
                          '点一下糊住的那行就会显示 —— 做出来的书就是这个行为'),
    'web.pv.download':   ('download', '下载'),
    'web.crashed':       ('Something went wrong handling that file. The details '
                          'are in the terminal running this server.',
                          '处理这个文件时出错了。详细报错在跑这个服务的终端窗口里。'),
    'web.no_session':    ('Your session expired. Reload the page and try again.',
                          '会话已过期，刷新页面重试。'),
    'web.stale_page':    ('This page is out of date. Reload it and try again.',
                          '这个页面已经过期了，刷新一下重试。'),
    'web.slow_down':     ('Too many jobs from your address. Try again in about '
                          '%d seconds.',
                          '你这个地址提交得太频繁了，大约 %d 秒后再试。'),
    'web.quota':         ('You have hit this session\'s file limit. Reload the page '
                          'to start a fresh one.',
                          '这个会话的文件数或体积到上限了，刷新页面重开一个。'),
    'web.no_paths':      ('This server does not accept server-side paths. Upload the '
                          'file instead.',
                          '这个服务器不接受填路径，请直接把文件传上来。'),
    'web.public_note':   ('Uploads are deleted automatically after a while, and only '
                          'you can download what you made.',
                          '上传的文件过一阵会自动删除；你做出来的东西也只有你能下载。'),
    'web.pv.real':       ('These are real files, built by the same code the buttons '
                          'below use. Download any of them and open it in a reader.',
                          '这三个是真文件，跟下面按钮走的是同一套代码。'
                          '点下载就能拿到，直接扔进阅读器就能看。'),
    'web.pv.live':       ('This is the sample pair in examples/ -- the blur below '
                          'follows the settings on the left.',
                          '这就是 examples/ 里那两本示例书；下面的模糊程度跟着左边的'
                          '设置实时变化。'),
    'web.pv.static':     ('This is the sample pair in examples/.',
                          '这就是 examples/ 里那两本示例书。'),
    'web.busy_ports':    ('Ports %d-%d are all taken; pick another with --port.',
                          '端口 %d~%d 都被占用了，用 --port 指定一个别的。'),
    'web.moved_port':    ('(%d was busy, using %d instead)', '（%d 被占用了，改用 %d）'),
    'web.open_hint':     ('  Your browser should open on its own; if not, paste the '
                          'address above into it.',
                          '  浏览器应该会自动打开；没有的话手动把上面这行地址复制进去。'),
    'web.stop_hint':     ('  Press Ctrl+C in this window when you are done.\n',
                          '  用完在这个窗口按 Ctrl+C 关掉。\n'),
    'web.stopped':       ('\nStopped.', '\n已停止。'),
}


def _detect():
    explicit = os.environ.get('BILINGUAL_EPUB_LANG', '').strip().lower()
    if explicit.startswith('zh'):
        return 'zh'
    if explicit.startswith('en'):
        return 'en'
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        val = os.environ.get(var, '')
        if val:
            low = val.lower()
            if low.startswith('zh') or 'hans' in low or 'hant' in low:
                return 'zh'
            return 'en'
    return 'en'


def set_lang(lang):
    """Force the interface language; None re-runs auto-detection."""
    global _LANG
    _LANG = lang if lang in ('en', 'zh') else None


def get_lang():
    global _LANG
    if _LANG is None:
        _LANG = _detect()
    return _LANG


def t(key, *args):
    """Look up a string in the current language and %-format it."""
    pair = STRINGS.get(key)
    if pair is None:
        return key
    text = pair[1] if get_lang() == 'zh' else pair[0]
    return text % args if args else text
