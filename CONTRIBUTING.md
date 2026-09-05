# Contributing

Thanks for looking. This is a small project with a narrow purpose, so the most
useful contributions are usually specific: a book that fails to parse, a
language pair that aligns badly, a reader that renders the output wrong.

## Reporting a problem

The single most useful thing you can attach is **what the file looks like
structurally** — not the book itself. This produces it:

```bash
bilingual-epub export-text --in problem.epub --out structure.json
```

Or, if the hosted instance is where it failed, use the "report this failure"
button on the result card. It sends the error and the file's shape; attaching
the book is a separate, optional checkbox.

Please do not attach copyrighted books to public issues.

## Setting up

```bash
git clone https://github.com/StarryGuli/bilingual-epub-toolkit.git
cd bilingual-epub-toolkit
pip install -e ".[dev,chinese]"
pytest && ruff check .
```

Python 3.9 or later. The only runtime dependency is lxml; everything else in
the dev extra is for testing and linting.

## Test fixtures are generated, not checked in

`tests/conftest.py` builds EPUBs in code. No book files are committed, and
`*.epub` is gitignored apart from the samples in `examples/`, which are an
original short story written for this project.

If you need a fixture with a particular shape — no headings, a broken spine,
a cover in an unusual format — add a builder to `conftest.py` rather than
committing a file.

## What tends to matter here

- **Alignment quality.** The pairing is statistical, so it is judged by the
  per-chapter table a merge prints, not by whether it crashed. A change that
  moves that rate on real books is worth more than one that tidies code.
- **Structural tolerance.** Real EPUBs violate the spec constantly. Fixes for
  a book that fails should come with a fixture reproducing its shape.
- **Not leaking book text.** Diagnostics record structure only. If you touch
  `diagnostics.py`, the tests there assert that prose, filenames and paths do
  not survive into a report; keep them passing.

## Style

`ruff check .` is the whole style guide. The code uses `%`-formatting
throughout because it builds XHTML and CSS full of literal percent signs;
`UP031` is disabled for that reason and not by accident.

Comments explain why something is the way it is, especially where the obvious
approach was tried and failed. Several of them exist because a bug got past a
review once already.

## Pull requests

Small and self-contained is easier to accept than broad. If a change alters
what the tool produces — output markup, alignment behaviour, the CLI surface —
say so plainly in the description, because that is what people's existing books
and scripts depend on.

## License

Contributions are accepted under Apache-2.0, the same as the project.
