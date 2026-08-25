<p align="center">
  <img src="https://raw.githubusercontent.com/StarryGuli/bilingual-epub-toolkit/main/assets/readme/hero.svg" width="100%"
       alt="Bilingual EPUB Toolkit — two monolingual EPUBs in, one facing-text book out, with the translation blurred until tapped">
</p>

<p align="center">
  <a href="https://epub.starry-files.duckdns.org"><b>Try it online</b></a> ·
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

## Try it without installing anything

**[epub.starry-files.duckdns.org](https://epub.starry-files.duckdns.org)** runs
this same code. Drag two EPUBs in and it hands back the merged book.

It is a small personal server, so treat it as a demo: uploads are capped at
25 MB, jobs are rate limited per address, and everything you upload or produce
is deleted automatically after 30 minutes. Nobody else can download what you
made. For real work, or for anything you would rather not upload at all,
install it and run it locally — that is what the rest of this page is about.

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

## Only have the book in one language?

There is no second edition to merge against, so make one. Both routes produce a
translation that is *structurally parallel* to the original — same blocks, same
order — which is why the merge that follows comes out 100% one-to-one instead of
the ~90% two independently published editions give you.

### Let your own coding agent translate it

This costs no API key at all: the agent translates on the subscription you are
already paying for.

```bash
bilingual-epub skill            # writes .claude/skills/bilingual-epub/SKILL.md
```

Then ask your agent for a bilingual edition of the book. The skill tells it to
export the text, translate it, and fold it back in. You can also grab the file
from the [hosted instance](https://epub.starry-files.duckdns.org/skill).

Under the hood it is three commands, usable by hand too:

```bash
bilingual-epub export-text --in book.epub --out book.json
# …translate book.json into translated.json…
bilingual-epub import-text --export book.json --text translated.json \
    --out book.zh.epub --lang zh
```

The translation may be a JSON array of strings, a JSON object with a `blocks`
list, or plain text one block per line. A file whose block count does not match
is rejected rather than accepted — a translation one block short would shift
every later paragraph against the wrong original.

### Or use an API key

Bring your own endpoint; the bill lands on your account.

```bash
bilingual-epub translate --in book.epub --out book.zh.epub --to zh \
    --base-url https://api.deepseek.com/v1 --api-key "$KEY" --model deepseek-chat
```

`--dialect openai` (the default) covers OpenAI, DeepSeek, Moonshot, Zhipu,
SiliconFlow, OpenRouter, Groq, Together and any local server speaking
`/chat/completions` — Ollama, LM Studio, vLLM. `--dialect anthropic` uses
`/v1/messages`.

- `--dry-run` reports blocks, characters and request count without spending
  anything
- progress is cached next to the output, so an interrupted run resumes instead
  of paying twice
- a batch that comes back the wrong length is retried, then halved, then done
  one block at a time — never silently accepted
- keys also read from `BILINGUAL_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`

## Running it on a server

The local web UI assumes one trusted user on their own machine. `--public`
switches those assumptions for a host other people can reach:

```bash
bilingual-epub-web --public --port 8799
```

That refuses server-side paths (locally the path field opens anything you
could open yourself; on a public host that is an arbitrary-file-read hole),
gives every visitor an isolated scratch directory so nobody can download
anybody else's books, rate-limits per address, caps uploads at 25 MB, and
deletes idle sessions after 30 minutes (`--ttl`).

### Keeping bots out without shutting people out

Cookies and rate limits alone do not stop a determined bot: rotating addresses
defeats the bucket, and a headless browser collects a cookie as readily as a
person does. Turnstile is what actually raises that cost, and unlike a password
it costs a visitor nothing — the service stays open to everyone.

```bash
export TURNSTILE_SITEKEY=0x...      # from the Cloudflare dashboard, Turnstile
export TURNSTILE_SECRET=0x...
bilingual-epub-web --public
```

Every job is then verified with Cloudflare before it runs. Verification fails
closed: if Cloudflare cannot be reached the job is refused rather than quietly
let through. With no keys set, the widget is not rendered and nothing is
checked, which is what you want locally.

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
