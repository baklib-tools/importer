#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
预创建目录与标签脚本（批量导入前可选）

目的：
- 扫描 Excel 导入清单中的所有文件路径
- 提取目录结构与标签
- 预先创建：
  - DAM 集合（目录）
  - 站点栏目（目录）
  - DAM 标签
  - 站点标签

说明：
- 不上传文件，不创建“每个文件对应的资源页面”
- 适合在批量导入前先跑一遍，减少后续每个文件重复创建目录/标签的耗时
- 启动时会执行 warm-up：将服务端已有的 DAM 集合/标签、站点栏目/站点标签全量拉取到本地缓存，
  后续创建前先查缓存，减少「创建前查询」与「记录已存在再查询」的 API 调用，提升效率

用法示例：
  # 单个 Excel（使用配置文件）
  python prepare_directories_and_tags.py --excel file_list.xlsx --config config.json

  # 批量：指定目录，处理目录下所有 .xlsx（与 batch_import 一致：不含子文件夹，跳过 ~$ 临时文件）
  python prepare_directories_and_tags.py --directory ./excel_files --config config.json

  # 仅预创建 DAM
  python prepare_directories_and_tags.py --excel file_list.xlsx --config config.json --skip-site

  # 模拟运行（只统计，不实际创建）
  python prepare_directories_and_tags.py --excel file_list.xlsx --config config.json --dry-run
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from excel_reader import ExcelReader
from path_processor import PathProcessor
from dam_collections import DAMCollections
from dam_tags import DAMTags
from dam_upload import DAMUpload
from site_pages import SitePages
from site_tags import SiteTags
from create_directories_and_tags import ensure_directories_and_tags
from project_paths import resolve_config_path


def setup_logging(log_file: str = None, debug: bool = False):
    """设置日志配置"""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))

    log_level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=handlers
    )
    return logging.getLogger(__name__)


def load_config(config_path: str) -> Dict:
    """从配置文件加载配置，自动检测编码格式"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在：{config_path}")

    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'latin-1']
    for encoding in encodings:
        try:
            with open(config_path, 'r', encoding=encoding) as f:
                return json.load(f)
        except UnicodeDecodeError:
            continue
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"配置文件 JSON 格式错误（使用 {encoding} 编码）：{e.msg}",
                e.doc,
                e.pos
            )

    raise ValueError(
        f"无法读取配置文件：{config_path}。"
        f"已尝试的编码格式：{', '.join(encodings)}。"
        f"请确保文件是有效的 JSON 格式，并使用 UTF-8 或 GBK 编码。"
    )


def normalize_skip_directories(skip_directories: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """标准化跳过目录列表（用于忽略某些目录及其子目录）"""
    normalized_skip_dirs: List[str] = []
    mapping: Dict[str, str] = {}
    for skip_dir in skip_directories or []:
        normalized = skip_dir.replace('\\', '/').strip('/')
        if not normalized:
            continue
        normalized_lower = normalized.lower()
        normalized_skip_dirs.append(normalized_lower)
        mapping[normalized_lower] = skip_dir
    return normalized_skip_dirs, mapping


def normalize_path_for_skip_compare(file_path: str, path_prefix: Optional[str]) -> str:
    """
    将文件路径标准化为“相对于 path_prefix 的相对路径”（小写，用 / 分隔），用于 skip_directories 比较
    """
    normalized = file_path.replace('\\', '/')

    # 移除 Windows 盘符
    windows_drive_pattern = r'^([A-Za-z]):[/\\]?'
    match = re.match(windows_drive_pattern, normalized)
    if match:
        normalized = normalized[2:]

    # 移除 path_prefix（skip_directories 是相对于 path_prefix 的相对路径）
    if path_prefix:
        normalized_prefix = path_prefix.replace('\\', '/')
        match = re.match(windows_drive_pattern, normalized_prefix)
        if match:
            normalized_prefix = normalized_prefix[2:]
        normalized_prefix = normalized_prefix.strip('/')

        prefix_variants = [
            f'/{normalized_prefix}/',
            f'{normalized_prefix}/',
            f'/{normalized_prefix}',
            normalized_prefix
        ]
        for variant in prefix_variants:
            if normalized.startswith(variant):
                normalized = normalized[len(variant):].lstrip('/')
                break

    return normalized.strip('/').lower()


def is_path_skipped(file_path: str, normalized_skip_dirs: List[str], path_prefix: Optional[str]) -> Tuple[bool, Optional[str]]:
    """判断文件是否命中 skip_directories（返回是否跳过，以及匹配到的 normalized skip_dir）"""
    if not normalized_skip_dirs:
        return False, None

    rel_path = normalize_path_for_skip_compare(file_path, path_prefix)
    for skip_dir in normalized_skip_dirs:
        if rel_path == skip_dir or rel_path.startswith(skip_dir + '/'):
            return True, skip_dir
    return False, None


def get_excel_files_in_directory(directory: str) -> List[str]:
    """
    获取目录下所有 Excel 文件（仅 *.xlsx，不含子文件夹，跳过 ~$ 临时文件）。
    排序与 batch_import 一致：先按文件名长度再按文件名，便于按序号分批。
    """
    directory_path = Path(directory)
    if not directory_path.exists():
        raise FileNotFoundError(f"目录不存在：{directory}")
    if not directory_path.is_dir():
        raise ValueError(f"路径不是目录：{directory}")
    files = []
    for item in directory_path.iterdir():
        if not item.is_file():
            continue
        if item.suffix.lower() != '.xlsx':
            continue
        if item.name.startswith('~$'):
            continue
        files.append(str(item.absolute()))
    files.sort(key=lambda f: (len(os.path.basename(f)), os.path.basename(f)))
    return files


def main():
    parser = argparse.ArgumentParser(
        description='预创建目录与标签（不上传文件、不创建资源页面）'
    )

    parser.add_argument('--excel', help='单个 Excel 文件路径')
    parser.add_argument('--directory', help='Excel 所在目录（批量处理该目录下所有 .xlsx）')
    parser.add_argument(
        '--config',
        help='配置文件路径（JSON，可选）；相对路径相对于项目根目录（与当前工作目录无关）',
    )
    parser.add_argument('--api-key', help='API 密钥（格式：access_key:secret_key，如果使用配置文件则不需要）')
    parser.add_argument('--site-id', type=int, help='站点 ID（可选：不提供则跳过站点栏目/站点标签）')
    parser.add_argument('--base-url', help='API 基础地址（如果使用配置文件则从配置文件读取）')
    parser.add_argument('--start-row', type=int, help='开始行（默认：2，第1行是标题）')
    parser.add_argument('--path-column', help='文件路径列（默认：E）')
    parser.add_argument('--path-prefix', help='路径前缀（要去掉的前缀，支持多个用逗号分隔）')
    parser.add_argument('--max-rows', type=int, help='最大读取行数（可选，用于测试）')
    parser.add_argument('--dry-run', action='store_true', help='模拟运行（只统计，不实际创建）')
    parser.add_argument('--skip-site', action='store_true', help='跳过站点栏目/站点标签创建（只创建 DAM 集合/标签）')
    parser.add_argument('--skip-dam', action='store_true', help='跳过 DAM 集合/标签创建（只创建站点栏目/站点标签）')
    parser.add_argument('--delay', type=float, help='每次 API 操作之间的延迟（秒，默认：0.0）')
    parser.add_argument('--log-file', help='日志文件路径（可选）')
    parser.add_argument('--debug', action='store_true', help='启用调试模式（显示详细 HTTP 信息）')
    parser.add_argument('--skip-confirm', action='store_true', help='跳过参数确认提示（用于批量执行）')

    args = parser.parse_args()

    # --excel 与 --directory 二选一
    if bool(args.excel) == bool(args.directory):
        parser.error("必须且只能指定其一：--excel <文件路径> 或 --directory <目录路径>")

    # 确定待处理的 Excel 列表
    if args.directory:
        excel_files = get_excel_files_in_directory(args.directory)
        if not excel_files:
            raise SystemExit(f"目录下没有 .xlsx 文件：{args.directory}")
    else:
        if not os.path.exists(args.excel):
            raise SystemExit(f"Excel 文件不存在：{args.excel}")
        excel_files = [args.excel]

    # 加载配置
    config = None
    config_path = resolve_config_path(args.config)
    if config_path:
        config = load_config(config_path)

    # 参数合并（命令行优先）
    api_key = None
    base_url = None
    site_id = None
    start_row = 2
    path_column = 'E'
    path_prefix = None
    skip_directories: List[str] = []
    delay = 0.0
    log_file = args.log_file
    max_depth = 9

    if config:
        api_key = f"{config['api']['access_key']}:{config['api']['secret_key']}"
        base_url = config['api']['base_url']
        site_id = config.get('site_id') or None
        if site_id == 0:
            site_id = None
        start_row = config['import']['start_row']
        path_column = config['import']['columns']['path']
        path_prefix = config['import'].get('path_prefix')
        skip_directories = config['import'].get('skip_directories', [])
        log_file = log_file or config.get('logging', {}).get('log_file')
        delay = float(config.get('import', {}).get('delay', 0.0) or 0.0)
        max_depth = int(config.get('import', {}).get('max_depth', max_depth) or max_depth)
    else:
        if not args.api_key:
            raise SystemExit("必须提供 --api-key 或 --config 参数")
        api_key = args.api_key
        base_url = args.base_url or 'https://open.baklib.com/api/v1'
        site_id = args.site_id

    if args.base_url:
        base_url = args.base_url
    if args.site_id is not None:
        site_id = args.site_id
    if args.start_row is not None:
        start_row = args.start_row
    if args.path_column:
        path_column = args.path_column
    if args.path_prefix:
        path_prefix = args.path_prefix
    if args.delay is not None:
        delay = args.delay

    # 如果显式跳过站点，就忽略 site_id
    if args.skip_site:
        site_id = None

    logger = setup_logging(log_file=log_file, debug=args.debug)

    print("\n" + "=" * 80)
    print("[预创建参数确认]")
    print("=" * 80)
    if len(excel_files) == 1:
        print(f"[文件] Excel 文件路径: {excel_files[0]}")
    else:
        print(f"[目录] Excel 目录（共 {len(excel_files)} 个文件）: {args.directory}")
    if config_path:
        print(f"[配置] 配置文件路径: {config_path}")
    print(f"[API] API 基础地址: {base_url}")
    print(f"[站点] 站点 ID: {site_id if site_id else '（跳过站点操作）'}")
    print(f"[行] 开始行: {start_row}")
    print(f"[列] 文件路径列: {path_column}")
    print(f"[前缀] 路径前缀: {path_prefix or '无'}")
    print(f"[跳过] skip_directories: {len(skip_directories)}")
    print(f"[模式] dry-run: {'是' if args.dry_run else '否'}")
    print(f"[开关] 跳过站点: {'是' if args.skip_site else '否'}")
    print(f"[开关] 跳过 DAM: {'是' if args.skip_dam else '否'}")
    print(f"[延迟] 每次 API 操作延迟: {delay} 秒")
    print("=" * 80)

    if not args.skip_confirm:
        print("\n[警告] 请确认以上参数是否正确")
        print("按 Enter 键继续，其他任意键取消...")
        user_input = input().strip()
        if user_input != '':
            print("\n[取消] 操作已取消")
            raise SystemExit(0)

    # 初始化 API 模块
    dam_collections = None
    dam_tags = None
    dam_upload = None
    if not args.skip_dam:
        dam_collections = DAMCollections(api_key, base_url, debug=args.debug)
        dam_tags = DAMTags(api_key, base_url, debug=args.debug)
        dam_upload = DAMUpload(api_key, base_url, debug=args.debug)

    site_pages = None
    site_tags = None
    if site_id and (not args.skip_site):
        site_pages = SitePages(api_key, site_id, base_url, debug=args.debug)
        site_tags = SiteTags(api_key, site_id, base_url, debug=args.debug)

    # 查询系统限制参数（用于与导入脚本一致的路径处理）
    max_channel_depth: Optional[int] = None
    if dam_collections:
        try:
            dam_limits = dam_collections.get_limits(force_refresh=True)
            if dam_limits and dam_limits.get('max_depth'):
                max_depth = int(dam_limits.get('max_depth', max_depth))
        except Exception as e:
            logger.warning(f"查询 DAM 限制失败（继续使用配置/默认 max_depth={max_depth}）：{e}")

    if site_pages:
        try:
            # 与 import_files_to_dam_and_pages.py 保持一致：使用 SitePages 内部的栏目层级计算逻辑
            # （get_max_channel_depth 会基于站点 max_depth 为资源页预留层级空间）
            site_pages.get_limits(force_refresh=True)
            max_channel_depth = site_pages.get_max_channel_depth()
        except Exception as e:
            logger.warning(f"查询站点限制失败（继续使用 DAM max_depth={max_depth}）：{e}")

    # 测试连接（只要有一个目标端需要操作就测试）
    if dam_upload and (not args.dry_run):
        logger.info("测试 API 连接...")
        if not dam_upload.test_connection():
            raise SystemExit("API 连接测试失败，请检查 API 密钥和网络连接")
        logger.info("API 连接测试成功")

    normalized_skip_dirs, skip_dir_mapping = normalize_skip_directories(skip_directories)

    # PathProcessor：尽量与导入脚本保持一致的目录截断规则
    path_processor_max_depth = max_channel_depth if max_channel_depth is not None else max_depth
    logger.info(f"路径处理器 max_depth: {path_processor_max_depth}（站点栏目限制优先，其次 DAM 限制/配置）")
    path_processor = PathProcessor(max_depth=path_processor_max_depth, path_prefix=path_prefix)

    if args.dry_run:
        logger.info("dry-run 模式：只统计，不执行任何创建操作")
    else:
        logger.info(f"开始批量处理，共 {len(excel_files)} 个 Excel 文件")
    logger.info("=" * 80)

    total_scanned = 0
    total_skipped = 0
    total_pairs_created = 0

    for file_idx, excel_path in enumerate(excel_files, 1):
        logger.info("")
        logger.info(f"[{file_idx}/{len(excel_files)}] Excel: {os.path.basename(excel_path)}")

        excel_reader = ExcelReader(excel_path)
        try:
            file_list = excel_reader.read_file_list(
                start_row=start_row,
                path_column=path_column,
                status_column=None,
                dam_id_column=None,
                max_rows=args.max_rows
            )
            logger.info(f"  共读取 {len(file_list)} 条记录（状态为'成功'的行会被自动跳过）")
        finally:
            excel_reader.close()

        unique_pairs: Set[Tuple[str, str]] = set()
        scanned = 0
        skipped = 0

        for item in file_list:
            file_path = item['file_path']
            should_skip, matched = is_path_skipped(file_path, normalized_skip_dirs, path_prefix)
            if should_skip:
                skipped += 1
                continue
            scanned += 1
            tags_string = path_processor.extract_tags_from_path(file_path)
            target_dir = path_processor.get_target_directory(file_path)
            unique_pairs.add((tags_string or '', target_dir or ''))

        total_scanned += scanned
        total_skipped += skipped
        sorted_pairs = sorted(unique_pairs, key=lambda p: (p[1].count('/'), p[1], p[0]))
        logger.info(f"  参与扫描: {scanned}，跳过: {skipped}，唯一 (标签, 目录) 对: {len(sorted_pairs)}")

        if args.dry_run:
            continue

        for idx, (tags_string, target_dir) in enumerate(sorted_pairs, 1):
            logger.info(f"  [{idx}/{len(sorted_pairs)}] 标签: {tags_string or '(无)'} | 目录: {target_dir or '(无)'}")
            ensure_directories_and_tags(
                tags_string,
                target_dir,
                dam_collections=dam_collections,
                dam_tags=dam_tags,
                site_pages=site_pages,
                site_tags=site_tags,
            )
            total_pairs_created += 1
            if delay:
                time.sleep(delay)

    logger.info("")
    logger.info("=" * 80)
    logger.info("预创建完成")
    logger.info(f"处理 Excel 文件数: {len(excel_files)}，总扫描: {total_scanned}，总跳过: {total_skipped}")
    if not args.dry_run:
        logger.info(f"实际创建/命中缓存的 (标签, 目录) 项数: {total_pairs_created}")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()

