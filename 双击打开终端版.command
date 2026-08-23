#!/bin/bash
# 双击这个文件就能用终端向导：一步步问你要做什么，不用记命令和参数。
cd "$(dirname "$0")" || exit 1
python3 -m bilingual_epub.tui
echo
echo "可以关掉这个窗口了。"
