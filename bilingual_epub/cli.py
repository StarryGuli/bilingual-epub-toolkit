#!/usr/bin/env python3
"""CLI entry point for the generic bilingual-EPUB toolkit.

Three subcommands:
  merge    two monolingual EPUBs (any book, any language pair)  -> one bilingual EPUB
  split    one bilingual (or multi-language) EPUB                -> N monolingual EPUBs
  remerge  one existing bilingual EPUB, re-rendered w/ new options -> a new bilingual EPUB
           (= split then merge again; handy for "I have a bilingual book from
           somewhere else and want it in this tool's tap-to-reveal style", or
           "same book, different blur/opencc settings")

Messages and help are English or Chinese, following the system locale;
override with --lang or BILINGUAL_EPUB_LANG.
"""
import argparse
import os
import sys

from . import merge as merge_mod
from . import split as split_mod
from .i18n import set_lang, t


def cmd_merge(args):
    out, stats = merge_mod.merge_bilingual(
        a_epub=args.a, b_epub=args.b, out_path=args.out, workdir=args.workdir,
        blur=args.blur, blur_side=args.blur_side, convert_side=args.convert_side,
        cc_config=args.convert, title=args.title,
        authors=args.author.split(';') if args.author else None,
        toggle_label=args.toggle_label)
    _print_stats(stats)
    print(t('cli.wrote', out, os.path.getsize(out) // 1024))


def cmd_split(args):
    langs = args.langs.split(',') if args.langs else None
    results = split_mod.split_by_lang(args.input, args.out_dir, langs=langs, workdir=args.workdir)
    if not results:
        print(t('cli.split_none'), file=sys.stderr)
        sys.exit(1)
    for lang, path in results.items():
        print('%-8s -> %s (%d KB)' % (lang, path, os.path.getsize(path) // 1024))


def cmd_remerge(args):
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix='remerge_')
    try:
        parts = split_mod.split_by_lang(args.input, os.path.join(tmp, 'parts'), workdir=tmp)
        if len(parts) < 2:
            raise SystemExit(t('cli.too_few', len(parts), ', '.join(parts) or '-'))
        langs = sorted(parts)
        a_lang = args.a_lang or langs[0]
        b_lang = args.b_lang or (langs[1] if len(langs) > 1 else langs[0])
        if a_lang not in parts or b_lang not in parts:
            raise SystemExit(t('cli.pick_from', ', '.join(langs)))
        out, stats = merge_mod.merge_bilingual(
            a_epub=parts[a_lang], b_epub=parts[b_lang], out_path=args.out, workdir=None,
            blur=args.blur, blur_side=args.blur_side, convert_side=args.convert_side,
            cc_config=args.convert, title=args.title,
            authors=args.author.split(';') if args.author else None,
            toggle_label=args.toggle_label)
        _print_stats(stats)
        print(t('cli.used', ', '.join(langs), a_lang, b_lang))
        print(t('cli.wrote', out, os.path.getsize(out) // 1024))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _print_stats(stats):
    print('%-8s %5s %5s | %5s %5s %6s %6s' %
          (t('stats.chapter'), t('stats.a'), t('stats.b'), '1:1', 'n:m',
           t('stats.a_only'), t('stats.b_only')))
    for row in stats:
        print('%-8s %5d %5d | %5d %5d %6d %6d' % row)


def main(argv=None):
    # --lang has to be honoured before the parser is built, because argparse
    # bakes the help text in at construction time.
    raw = list(sys.argv[1:] if argv is None else argv)
    for i, tok in enumerate(raw):
        if tok == '--lang' and i + 1 < len(raw):
            set_lang(raw[i + 1])
        elif tok.startswith('--lang='):
            set_lang(tok.split('=', 1)[1])

    p = argparse.ArgumentParser(prog='bilingual-epub', description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--lang', choices=['en', 'zh'], default=None, help=t('cli.lang'))
    sub = p.add_subparsers(dest='cmd', required=True)

    pm = sub.add_parser('merge', help=t('cli.merge'))
    pm.add_argument('--a', required=True, help=t('cli.a'))
    pm.add_argument('--b', required=True, help=t('cli.b'))
    pm.add_argument('--out', required=True, help=t('cli.out'))
    pm.add_argument('--workdir', default=None, help=t('cli.workdir'))
    pm.add_argument('--blur', default='0.25em', help=t('cli.blur'))
    pm.add_argument('--blur-side', choices=['a', 'b', 'none'], default='b',
                    help=t('cli.blur_side'))
    pm.add_argument('--convert-side', choices=['a', 'b'], default=None,
                    help=t('cli.convert_side'))
    pm.add_argument('--convert', default='none', help=t('cli.convert'))
    pm.add_argument('--title', default=None, help=t('cli.title'))
    pm.add_argument('--author', default=None, help=t('cli.author'))
    pm.add_argument('--toggle-label', default='Show / Hide translation',
                    help=t('cli.toggle_label'))
    pm.set_defaults(func=cmd_merge, blur_side_default=True)

    ps = sub.add_parser('split', help=t('cli.split'))
    ps.add_argument('--in', dest='input', required=True, help=t('cli.in'))
    ps.add_argument('--out-dir', required=True, help=t('cli.out_dir'))
    ps.add_argument('--langs', default=None, help=t('cli.langs'))
    ps.add_argument('--workdir', default=None, help=t('cli.workdir'))
    ps.set_defaults(func=cmd_split)

    pr = sub.add_parser('remerge', help=t('cli.remerge'))
    pr.add_argument('--in', dest='input', required=True, help=t('cli.in'))
    pr.add_argument('--out', required=True, help=t('cli.out'))
    pr.add_argument('--a-lang', default=None, help=t('cli.a_lang'))
    pr.add_argument('--b-lang', default=None, help=t('cli.b_lang'))
    pr.add_argument('--blur', default='0.25em', help=t('cli.blur'))
    pr.add_argument('--blur-side', choices=['a', 'b', 'none'], default='b',
                    help=t('cli.blur_side'))
    pr.add_argument('--convert-side', choices=['a', 'b'], default=None,
                    help=t('cli.convert_side'))
    pr.add_argument('--convert', default='none', help=t('cli.convert'))
    pr.add_argument('--title', default=None, help=t('cli.title'))
    pr.add_argument('--author', default=None, help=t('cli.author'))
    pr.add_argument('--toggle-label', default='Show / Hide translation',
                    help=t('cli.toggle_label'))
    pr.set_defaults(func=cmd_remerge)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    main()
