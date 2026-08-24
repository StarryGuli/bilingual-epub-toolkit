#!/usr/bin/env python3
"""Regenerate the sample EPUBs committed in this directory.

    python3 examples/make_sample_books.py

The text and the builder both live in the package, at
``bilingual_epub/samples.py`` -- the local web UI offers these books as real
downloads and the wheel does not ship examples/, so the package has to be able
to produce them on its own. This script is just the command-line way to write
them out here.

The generated files are committed so the toolkit can be tried without running
this first; re-run it after editing the text.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bilingual_epub.samples import build_samples  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    for lang, path in sorted(build_samples(HERE).items()):
        print('%s  %s (%d KB)' % (lang, os.path.relpath(path),
                                  os.path.getsize(path) // 1024 or 1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
