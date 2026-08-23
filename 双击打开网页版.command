#!/bin/bash
# 双击这个文件就能用网页版：自动起服务器 + 自动开浏览器。
# 用完直接关掉弹出来的终端窗口（或按 Ctrl+C）即可。
cd "$(dirname "$0")" || exit 1
echo "正在启动双语 EPUB 工具箱（网页版）……"
python3 -m bilingual_epub.webui
echo
echo "已停止。可以关掉这个窗口了。"
