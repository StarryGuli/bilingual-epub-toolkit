<p align="center">
  <img src="./assets/readme/hero.svg" width="100%"
       alt="Bilingual EPUB Toolkit — two monolingual EPUBs in, one facing-text book out, with the translation blurred until tapped">
</p>

<p align="center">
  <a href="./README.zh-CN.md">中文说明</a> ·
  <a href="#install">Install</a> ·
  <a href="#try-it-in-one-command">Try it</a> ·
  <a href="#known-limits">Limits</a>
</p>

Reading a book in a language you are still learning usually means choosing: the
original, and looking things up constantly, or the translation, and not
learning much. This makes a third thing — one EPUB where every paragraph is
followed by its translation, blurred, until you tap it.

It works on any standard EPUB, in any language pair. Nothing is uploaded
anywhere; everything runs on your machine.

## Try it in one command

Two sample books ship with the repository, so there is nothing to find first:

```bash
bilingual-epub merge --a examples/sample-en.epub --b examples/sample-fr.epub --out demo.epub
```

Open `demo.epub` in Apple Books, or any EPUB 3 reader: English paragraph,
French paragraph blurred underneath, tap to reveal, tap again to hide.

The samples are an original short story written for this repository — not a
real book, so there is no rights question. See [`examples/`](./examples/).

## Install

```bash
pip install bilingual-epub-toolkit
```

For Chinese Traditional ↔ Simplified conversion, which needs opencc:

```bash
pip install "bilingual-epub-toolkit[chinese]"
```

Three commands are installed:

| Command | What it is |
| --- | --- |
| `bilingual-epub` | the CLI, with `merge` / `split` / `remerge` |
| `bilingual-epub-tui` | a terminal wizard that asks instead of taking flags |
| `bilingual-epub-web` | a local web page — drag books in, no paths to type |

All three speak English or Chinese, following your locale. Force it with
`--lang en` or `--lang zh`.

## The three operations

### merge — two monolingual books into one

```bash
bilingual-epub merge \
  --a english.epub --b french.epub --out bilingual.epub \
  --blur-side b --blur 0.25em
```

Hiding a side is optional. For plain facing text with nothing blurred:

```bash
bilingual-epub merge --a english.epub --b french.epub --out plain.epub --no-blur
```

Otherwise `--blur-side` takes `a` or `b`, and `--blur` is any CSS length; `em`
is worth preferring because it scales with the reader's font size. Title and
author default to a combination of both sources; `--title` and `--author`
override.

To convert Chinese script while merging:

```bash
bilingual-epub merge --a en.epub --b zh-hant.epub --out out.epub \
  --convert-side b --convert tw2sp
```

### split — one bilingual book back into monolingual ones

```bash
bilingual-epub split --in bilingual.epub --out-dir ./split/ --langs en,fr
```

Which paragraph belongs to which language is read from each block's `lang`
attribute. Without `--langs`, every language found is written out.

### remerge — restyle a bilingual book you already have

```bash
bilingual-epub remerge --in old.epub --out new.epub --blur-side a --blur 0.35em
```

Split then merge, in one step. Useful for changing the blur, flipping which
side is hidden, or converting a bilingual book from elsewhere into this
tap-to-reveal form.

## How it works

Two problems have to be solved: where the chapters are, and which paragraph
matches which.

**Chapters** come from the EPUB itself — `META-INF/container.xml` to the OPF to
the manifest and spine, the standard path. Chapter boundaries are found by
scanning every heading level in the book and picking the one that recurs the
way a chapter does, so no per-book table of internal filenames is needed.

**Alignment** is Gale–Church: a length-based statistical model solved by
dynamic programming, with a bonus when headings coincide so section starts
anchor the sequence. It handles the usual 1:1 case plus paragraphs that were
split or merged in translation.

Every block in the output carries a `lang` attribute, which is what lets
`split` undo a `merge` exactly.

The tap-to-reveal effect is CSS `:target` plus a small progressive-enhancement
script, so it degrades to plain visible text in readers that allow neither.

## Known limits

- **DRM is not supported.** Encrypted EPUBs — most bought from commercial
  stores — decompress into ciphertext. The tool reports that it found no text
  and stops.
- **Chapter detection needs headings.** A book that uses no `<h1>`–`<h6>` at
  all degrades to a single chapter. Nothing is lost, but nothing is divided.
- **Alignment is statistical, not semantic.** Paragraph length and heading
  co-occurrence are heuristics. Editions that add, cut, or restructure text
  will pair imperfectly; the per-chapter table printed after a merge reports
  the 1:1 rate so you can judge the result yourself.
- **`split` depends on per-paragraph `lang`.** Books this tool merged always
  split cleanly. Bilingual books from elsewhere often do not tag language per
  paragraph, in which case everything lands in one bucket and there is nothing
  to separate.

## Bring your own books

This repository contains no real books, and `*.epub` is gitignored apart from
the generated samples. The tool reads files you already have; obtaining them is
your business.

## Development

```bash
git clone https://github.com/StarryGuli/bilingual-epub-toolkit.git
cd bilingual-epub-toolkit
pip install -e ".[dev,chinese]"
pytest && ruff check .
```

Tests build synthetic EPUBs in code rather than checking book files into the
repository — see [`tests/conftest.py`](./tests/conftest.py). They cover merge,
split, and remerge end to end, both cover image formats, the option surface,
and the error cases.

## License

Apache-2.0. See [LICENSE](./LICENSE).
