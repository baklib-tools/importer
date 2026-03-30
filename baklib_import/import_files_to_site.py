#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入到站点页面（= DAM + 站点栏目/资源页）的入口脚本。

内部复用 import_files_to_dam_and_pages.py 的实现，保留其默认行为：创建页面。
如需仅导入 DAM，请使用 import_files_to_dam.py。
"""

from import_files_to_dam_and_pages import main as core_main


def main():
    core_main()


if __name__ == "__main__":
    main()

