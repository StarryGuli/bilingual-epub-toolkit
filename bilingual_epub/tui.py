#!/usr/bin/env python3
"""Interactive terminal wizard -- no flags to remember, it just asks.

    bilingual-epub-tui

Pick an action, give it paths, choose options. Paths can be dragged straight
from a file manager into the terminal (the quoting and backslash-escaped
spaces that produces are cleaned up), ~ is expanded, and Enter takes the
default. English or Chinese, following the system locale; override with
--lang or BILINGUAL_EPUB_LANG.
"""
import os
import sys

from . import merge as merge_mod
from . import split as split_mod
from .i18n import get_lang, set_lang, t

# ANSI colour; switched off when piped to a file so logs stay readable
_TTY = sys.stdout.isatty()


def _c(code, s):
    return '\033[%sm%s\033[0m' % (code, s) if _TTY else s


def bold(s):    return _c('1', s)
def dim(s):     return _c('2', s)
def green(s):   return _c('32', s)
def red(s):     return _c('31', s)
def cyan(s):    return _c('36', s)


def clean_path(raw):
    """Normalise a typed or drag-and-dropped path.

    Dropping a file into a terminal yields '/path/with\\ space.epub' or a
    quoted form; strip quotes, unescape spaces, trim, then expand ~.
    """
    s = (raw or '').strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1]
    s = s.replace('\\ ', ' ').replace('\\~', '~').strip()
    return os.path.expanduser(s)


def ask(prompt, default=None, required=True, is_path=False, must_exist=False):
    """Ask until the answer is usable. Ctrl-C / Ctrl-D exit cleanly."""
    hint = dim(' [%s]' % default) if default else ''
    while True:
        try:
            raw = input('%s%s: ' % (cyan(prompt), hint)).strip()
        except (EOFError, KeyboardInterrupt):
            print('\n' + dim(t('ui.cancelled')))
            sys.exit(130)
        if not raw and default is not None:
            raw = default
        if not raw:
            if not required:
                return ''
            print(red(t('ui.required')))
            continue
        if is_path:
            raw = clean_path(raw)
            if must_exist and not os.path.exists(raw):
                print(red(t('ui.not_found', raw)))
                continue
        return raw


def choose(prompt, options, default_idx=0):
    """options: [(value, label, help_text)] -> the chosen value."""
    print('\n' + bold(prompt))
    for i, (_v, label, help_text) in enumerate(options, 1):
        mark = dim(t('ui.default')) if i - 1 == default_idx else ''
        print('  %s. %s %s' % (bold(str(i)), label, mark))
        if help_text:
            print('     ' + dim(help_text))
    while True:
        try:
            raw = input(cyan(t('ui.pick', len(options)))).strip()
        except (EOFError, KeyboardInterrupt):
            print('\n' + dim(t('ui.cancelled')))
            sys.exit(130)
        if not raw:
            return options[default_idx][0]
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        print(red(t('ui.pick_range', len(options))))


def confirm(prompt, default=True):
    d = 'Y/n' if default else 'y/N'
    while True:
        try:
            raw = input('%s %s: ' % (cyan(prompt), dim('[%s]' % d))).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print('\n' + dim(t('ui.cancelled')))
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
                      % (t('stats.chapter'), t('stats.a'), t('stats.b'),
                         '1:1', 'n:m', t('stats.a_only'), t('stats.b_only'))))
    for row in stats:
        print('%-8s %5d %5d | %5d %5d %6d %6d' % row)
    tot_11 = sum(r[3] for r in stats)
    tot_all = sum(r[3] + r[4] + r[5] + r[6] for r in stats)
    if tot_all:
        pct = 100.0 * tot_11 / tot_all
        print(dim(t('stats.ratio', pct, tot_11, tot_all, t('stats.ratio_note'))))


def ask_blur_opts():
    # Whether to hide a side at all comes first: plenty of people just want
    # facing text, and that should not be buried inside "which side".
    print('\n' + dim(t('blur.enable.help')))
    if not confirm(t('blur.enable'), default=True):
        return 'none', '0.25em'
    blur_side = choose(t('blur.which'), [
        ('b', t('blur.b'), t('blur.b.help')),
        ('a', t('blur.a'), t('blur.a.help')),
    ], default_idx=0)
    return blur_side, ask(t('blur.amount'), default='0.25em')


def ask_convert_opts():
    if not confirm(t('cc.ask'), default=False):
        return None, 'none'
    side = choose(t('cc.side'), [
        ('b', t('blur.b'), ''),
        ('a', t('blur.a'), ''),
    ], default_idx=0)
    cfg = choose(t('cc.how'), [
        ('tw2sp', 'tw2sp', t('cc.tw2sp')),
        ('t2s', 't2s', t('cc.t2s')),
        ('s2t', 's2t', t('cc.s2t')),
        ('s2tw', 's2tw', t('cc.s2tw')),
    ], default_idx=0)
    return side, cfg


def flow_merge():
    print(bold(t('merge.title')))
    print(dim(t('ui.drag_hint')))
    a = ask(t('merge.a'), is_path=True, must_exist=True)
    b = ask(t('merge.b'), is_path=True, must_exist=True)
    default_out = os.path.join(os.path.dirname(a) or '.', 'bilingual.epub')
    out = ask(t('merge.out'), default=default_out, is_path=True)
    blur_side, blur = ask_blur_opts()
    convert_side, cc = ask_convert_opts()
    title = ask(t('merge.book_title'), required=False)

    print(dim(t('ui.working_long')))
    out_path, stats = merge_mod.merge_bilingual(
        a_epub=a, b_epub=b, out_path=out, blur=blur, blur_side=blur_side,
        convert_side=convert_side, cc_config=cc, title=title or None)
    print_stats(stats)
    print(green(t('ui.done', out_path, os.path.getsize(out_path) // 1024)))
    return out_path


def flow_split():
    print(bold(t('split.title')))
    src = ask(t('split.src'), is_path=True, must_exist=True)
    default_dir = os.path.join(os.path.dirname(src) or '.', 'split_out')
    out_dir = ask(t('split.outdir'), default=default_dir, is_path=True)
    langs_raw = ask(t('split.langs'), required=False)
    langs = [s.strip() for s in langs_raw.split(',') if s.strip()] or None

    print(dim(t('ui.working')))
    results = split_mod.split_by_lang(src, out_dir, langs=langs)
    if not results:
        print(red(t('split.none')))
        return None
    print(green(t('split.ok', len(results))))
    for lang, path in results.items():
        print('   %-8s %s (%d KB)' % (lang, path, os.path.getsize(path) // 1024))
    return out_dir


def flow_remerge():
    import shutil
    import tempfile
    print(bold(t('remerge.title')))
    print(dim(t('remerge.why')))
    src = ask(t('remerge.src'), is_path=True, must_exist=True)
    default_out = os.path.join(os.path.dirname(src) or '.', 'remerged.epub')
    out = ask(t('merge.out'), default=default_out, is_path=True)

    tmp = tempfile.mkdtemp(prefix='remerge_')
    try:
        print(dim(t('remerge.peek')))
        parts = split_mod.split_by_lang(src, os.path.join(tmp, 'parts'), workdir=tmp)
        langs = sorted(parts)
        if len(langs) < 2:
            print(red(t('remerge.too_few', len(langs), ', '.join(langs) or '-')))
            print(dim(t('remerge.too_few_hint')))
            return None
        print(green(t('remerge.found', ', '.join(langs))))
        a_lang = choose(t('remerge.pick_a'),
                        [(lg, lg, '') for lg in langs], default_idx=0)
        rest = [lg for lg in langs if lg != a_lang]
        b_lang = choose(t('remerge.pick_b'),
                        [(lg, lg, '') for lg in rest], default_idx=0)
        blur_side, blur = ask_blur_opts()

        print(dim(t('ui.working')))
        out_path, stats = merge_mod.merge_bilingual(
            a_epub=parts[a_lang], b_epub=parts[b_lang], out_path=out,
            blur=blur, blur_side=blur_side)
        print_stats(stats)
        print(green(t('ui.done', out_path, os.path.getsize(out_path) // 1024)))
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog='bilingual-epub-tui', add_help=True)
    ap.add_argument('--lang', choices=['en', 'zh'], default=None,
                    help='interface language / 界面语言')
    args = ap.parse_args(argv)
    if args.lang:
        set_lang(args.lang)

    print(bold('\n%s  %s' % ('📖', t('app.name'))))
    print(dim('%s %s' % (t('app.any_epub'), t('ui.quit_hint'))))
    if get_lang() == 'en':
        print(dim('(中文界面: --lang zh)'))
    else:
        print(dim('(English: --lang en)'))

    while True:
        action = choose(t('menu.what'), [
            ('merge',   t('menu.merge'), t('menu.merge.help')),
            ('split',   t('menu.split'), ''),
            ('remerge', t('menu.remerge'), ''),
            ('quit',    t('menu.quit'), ''),
        ], default_idx=0)

        if action == 'quit':
            print(dim(t('ui.bye')))
            return 0

        try:
            {'merge': flow_merge, 'split': flow_split, 'remerge': flow_remerge}[action]()
        except SystemExit as e:
            # SystemExit from the engine always carries a human-readable
            # message (missing file, not an EPUB, no text found); it should
            # not take the wizard down with it
            if isinstance(e.code, str):
                print(red(t('ui.error', e.code)))
            else:
                raise
        except Exception as ex:
            print(red(t('ui.error', '%s: %s' % (type(ex).__name__, ex))))
            print(dim(t('ui.error_detail')))

        if not confirm(t('ui.anything_else'), default=False):
            print(dim(t('ui.bye')))
            return 0


if __name__ == '__main__':
    sys.exit(main())
