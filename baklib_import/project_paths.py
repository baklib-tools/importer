#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
仓库路径约定：本目录的上一级为项目根目录（含 preprocessing/、docs/、baklib_import/ 等）。

配置文件默认放在项目根目录；相对路径相对于项目根解析，与当前工作目录无关。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# importer/ 根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resolve_config_path(config_arg: Optional[str]) -> Optional[str]:
    """
    将 --config 解析为绝对路径。

    - 未传入：返回 None
    - 绝对路径：规范化后返回
    - 相对路径：相对于 PROJECT_ROOT（不是当前工作目录）
    """
    if not config_arg:
        return None
    if os.path.isabs(config_arg):
        return os.path.normpath(config_arg)
    return str((PROJECT_ROOT / config_arg).resolve())
