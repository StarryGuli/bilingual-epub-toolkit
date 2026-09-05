<p align="center">
  <img src="https://raw.githubusercontent.com/StarryGuli/bilingual-epub-toolkit/main/assets/readme/hero.svg" width="100%"
       alt="Bilingual EPUB Toolkit — two monolingual EPUBs in, one facing-text book out, with the translation blurred until tapped">
</p>

<p align="center">
  <a href="https://epub.starry-files.duckdns.org"><b>Live demo</b></a> ·
  <a href="./README.zh-CN.md">中文说明</a> ·
  <a href="#installation">Installation</a> ·
  <a href="#usage">Usage</a> ·
  <a href="#translation">Translation</a> ·
  <a href="#limitations">Limitations</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/bilingual-epub-toolkit/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/bilingual-epub-toolkit"></a>
  <img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-blue">
  <img alt="Python 3.9+" src="https://img.shields.io/badge/python-3.9%2B-blue">
  <img alt="No required dependencies beyond lxml" src="https://img.shields.io/badge/dependencies-lxml-lightgrey">
</p>

Builds facing-text bilingual EPUBs. Each paragraph is followed by its
translation, blurred until tapped, so the original can be read first and the
translation consulted only when needed.

Works with any standard EPUB and any language pair. Chapter structure and
paragraph pairing are derived from the files themselves — no per-book
configuration. All processing is local.

- **merge** two monolingual editions into one bilingual book
- **split** a bilingual book back into separate languages
- **remerge** an existing bilingual book with different settings
- **translate** the missing side via a model API, or via a coding agent
- Command line, terminal wizard, and local web interface, in English or Chinese

## Installation

```bash
pip install bilingual-epub-toolkit
```

Chinese Traditional ↔ Simplified conversion requires opencc:

```bash
pip install "bilingual-epub-toolkit[chinese]"
```

Requires Python 3.9 or later. The only runtime dependency is lxml.

Three commands are installed:

| Command | Interface |
| --- | --- |
| `bilingual-epub` | command line |
| `bilingual-epub-tui` | terminal wizard, prompts instead of flags |
| `bilingual-epub-web` | local web page with drag-and-drop |

Interface language follows the system locale and can be set with `--lang en`
or `--lang zh`.

## Quick start

Two sample books ship with the repository:

```bash
bilingual-epub merge --a examples/sample-en.epub --b examples/sample-fr.epub --out demo.epub
```

Open `demo.epub` in Apple Books or any EPUB 3 reader. The samples are an
original short story written for this project, so no third-party rights are
involved. A hosted instance is available at
[epub.starry-files.duckdns.org](https://epub.starry-files.duckdns.org) for
trying the tool without installing it; uploads there are capped at 25 MB and
deleted after 30 minutes.

<p align="center">
  <img src="https://raw.githubusercontent.com/StarryGuli/bilingual-epub-toolkit/main/assets/readme/demo.gif" width="100%"
       alt="Two EPUBs picked, uploaded, and merged, ending with the per-chapter alignment table">
</p>

## Usage

### merge

Combine two monolingual editions:

```bash
bilingual-epub merge \
  --a english.epub --b french.epub --out bilingual.epub \
  --blur-side b --blur 0.25em
```

| Option | Effect |
| --- | --- |
| `--blur-side a\|b` | which side is hidden until tapped (default `b`) |
| `--no-blur` | plain facing text, nothing hidden |
| `--blur` | CSS length; `em` units scale with the reader's font size |
| `--title`, `--author` | override the combined metadata |
| `--convert-side`, `--convert` | opencc script conversion, e.g. `--convert-side b --convert tw2sp` |

A per-chapter table is printed after each merge, reporting how many paragraphs
paired one to one.

### split

Separate a bilingual book by language:

```bash
bilingual-epub split --in bilingual.epub --out-dir ./split/ --langs en,fr
```

Language is read from each block's `lang` attribute. Omitting `--langs` writes
out every language found.

### remerge

Re-render an existing bilingual book with different settings:

```bash
bilingual-epub remerge --in old.epub --out new.epub --blur-side a --blur 0.35em
```

Equivalent to a split followed by a merge. Also converts bilingual books from
other sources into this tap-to-reveal format.

## Translation

When only one edition exists, the second can be generated. Both routes produce
a translation with the same block count and order as the source, so the
subsequent merge pairs every paragraph exactly.

### With a coding agent

Installs a skill that lets an agent such as Claude Code drive the toolkit,
translating on an existing subscription rather than a metered API:

```bash
bilingual-epub skill      # writes .claude/skills/bilingual-epub/SKILL.md
```

The skill file is also available from
[the hosted instance](https://epub.starry-files.duckdns.org/skill).

The underlying commands can be used directly:

```bash
bilingual-epub export-text --in book.epub --out book.json
# translate book.json into translated.json
bilingual-epub import-text --export book.json --text translated.json \
    --out book.zh.epub --lang zh
```

`import-text` accepts a JSON array of strings, a JSON object with a `blocks`
list, or plain text with one block per line. Files whose block count differs
from the source are rejected.

### With a model API

```bash
bilingual-epub translate --in book.epub --out book.zh.epub --to zh \
    --base-url https://api.deepseek.com/v1 --api-key "$KEY" --model deepseek-chat
```

| Option | Effect |
| --- | --- |
| `--dialect openai` | `/chat/completions`; OpenAI, DeepSeek, Moonshot, Zhipu, SiliconFlow, OpenRouter, Groq, Together, Ollama, LM Studio, vLLM (default) |
| `--dialect anthropic` | `/v1/messages` |
| `--dry-run` | report block, character and request counts without sending anything |
| `--batch-size` | paragraphs per request (default 20) |
| `--cache` | progress file; an interrupted run resumes from it |

Credentials may also be supplied through `BILINGUAL_API_KEY`, `OPENAI_API_KEY`
or `ANTHROPIC_API_KEY`. Batches returning the wrong number of blocks are
retried, then subdivided, and are never accepted as-is.

## Self-hosting

The web interface defaults to a single trusted user on localhost. `--public`
adapts it for a shared host:

```bash
bilingual-epub-web --public --port 8799
```

Public mode rejects server-side file paths, isolates each visitor's files,
rate-limits by address, caps uploads at 25 MB, and removes idle sessions after
30 minutes (`--ttl`).

Cloudflare Turnstile can be enabled to filter automated traffic while keeping
the service open to anyone:

```bash
export TURNSTILE_SITEKEY=0x...
export TURNSTILE_SECRET=0x...
bilingual-epub-web --public
```

Jobs are then verified before running, and refused if Cloudflare is
unreachable. Without keys, no widget is rendered and no verification occurs.

## How it works

Chapter boundaries are located by reading the EPUB container, OPF, manifest and
spine, then selecting the heading level that recurs at chapter frequency.

Paragraph pairing uses Gale–Church alignment: a length-based statistical model
solved by dynamic programming, weighted so that co-occurring headings anchor
the sequence. It handles one-to-one pairs as well as paragraphs split or merged
in translation.

Every output block carries a `lang` attribute, which is what allows `split` to
reverse a `merge`. The tap-to-reveal behaviour uses CSS `:target` with a small
progressive-enhancement script, degrading to plain visible text where neither
is supported.

## Limitations

| Limitation | Behaviour |
| --- | --- |
| DRM-protected files | Encrypted EPUBs yield no extractable text; the tool reports this and stops. |
| Books without headings | Degrade to a single chapter. Text is preserved; chapter divisions are not. |
| Statistical alignment | Editions that add, cut or restructure text pair imperfectly. The printed table reports the rate. |
| Untagged bilingual books | `split` requires per-paragraph `lang` attributes. Books lacking them cannot be separated. |

No EPUB files are included in this repository apart from the generated samples,
and `*.epub` is gitignored.

## Development

```bash
git clone https://github.com/StarryGuli/bilingual-epub-toolkit.git
cd bilingual-epub-toolkit
pip install -e ".[dev,chinese]"
pytest && ruff check .
```

Test fixtures are synthetic EPUBs constructed in code rather than checked-in
book files; see [`tests/conftest.py`](./tests/conftest.py). Coverage includes
the three operations end to end, both cover image formats, the translation
round trip against a stub API, public-mode isolation and rate limiting, and
the error paths.

Coverage and conventions are described in [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](./LICENSE).
