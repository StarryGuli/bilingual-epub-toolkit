"""bilingual-epub-toolkit — merge, split, and re-merge bilingual EPUBs.

Public API:

    from bilingual_epub import merge_bilingual, split_by_lang

    merge_bilingual('english.epub', 'french.epub', 'bilingual.epub')
    split_by_lang('bilingual.epub', './out/')
"""
__version__ = '0.1.0'

from .merge import merge_bilingual
from .split import split_by_lang

__all__ = ['merge_bilingual', 'split_by_lang', '__version__']
