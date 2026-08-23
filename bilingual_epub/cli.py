#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI entry point for the generic bilingual-EPUB toolkit.

Three subcommands:
  merge    two monolingual EPUBs (any book, any language pair)  -> one bilingual EPUB
  split    one bilingual (or multi-language) EPUB                -> N monolingual EPUBs
  remerge  one existing bilingual EPUB, re-rendered w/ new options -> a new bilingual EPUB
           (= split then merge again; handy for "I have a bilingual book from
           somewhere else and want it in this tool's tap-to-reveal style", or
           "same book, different blur/opencc settings")

NOTE ON THE OLD Chatter-SPECIFIC SCRIPT: the version of this file that hand-
mapped internal filenames for one specific book (Ethan Kross's *Chatter*) is
kept as legacy_chatter_build.py for exact reproducibility of the original
2026-07-29 output. Everything below is the generalized replacement -- see
README.md for what "generalized" does and doesn't cover.
"""
import argparse
import os
import sys

from . import merge as merge_mod
from . import split as split_mod


def cmd_merge(args):
    out, stats = merge_mod.merge_bilingual(
        a_epub=args.a, b_epub=args.b, out_path=args.out, workdir=args.workdir,
        blur=args.blur, blur_side=args.blur_side, convert_side=args.convert_side,
        cc_config=args.convert, title=args.title,
        authors=args.author.split(';') if args.author else None,
        toggle_label=args.toggle_label)
    _print_stats(stats)
    print('\nwrote', out, os.path.getsize(out) // 1024, 'KB')


def cmd_split(args):
    langs = args.langs.split(',') if args.langs else None
    results = split_mod.split_by_lang(args.input, args.out_dir, langs=langs, workdir=args.workdir)
    if not results:
        print('没有可拆出的内容(读不到任何带语言标记的段落)', file=sys.stderr)
        sys.exit(1)
    for lang, path in results.items():
        print('%-8s -> %s (%d KB)' % (lang, path, os.path.getsize(path) // 1024))


def cmd_remerge(args):
    import tempfile, shutil
    tmp = tempfile.mkdtemp(prefix='remerge_')
    try:
        parts = split_mod.split_by_lang(args.input, os.path.join(tmp, 'parts'), workdir=tmp)
        if len(parts) < 2:
            raise SystemExit('只找到 %d 种语言(%s)，重新合并需要至少 2 种。'
                             % (len(parts), ', '.join(parts) or '无'))
        langs = sorted(parts)
        a_lang = args.a_lang or langs[0]
        b_lang = args.b_lang or (langs[1] if len(langs) > 1 else langs[0])
        if a_lang not in parts or b_lang not in parts:
            raise SystemExit('这本书里找到的语言是 %s，--a-lang/--b-lang 得从里面选。' % ', '.join(langs))
        out, stats = merge_mod.merge_bilingual(
            a_epub=parts[a_lang], b_epub=parts[b_lang], out_path=args.out, workdir=None,
            blur=args.blur, blur_side=args.blur_side, convert_side=args.convert_side,
            cc_config=args.convert, title=args.title,
            authors=args.author.split(';') if args.author else None,
            toggle_label=args.toggle_label)
        _print_stats(stats)
        print('\n(拆出的语言: %s；用了 a=%s, b=%s)' % (', '.join(langs), a_lang, b_lang))
        print('wrote', out, os.path.getsize(out) // 1024, 'KB')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _print_stats(stats):
    print('%-8s %5s %5s | %5s %5s %5s %5s' %
          ('chapter', 'A', 'B', '1:1', 'n:m', 'A-only', 'B-only'))
    for row in stats:
        print('%-8s %5d %5d | %5d %5d %5d %5d' % row)


def main(argv=None):
    p = argparse.ArgumentParser(prog='bilingual-epub', description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)

    pm = sub.add_parser('merge', help='两本单语 EPUB -> 一本双语 EPUB(点按显示)')
    pm.add_argument('--a', required=True, help='A 侧 EPUB 路径(默认不模糊)')
    pm.add_argument('--b', required=True, help='B 侧 EPUB 路径(默认模糊)')
    pm.add_argument('--out', required=True, help='输出 EPUB 路径')
    pm.add_argument('--workdir', default=None, help='中间文件目录，默认用系统临时目录，用完自动清理')
    pm.add_argument('--blur', default='0.25em', help='模糊程度(CSS 长度，建议用 em)，默认 0.25em')
    pm.add_argument('--blur-side', choices=['a', 'b', 'none'], default='b', help='模糊哪一侧，默认 b；none=不模糊')
    pm.add_argument('--convert-side', choices=['a', 'b'], default=None, help='对哪一侧做 opencc 转换(如繁转简)')
    pm.add_argument('--convert', default='none', help='opencc 配置，如 tw2sp/s2t，默认 none(不转换)')
    pm.add_argument('--title', default=None, help='覆盖书名，默认拼接两侧原书名')
    pm.add_argument('--author', default=None, help='覆盖作者(分号分隔多个)，默认合并两侧作者')
    pm.add_argument('--toggle-label', default='Show / Hide translation', help='"全部显示/隐藏"按钮文案')
    pm.set_defaults(func=cmd_merge, blur_side_default=True)

    ps = sub.add_parser('split', help='一本双语/多语 EPUB -> 每种语言各一本单语 EPUB')
    ps.add_argument('--in', dest='input', required=True, help='源 EPUB 路径')
    ps.add_argument('--out-dir', required=True, help='输出目录')
    ps.add_argument('--langs', default=None, help='只拆这些语言(逗号分隔)，默认拆出全部发现的语言')
    ps.add_argument('--workdir', default=None)
    ps.set_defaults(func=cmd_split)

    pr = sub.add_parser('remerge', help='已有双语 EPUB -> 拆开重新合并成新双语 EPUB(换参数/换风格用)')
    pr.add_argument('--in', dest='input', required=True)
    pr.add_argument('--out', required=True)
    pr.add_argument('--a-lang', default=None, help='选哪个语言当 A 侧，默认按发现顺序第一个')
    pr.add_argument('--b-lang', default=None, help='选哪个语言当 B 侧(会被模糊)，默认第二个')
    pr.add_argument('--blur', default='0.25em')
    pr.add_argument('--blur-side', choices=['a', 'b', 'none'], default='b')
    pr.add_argument('--convert-side', choices=['a', 'b'], default=None)
    pr.add_argument('--convert', default='none')
    pr.add_argument('--title', default=None)
    pr.add_argument('--author', default=None)
    pr.add_argument('--toggle-label', default='Show / Hide translation')
    pr.set_defaults(func=cmd_remerge)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    main()
