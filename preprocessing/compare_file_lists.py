#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比「导入开始前」与「导入结束后」的文件路径，找出期间新增的文件。

典型场景：长时间批量导入期间，业务侧仍在原磁盘上新增文件；导入完成后用本脚本
对比「当初的路径清单」与「重新扫描磁盘得到的路径清单」，得到需补导入的新增文件列表。

用法示例（在仓库 importer 根目录）：

    # 两份文本清单（每行一个路径，与 find / preprocess 约定一致）
    python3 preprocessing/compare_file_lists.py \\
        --baseline ./file_list_at_import_start.txt \\
        --current ./file_list_rescan.txt \\
        -o ./new_files_since_baseline.txt

    # 无 --current 时，直接扫描目录生成「当前」集合再对比
    python3 preprocessing/compare_file_lists.py \\
        --baseline ./file_list_at_import_start.txt \\
        --scan /path/to/data/root \\
        -o ./new_files_since_baseline.txt

    # 同时输出「基准中有、当前已不存在」的路径（删除/移动/改名后可能误报）
    python3 preprocessing/compare_file_lists.py -b old.txt -c new.txt --also-removed -o new_since_old.txt
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def detect_file_encoding(file_path: str) -> str:
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb18030", "gb2312", "utf-16", "latin1"]
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                f.read(4096)
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "utf-8"


def read_path_lines(path: str) -> list[str]:
    enc = detect_file_encoding(path)
    lines: list[str] = []
    with open(path, "r", encoding=enc, errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            lines.append(s)
    return lines


def normalize_path_for_compare(path: str, *, case_fold: bool) -> str:
    """统一路径写法，减少因分隔符、符号链接（如 macOS /tmp）、大小写导致的假差异。"""
    p = path.strip().strip("\ufeff")
    if not p:
        return ""
    expanded = os.path.expanduser(p)
    norm = os.path.normpath(expanded)
    try:
        # 对不存在路径 realpath 仍会规范化已存在的路径前缀（如 /tmp → /private/tmp）
        norm = os.path.realpath(norm)
    except OSError:
        pass
    if case_fold:
        norm = os.path.normcase(norm)
    return norm


def load_path_set(
    lines: list[str], *, case_fold: bool
) -> tuple[set[str], dict[str, str]]:
    """返回规范化集合，以及 规范化路径 -> 展示用原始一行（取首次出现）。"""
    seen: set[str] = set()
    canonical_to_display: dict[str, str] = {}
    for raw in lines:
        key = normalize_path_for_compare(raw, case_fold=case_fold)
        if not key:
            continue
        if key not in canonical_to_display:
            canonical_to_display[key] = raw
        seen.add(key)
    return seen, canonical_to_display


def iter_files_under_roots(roots: list[str]) -> list[str]:
    """递归列出各根目录下文件，返回绝对路径字符串。"""
    out: list[str] = []
    for root in roots:
        r = Path(root).expanduser()
        if not r.is_dir():
            print(f"警告：跳过非目录路径: {root}", file=sys.stderr)
            continue
        base = r.resolve()
        for dirpath, _dirnames, filenames in os.walk(base, followlinks=False):
            for name in filenames:
                out.append(str(Path(dirpath) / name))
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="对比基准路径清单与当前路径，输出新增文件列表（长时间导入后补扫场景）。"
    )
    p.add_argument(
        "-b",
        "--baseline",
        required=True,
        help="导入开始前生成的路径清单（每行一个路径的 UTF-8/GBK 文本）",
    )
    p.add_argument(
        "-c",
        "--current",
        help="重新扫描后得到的路径清单；与 --scan 二选一，不可同时使用",
    )
    p.add_argument(
        "--scan",
        action="append",
        metavar="DIR",
        help="可多次指定：在这些目录下递归扫描文件，作为「当前」集合",
    )
    p.add_argument(
        "-o",
        "--output",
        help="写入新增路径列表（UTF-8）；未指定则打印到标准输出",
    )
    p.add_argument(
        "--also-removed",
        action="store_true",
        help="另写一份「仅在基准中、当前不存在」的路径（需配合 -o，文件名为 <主文件名>.removed<扩展名>）",
    )
    p.add_argument(
        "--case-sensitive",
        action="store_true",
        help="路径比较区分大小写（默认：仅 Windows 下忽略大小写；macOS/Linux 区分大小写）",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if bool(args.current) == bool(args.scan):
        print(
            "错误：请指定其一：--current <重新扫描清单> 或 --scan <目录>（可多次）",
            file=sys.stderr,
        )
        return 2
    if args.also_removed and not args.output:
        print("错误：--also-removed 需配合 -o/--output 指定主输出文件", file=sys.stderr)
        return 2

    case_fold = False if args.case_sensitive else (os.name == "nt")

    baseline_lines = read_path_lines(args.baseline)
    baseline_set, baseline_display = load_path_set(baseline_lines, case_fold=case_fold)

    if args.current:
        current_lines = read_path_lines(args.current)
    else:
        current_lines = iter_files_under_roots(args.scan or [])

    current_set, current_display = load_path_set(current_lines, case_fold=case_fold)

    new_keys = sorted(current_set - baseline_set)
    removed_keys = sorted(baseline_set - current_set) if args.also_removed else []

    new_paths = [current_display.get(k, k) for k in new_keys]
    removed_paths = [baseline_display.get(k, k) for k in removed_keys]

    out_lines = "\n".join(new_paths) + ("\n" if new_paths else "")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out_lines, encoding="utf-8")
        print(
            f"新增文件：{len(new_paths)} 条 → {out_path}",
            file=sys.stderr,
        )
        if args.also_removed:
            rem_path = out_path.with_name(
                f"{out_path.stem}.removed{out_path.suffix}"
            )
            rem_path.write_text(
                "\n".join(removed_paths) + ("\n" if removed_paths else ""),
                encoding="utf-8",
            )
            print(
                f"仅基准存在：{len(removed_paths)} 条 → {rem_path}",
                file=sys.stderr,
            )
    else:
        sys.stdout.write(out_lines)

    print(
        f"统计：基准 {len(baseline_set)} 条，当前 {len(current_set)} 条，"
        f"新增 {len(new_paths)} 条"
        + (f"，仅基准 {len(removed_paths)} 条" if args.also_removed else ""),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
