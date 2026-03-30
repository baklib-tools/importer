#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
仅导入到 DAM（不创建站点页面）的入口脚本。

内部复用 import_files_to_dam_and_pages.py 的实现，并强制开启 --skip-pages。
"""

import sys

from import_files_to_dam_and_pages import main as core_main


def main():
    argv = sys.argv[1:]
    if "--skip-pages" not in argv:
        argv = argv + ["--skip-pages"]
    sys.argv = [sys.argv[0]] + argv
    core_main()


if __name__ == "__main__":
    main()

