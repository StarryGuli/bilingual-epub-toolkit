#!/usr/bin/env python3
"""CLI entry point for the generic bilingual-EPUB toolkit.

Subcommands:
  merge    two monolingual EPUBs (any book, any language pair)  -> one bilingual EPUB
  split    one bilingual (or multi-language) EPUB                -> N monolingual EPUBs
  remerge  one existing bilingual EPUB, re-rendered w/ new options -> a new bilingual EPUB
           (= split then merge again; handy for "I have a bilingual book from
           somewhere else and want it in this tool's tap-to-reveal style", or
           "same book, different blur/opencc settings")

For a book that exists in only one language, there is no second edition to
merge against, so make one:
  translate    call your own model API and write the translated edition
  export-text  dump the paragraphs for something else to translate
  import-text  fold a finished translation back into an EPUB

export/import is the route for an agent that already has your subscription:
it translates the exported file itself, so no API key is involved at all.

  skill        drop the agent instructions into your own project

Messages and help are English or Chinese, following the system locale;
override with --lang or BILINGUAL_EPUB_LANG.
"""
import argparse
import os
import sys

from . import merge as merge_mod
from . import split as split_mod
from . import textio
from .i18n import set_lang, t


def cmd_skill(args):
    """Copy the agent skill into the user's own project."""
    import shutil
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'skill', 'SKILL.md')
    dest_dir = os.path.join(args.out, 'bilingual-epub')
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, 'SKILL.md')
    shutil.copyfile(src, dest)
    print(t('cli.skill_wrote', dest))


def cmd_export_text(args):
    payload = textio.export_text(args.input, workdir=args.workdir)
    textio.write_export(payload, args.out)
    chars = sum(len(b['text']) for b in payload['blocks'])
    print(t('cli.exported', args.out, len(payload['blocks']), chars))


def cmd_import_text(args):
    out = textio.import_text(args.export, args.text, args.out,
                             lang=args.lang, title=args.title)
    print(t('cli.wrote', out, os.path.getsize(out) // 1024))


def cmd_translate(args):
    from . import translate as tr
    payload = textio.export_text(args.input, workdir=args.workdir)
    est = tr.estimate(payload, args.batch_size)
    print(t('cli.tr_plan', est['blocks'], est['chars'], est['requests']),
          file=sys.stderr)
    if args.dry_run:
        return
    provider = tr.provider_from_args(args)
    cache = args.cache or (args.out + '.progress.json')
    texts = tr.translate_payload(
        payload, provider, args.to, batch_size=args.batch_size,
        cache_path=cache, retries=args.retries,
        on_progress=tr.progress_printer(args.quiet))
    textio.build_epub(payload, texts, args.out, args.to, title=args.title)
    if not args.keep_cache and os.path.exists(cache):
        os.remove(cache)
    print(t('cli.wrote', args.out, os.path.getsize(args.out) // 1024))


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
    pm.add_argument('--no-blur', action='store_true', help=t('cli.no_blur'))
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
    pr.add_argument('--no-blur', action='store_true', help=t('cli.no_blur'))
    pr.add_argument('--convert-side', choices=['a', 'b'], default=None,
                    help=t('cli.convert_side'))
    pr.add_argument('--convert', default='none', help=t('cli.convert'))
    pr.add_argument('--title', default=None, help=t('cli.title'))
    pr.add_argument('--author', default=None, help=t('cli.author'))
    pr.add_argument('--toggle-label', default='Show / Hide translation',
                    help=t('cli.toggle_label'))
    pr.set_defaults(func=cmd_remerge)

    # ---- translate: your API, your bill ---------------------------------- #
    pt = sub.add_parser('translate', help=t('cli.translate'))
    pt.add_argument('--in', dest='input', required=True, help=t('cli.tr_in'))
    pt.add_argument('--out', required=True, help=t('cli.tr_out'))
    pt.add_argument('--to', required=True, help=t('cli.tr_to'))
    pt.add_argument('--dialect', choices=['openai', 'anthropic'], default='openai',
                    help=t('cli.tr_dialect'))
    pt.add_argument('--base-url', default=None, help=t('cli.tr_base'))
    pt.add_argument('--api-key', default=None, help=t('cli.tr_key'))
    pt.add_argument('--model', default=None, help=t('cli.tr_model'))
    pt.add_argument('--batch-size', type=int, default=20, help=t('cli.tr_batch'))
    pt.add_argument('--retries', type=int, default=3, help=t('cli.tr_retries'))
    pt.add_argument('--timeout', type=float, default=180.0, help=t('cli.tr_timeout'))
    pt.add_argument('--cache', default=None, help=t('cli.tr_cache'))
    pt.add_argument('--keep-cache', action='store_true', help=t('cli.tr_keepcache'))
    pt.add_argument('--dry-run', action='store_true', help=t('cli.tr_dry'))
    pt.add_argument('--quiet', action='store_true', help=t('cli.tr_quiet'))
    pt.add_argument('--title', default=None, help=t('cli.tr_title'))
    pt.add_argument('--workdir', default=None, help=t('cli.workdir'))
    pt.set_defaults(func=cmd_translate)

    # ---- export-text / import-text: let something else translate --------- #
    pe = sub.add_parser('export-text', help=t('cli.export'))
    pe.add_argument('--in', dest='input', required=True, help=t('cli.tr_in'))
    pe.add_argument('--out', required=True, help=t('cli.ex_out'))
    pe.add_argument('--workdir', default=None, help=t('cli.workdir'))
    pe.set_defaults(func=cmd_export_text)

    pi = sub.add_parser('import-text', help=t('cli.import'))
    pi.add_argument('--export', required=True, help=t('cli.im_export'))
    pi.add_argument('--text', required=True, help=t('cli.im_text'))
    pi.add_argument('--out', required=True, help=t('cli.tr_out'))
    pi.add_argument('--lang', default=None, help=t('cli.im_lang'))
    pi.add_argument('--title', default=None, help=t('cli.tr_title'))
    pi.set_defaults(func=cmd_import_text)

    # ---- skill: hand the agent instructions to the user's own codebase --- #
    pk = sub.add_parser('skill', help=t('cli.skill'))
    pk.add_argument('--out', default='.claude/skills', help=t('cli.skill_out'))
    pk.set_defaults(func=cmd_skill)

    args = p.parse_args(argv)
    # --no-blur is the plain-language spelling of --blur-side none
    if getattr(args, 'no_blur', False):
        args.blur_side = 'none'
    args.func(args)


if __name__ == '__main__':
    main()
