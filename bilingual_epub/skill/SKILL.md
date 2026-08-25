---
name: bilingual-epub
description: Build a tap-to-reveal bilingual EPUB from books the user already has. Use when the user wants a facing-text or side-by-side bilingual ebook, wants to read a book with a translation under each paragraph, has two editions of one book to combine, wants a bilingual EPUB split back into separate languages, or has a book in only one language and wants the other side translated. Triggers include "双语电子书", "中英对照", "对照书", "bilingual epub", "facing text", "把这本书做成双语", "翻译这本书做成对照版".
---

# Bilingual EPUB

Turn EPUBs into a tap-to-reveal bilingual edition: each paragraph in the
original, its translation directly below, blurred until tapped.

When the user has **two editions of the same book**, merge them. When they have
**only one**, translate it first — and when *you* do the translating, it runs on
the subscription they already pay for rather than a separate API bill.

## Setup

```bash
pip install bilingual-epub-toolkit
```

Confirm with `bilingual-epub --help`. Everything below is that one command.

## Which route

| The user has | Do this |
| --- | --- |
| Two editions, same book, different languages | `merge` |
| One edition, wants the other side | **translate it yourself** (below), then `merge` |
| One edition, and an API budget they would rather spend | `translate`, then `merge` |
| A bilingual book, wants it restyled | `remerge` |
| A bilingual book, wants the languages separated | `split` |

Do not reach for `translate` just because translation was mentioned. If you can
read and write the target language, doing it yourself costs the user nothing
extra and you can hold the whole book's context, which per-batch API calls
cannot.

## Translating it yourself

Three steps: text out, translate, text back in.

### 1. Export

```bash
bilingual-epub export-text --in book.epub --out book.json
```

Numbered blocks come out:

```json
{"format": "bilingual-epub-text/1", "source_lang": "en",
 "blocks": [{"i": 0, "tag": "h1", "text": "Chapter One"},
            {"i": 1, "tag": "p", "text": "It was a bright cold day..."}]}
```

Check the size before starting. A novel runs to a thousand blocks and several
hundred thousand characters — tell the user roughly what that involves and let
them confirm, rather than silently beginning a very long job.

### 2. Translate

Write one translation per block. Any of these is accepted:

- a JSON array of strings
- `{"target_lang": "zh", "blocks": [{"i": 0, "text": "..."}, ...]}`
- plain text, one block per line

**The rule that matters: exactly as many blocks out as went in, same order.**

That parallel structure is the entire reason this produces a clean bilingual
book — every paragraph pairs with its own translation instead of being guessed
at by a length heuristic. So:

- never merge two blocks into one, even when it reads better
- never split one block into two
- never drop a block, and never add a note or comment as a block
- a heading stays a heading, and stays short
- if a block is untranslatable, repeat it unchanged rather than leaving it empty

Work in chunks that sit comfortably in context — a few dozen blocks — and keep
the numbering straight across chunks. For a long book write results to disk as
you go, so an interrupted session resumes instead of restarting.

Import refuses a file whose count does not match and prints both numbers. That
is a real error, not a warning to route around: a file one block short shifts
every later paragraph against the wrong original, and nobody notices until they
are reading it.

### 3. Import and merge

```bash
bilingual-epub import-text --export book.json --text translated.json \
    --out book.zh.epub --lang zh
bilingual-epub merge --a book.epub --b book.zh.epub --out bilingual.epub
```

The stats table from `merge` should be all 1:1 with zeros elsewhere. If it is
not, the translation drifted — check the block count rather than shipping it.

## Using an API key instead

When the user would rather spend an API budget than your context:

```bash
bilingual-epub translate --in book.epub --out book.zh.epub --to zh \
    --base-url https://api.deepseek.com/v1 --api-key "$KEY" --model deepseek-chat
```

- `--dialect openai` (default) covers OpenAI, DeepSeek, Moonshot, Zhipu,
  SiliconFlow, OpenRouter, Groq, Together, Ollama, LM Studio, vLLM — anything
  serving `/chat/completions`. `--dialect anthropic` uses `/v1/messages`.
- `--dry-run` reports blocks, characters and request count without spending
  anything. Run it first on a full-length book and show the user the numbers.
- Progress is cached beside the output, so an interrupted run resumes rather
  than paying twice.
- Keys can come from `BILINGUAL_API_KEY`, `OPENAI_API_KEY` or
  `ANTHROPIC_API_KEY`. Prefer the environment variable, and never write a key
  into a file that gets committed.

## Merging two existing editions

```bash
bilingual-epub merge --a english.epub --b chinese.epub --out bilingual.epub
```

- `--blur-side b|a|none` — which side starts hidden; `none` shows both plainly
- `--blur 0.25em` — how hard the hidden side is blurred
- `--convert-side b --convert tw2sp` — Traditional to Simplified, needs
  `pip install "bilingual-epub-toolkit[chinese]"`

Two independently published editions will not align perfectly; roughly 90% 1:1
is normal and the rest are n:m runs. That is expected and still readable. A book
you translated yourself should be 100%.

## Reading the stats

```
chapter      A     B |   1:1   n:m A-only B-only
ch001       42    42 |    42     0      0      0
```

`1:1` is paragraphs matched one to one. `n:m` is a run the aligner grouped
because the two editions break sentences differently. `A-only` / `B-only` are
paragraphs with no counterpart — many of those usually means the files are not
the same edition, or one carries front matter the other lacks.

## What will not work

- **DRM-protected files.** Nothing can be extracted; the tool stops with an
  error. Say so plainly rather than trying to work around it.
- **Books with no headings at all.** They come out as one long chapter. The text
  is intact, but there is no chapter navigation to build from.
- **Bilingual books not tagged per paragraph.** `split` reads `lang` attributes;
  a book without them lands entirely in one bucket and cannot be separated.

## Copyright

These are usually commercial books, and the output is for a user who already
owns them. Do not upload their books anywhere, and do not commit an EPUB into a
repository — the toolkit's own `.gitignore` excludes `*.epub` for that reason.
