#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交互式终端向导 —— 不用记参数，跑起来一步步问。

    python3 tui.py

选操作 → 填路径 → 选选项 → 干活。路径支持直接把文件拖进终端（自动去掉
拖拽产生的引号和转义空格），支持 ~ 展开，回车用默认值。
"""
import os
import sys

from . import merge as merge_mod
from . import split as split_mod

# ANSI 颜色；管道输出（不是终端）时自动关掉，免得日志里全是乱码
_TTY = sys.stdout.isatty()


def _c(code, s):
    return '\033[%sm%s\033[0m' % (code, s) if _TTY else s


def bold(s):    return _c('1', s)
def dim(s):     return _c('2', s)
def green(s):   return _c('32', s)
def red(s):     return _c('31', s)
def cyan(s):    return _c('36', s)
def yellow(s):  return _c('33', s)


def clean_path(raw):
    """把用户输入/拖拽进来的路径洗干净。

    终端拖文件会产生 '/path/with\\ space.epub' 或带引号的形式；这里统一处理
    掉引号、反斜杠转义的空格、首尾空白，再展开 ~。
    """
    s = (raw or '').strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1]
    s = s.replace('\\ ', ' ').replace('\\~', '~').strip()
    return os.path.expanduser(s)


def ask(prompt, default=None, required=True, is_path=False, must_exist=False):
    """问一个问题，直到拿到合法答案。Ctrl-C / Ctrl-D 干净退出。"""
    hint = dim(' [%s]' % default) if default else ''
    while True:
        try:
            raw = input('%s%s: ' % (cyan(prompt), hint)).strip()
        except (EOFError, KeyboardInterrupt):
            print('\n' + dim('已取消。'))
            sys.exit(130)
        if not raw and default is not None:
            raw = default
        if not raw:
            if not required:
                return ''
            print(red('  这项必填。'))
            continue
        if is_path:
            raw = clean_path(raw)
            if must_exist and not os.path.exists(raw):
                print(red('  找不到这个文件：%s' % raw))
                continue
        return raw


def choose(prompt, options, default_idx=0):
    """options: [(value, label, help_text)]，返回选中的 value。"""
    print('\n' + bold(prompt))
    for i, (_v, label, help_text) in enumerate(options, 1):
        mark = dim('(默认)') if i - 1 == default_idx else ''
        print('  %s. %s %s' % (bold(str(i)), label, mark))
        if help_text:
            print('     ' + dim(help_text))
    while True:
        try:
            raw = input(cyan('选择 [1-%d]: ' % len(options))).strip()
        except (EOFError, KeyboardInterrupt):
            print('\n' + dim('已取消。'))
            sys.exit(130)
        if not raw:
            return options[default_idx][0]
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        print(red('  请输入 1 到 %d 之间的数字。' % len(options)))


def confirm(prompt, default=True):
    d = 'Y/n' if default else 'y/N'
    while True:
        try:
            raw = input('%s %s: ' % (cyan(prompt), dim('[%s]' % d))).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print('\n' + dim('已取消。'))
            sys.exit(130)
        if not raw:
            return default
        if raw in ('y', 'yes', '是'):
            return True
        if raw in ('n', 'no', '否'):
            return False


def print_stats(stats):
    if not stats:
        return
    print('\n' + bold('%-8s %5s %5s | %5s %5s %6s %6s'
                      % ('章节', 'A段', 'B段', '1:1', 'n:m', '仅A', '仅B')))
    for row in stats:
        print('%-8s %5d %5d | %5d %5d %6d %6d' % row)
    tot_11 = sum(r[3] for r in stats)
    tot_all = sum(r[3] + r[4] + r[5] + r[6] for r in stats)
    if tot_all:
        pct = 100.0 * tot_11 / tot_all
        note = '对齐质量看这个数：越高说明两个版本的段落越是干净的一一对应。'
        print(dim('\n1:1 干净配对占比 %.1f%%（%d / %d）\n%s' % (pct, tot_11, tot_all, note)))


def ask_blur_opts():
    blur_side = choose('模糊哪一侧？（默认模糊的那侧就是"点一下才显示"的译文）', [
        ('b', 'B 侧', 'B 侧默认糊住，点按显示 —— 最常见：A=原文，B=译文'),
        ('a', 'A 侧', '反过来，A 侧糊住'),
        ('none', '都不模糊', '纯左右对照，不做点按效果'),
    ], default_idx=0)
    blur = '0.25em'
    if blur_side != 'none':
        blur = ask('模糊程度（CSS 长度，建议用 em，跟随字号缩放）', default='0.25em')
    return blur_side, blur


def ask_convert_opts():
    if not confirm('\n需要做 opencc 中文转换吗（比如繁体转简体）？', default=False):
        return None, 'none'
    side = choose('对哪一侧做转换？', [
        ('b', 'B 侧', ''),
        ('a', 'A 侧', ''),
    ], default_idx=0)
    cfg = choose('转换方式？', [
        ('tw2sp', 'tw2sp', '台湾繁体 → 简体，连词汇一起转（資訊→信息、網路→网络）'),
        ('t2s', 't2s', '繁体 → 简体，只转字形'),
        ('s2t', 's2t', '简体 → 繁体'),
        ('s2tw', 's2tw', '简体 → 台湾繁体'),
    ], default_idx=0)
    return side, cfg


def flow_merge():
    print(bold('\n=== 合并：两本单语 EPUB → 一本双语 EPUB ===\n'))
    print(dim('提示：可以直接把文件从访达拖进终端窗口，路径会自动填好。\n'))
    a = ask('A 侧 EPUB（通常是原文）', is_path=True, must_exist=True)
    b = ask('B 侧 EPUB（通常是译文）', is_path=True, must_exist=True)
    default_out = os.path.join(os.path.dirname(a) or '.', 'bilingual.epub')
    out = ask('输出到哪', default=default_out, is_path=True)
    blur_side, blur = ask_blur_opts()
    convert_side, cc = ask_convert_opts()
    title = ask('书名（回车=自动拼接两本原书名）', required=False)

    print(dim('\n处理中……大部头的书对齐要花点时间，别急。\n'))
    out_path, stats = merge_mod.merge_bilingual(
        a_epub=a, b_epub=b, out_path=out, blur=blur, blur_side=blur_side,
        convert_side=convert_side, cc_config=cc, title=title or None)
    print_stats(stats)
    print(green('\n✅ 完成：%s（%d KB）' % (out_path, os.path.getsize(out_path) // 1024)))
    return out_path


def flow_split():
    print(bold('\n=== 拆分：一本双语 EPUB → 每种语言各一本 ===\n'))
    src = ask('要拆的 EPUB', is_path=True, must_exist=True)
    default_dir = os.path.join(os.path.dirname(src) or '.', 'split_out')
    out_dir = ask('输出目录', default=default_dir, is_path=True)
    langs_raw = ask('只要某几种语言？逗号分隔，回车=全部拆出', required=False)
    langs = [s.strip() for s in langs_raw.split(',') if s.strip()] or None

    print(dim('\n处理中……\n'))
    results = split_mod.split_by_lang(src, out_dir, langs=langs)
    if not results:
        print(red('没拆出东西 —— 这本书大概没有逐段标注语言（见 README 的已知限制）。'))
        return None
    print(green('✅ 拆出 %d 种语言：' % len(results)))
    for lang, path in results.items():
        print('   %-8s %s（%d KB）' % (lang, path, os.path.getsize(path) // 1024))
    return out_dir


def flow_remerge():
    import shutil
    import tempfile
    print(bold('\n=== 重新合并：已有双语 EPUB → 换参数生成新版 ===\n'))
    print(dim('用途：手上的双语书想换模糊程度、换糊哪一侧，或把别处来的双语书\n'
              '收编成这个工具的点按显示风格。内部是先拆再合，你不用手动做两步。\n'))
    src = ask('源双语 EPUB', is_path=True, must_exist=True)
    default_out = os.path.join(os.path.dirname(src) or '.', 'remerged.epub')
    out = ask('输出到哪', default=default_out, is_path=True)

    tmp = tempfile.mkdtemp(prefix='remerge_')
    try:
        print(dim('\n先拆开看看里面有哪些语言……'))
        parts = split_mod.split_by_lang(src, os.path.join(tmp, 'parts'), workdir=tmp)
        langs = sorted(parts)
        if len(langs) < 2:
            print(red('只找到 %d 种语言（%s），重新合并至少要 2 种。'
                      % (len(langs), ', '.join(langs) or '无')))
            print(dim('多半是这本书没有逐段标注语言 —— 见 README 的已知限制。'))
            return None
        print(green('找到：%s' % ', '.join(langs)))
        a_lang = choose('哪个语言当 A 侧（默认不模糊的那侧）？',
                        [(l, l, '') for l in langs], default_idx=0)
        rest = [l for l in langs if l != a_lang]
        b_lang = choose('哪个语言当 B 侧？',
                        [(l, l, '') for l in rest], default_idx=0)
        blur_side, blur = ask_blur_opts()

        print(dim('\n重新合并中……\n'))
        out_path, stats = merge_mod.merge_bilingual(
            a_epub=parts[a_lang], b_epub=parts[b_lang], out_path=out,
            blur=blur, blur_side=blur_side)
        print_stats(stats)
        print(green('\n✅ 完成：%s（%d KB）' % (out_path, os.path.getsize(out_path) // 1024)))
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print(bold('\n📖  双语 EPUB 工具箱'))
    print(dim('任意标准 EPUB 都能处理（DRM 加密的除外）。Ctrl-C 随时退出。'))

    while True:
        action = choose('\n要做什么？', [
            ('merge',   '合并 —— 两本单语书 → 一本双语书',
             '英文一段、中文一段，译文默认糊住，点一下显示'),
            ('split',   '拆分 —— 一本双语书 → 每种语言各一本', ''),
            ('remerge', '重新合并 —— 已有双语书换个参数/换个风格', ''),
            ('quit',    '退出', ''),
        ], default_idx=0)

        if action == 'quit':
            print(dim('再见。'))
            return 0

        try:
            {'merge': flow_merge, 'split': flow_split, 'remerge': flow_remerge}[action]()
        except SystemExit as e:
            # 引擎里用 SystemExit 抛的都是"能看懂的人话错误"（文件不存在、
            # 不是合法 EPUB、读不到正文……），不该直接把向导也带崩
            if isinstance(e.code, str):
                print(red('\n❌ %s' % e.code))
            else:
                raise
        except Exception as ex:
            print(red('\n❌ 出错了：%s: %s' % (type(ex).__name__, ex)))
            print(dim('要看完整报错，用 python3 build.py 跑命令行版本。'))

        if not confirm('\n还要做点别的吗？', default=False):
            print(dim('再见。'))
            return 0


if __name__ == '__main__':
    sys.exit(main())
