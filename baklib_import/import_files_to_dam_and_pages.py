#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baklib 文件导入（核心实现）

说明：
- 本文件为“核心实现”，同时兼容历史入口 `import_files_to_dam_and_pages.py`。
- 推荐使用更清晰的两个入口脚本：
  - import_files_to_dam.py：仅导入到 DAM（不创建站点页面）
  - import_files_to_site.py：导入到站点页面（= DAM + Page）

功能：
- 从 Excel 文件读取文件路径列表
- 根据客户规则处理目录结构和标签
- 通过 Baklib API 将文件导入到 DAM 资源库
- （可选）在站点中创建对应栏目与资源页
- 记录导入日志和错误信息

使用方式（兼容）：
    python import_files_to_dam_and_pages.py --excel <Excel文件路径> --api-key <access_key:secret_key> --site-id <站点ID> [选项]

维护：Baklib Tools
"""

import os
import sys
import argparse
import json
import logging
import re
from typing import Dict, Optional, List
import time
from datetime import datetime

# 导入各个功能模块
from excel_reader import ExcelReader
from path_processor import PathProcessor
from dam_collections import DAMCollections
from dam_tags import DAMTags
from dam_upload import DAMUpload
from site_pages import SitePages
from site_tags import SiteTags
from create_directories_and_tags import ensure_directories_and_tags
from project_paths import resolve_config_path


# 配置日志
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
    
    # 尝试多种编码格式，自动处理 BOM
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'latin-1']
    
    for encoding in encodings:
        try:
            with open(config_path, 'r', encoding=encoding) as f:
                config = json.load(f)
            return config
        except UnicodeDecodeError:
            # 编码不匹配，尝试下一个
            continue
        except json.JSONDecodeError as e:
            # JSON 格式错误，抛出更详细的错误信息
            raise json.JSONDecodeError(
                f"配置文件 JSON 格式错误（使用 {encoding} 编码）：{e.msg}",
                e.doc,
                e.pos
            )
    
    # 所有编码都失败
    raise ValueError(
        f"无法读取配置文件：{config_path}。"
        f"已尝试的编码格式：{', '.join(encodings)}。"
        f"请确保文件是有效的 JSON 格式，并使用 UTF-8 或 GBK 编码。"
    )


def map_excel_path_to_local(
    file_path: str,
    excel_path_prefix: str,
    local_path_root: str,
) -> str:
    """
    将 Excel 中的路径（如 Windows 服务器路径）映射到本机实际路径。

    Args:
        file_path: Excel 中读取的路径，如 d:\\FileServer\\Share\\00-共享盘\\...
        excel_path_prefix: Excel 路径前缀，如 d:\\FileServer\\Share
        local_path_root: 本机对应根目录，如 /mnt/source-files（将服务器路径映射到本机调试目录时使用）

    Returns:
        映射后的本机路径；若无法匹配前缀则返回原路径。
    """
    if not excel_path_prefix or not local_path_root:
        return file_path
    normalized = file_path.replace('\\', '/')
    # 去掉 Windows 盘符
    if re.match(r'^[A-Za-z]:[/\\]', normalized):
        normalized = normalized[2:]
    normalized = normalized.lstrip('/')
    prefix_norm = PathProcessor._normalize_path_prefix(excel_path_prefix)
    if not normalized.startswith(prefix_norm + '/') and normalized != prefix_norm:
        return file_path
    rest = normalized[len(prefix_norm):].lstrip('/')
    return (local_path_root.rstrip('/') + '/' + rest) if rest else local_path_root.rstrip('/')


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Baklib DAM 文件导入和页面创建脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 使用配置文件
  python import_files_to_dam_and_pages.py --excel file_list.xlsx --config config.json
  # （config.json 放在项目根目录；相对路径相对项目根，与当前工作目录无关）
  
  # 模拟运行（不实际上传）
  python import_files_to_dam_and_pages.py --excel file_list.xlsx --api-key "access_key:secret_key" --site-id 123 --dry-run
  
  # 实际导入
  python import_files_to_dam_and_pages.py --excel file_list.xlsx --api-key "access_key:secret_key" --site-id 123
  
  # 测试导入（只导入前10条记录）
  python import_files_to_dam_and_pages.py --excel file_list.xlsx --api-key "access_key:secret_key" --site-id 123 --max-rows 10
        """
    )
    
    parser.add_argument('--excel', required=True, help='Excel 文件路径')
    parser.add_argument(
        '--config',
        help='配置文件路径（JSON，可选）；相对路径相对于项目根目录（与当前工作目录无关）',
    )
    parser.add_argument('--api-key', help='API 密钥（格式：access_key:secret_key，如果使用配置文件则不需要）')
    parser.add_argument('--site-id', type=int, help='站点 ID（如果使用配置文件则从配置文件读取）')
    parser.add_argument('--base-url', 
                       help='API 基础地址（如果使用配置文件则从配置文件读取）')
    parser.add_argument('--start-row', type=int, 
                       help='开始行（默认：2，第1行是标题）')
    parser.add_argument('--path-column', 
                       help='文件路径列（默认：E）')
    parser.add_argument('--status-column', 
                       help='导入状态列（如果未指定，无表头「导入状态」时自动插入到最左侧）')
    parser.add_argument('--dam-id-column', 
                       help='DAM ID列（如果未指定，无表头「DAM ID」时紧挨状态列自动插入）')
    parser.add_argument('--delay', type=float, 
                       help='每次上传之间的延迟（秒，默认：0.5）')
    parser.add_argument('--path-prefix', 
                       help='路径前缀（要去掉的前缀，如 "FileServer/Share"，支持多个用逗号分隔）')
    parser.add_argument('--dry-run', action='store_true', 
                       help='模拟运行（不实际上传）')
    parser.add_argument('--max-rows', type=int,
                       help='最大导入行数（可选，用于测试）')
    parser.add_argument('--log-file', help='日志文件路径（可选）')
    parser.add_argument('--debug', action='store_true',
                       help='启用调试模式（显示详细的 HTTP 请求信息）')
    parser.add_argument('--skip-pages', action='store_true',
                       help='跳过页面创建（仅导入到 DAM）')
    parser.add_argument('--skip-confirm', action='store_true',
                       help='跳过参数确认提示（用于批量执行）')
    parser.add_argument('--save-every', type=int,
                       help='Excel 批量保存间隔（行数，默认：10）')
    parser.add_argument('--save-interval', type=float,
                       help='Excel 定时保存间隔（秒，默认：30）')
    
    args = parser.parse_args()

    config_path = resolve_config_path(args.config)

    # 加载配置文件（如果提供）
    config = None
    if config_path:
        config = load_config(config_path)
        logger_temp = setup_logging(None)
        logger_temp.info(f"已加载配置文件：{config_path}")
    
    # 从配置文件或命令行参数获取配置值
    api_key = None
    base_url = None
    site_id = None
    start_row = 2
    path_column = 'E'
    max_depth = 9
    delay = 0.5
    path_prefix = None
    excel_path_prefix = None
    local_path_root = None
    skip_directories = []
    log_file = None
    save_every = 10
    save_interval = 30.0
    
    if config:
        # 从配置文件读取
        api_key = f"{config['api']['access_key']}:{config['api']['secret_key']}"
        base_url = config['api']['base_url']
        site_id = config.get('site_id')
        # 如果配置文件中 site_id 为 0 或 None，需要从命令行参数获取
        if not site_id or site_id == 0:
            site_id = None
        start_row = config['import']['start_row']
        path_column = config['import']['columns']['path']
        max_depth = config['import']['max_depth']
        delay = config['import']['delay']
        path_prefix = config['import'].get('path_prefix')
        excel_path_prefix = config['import'].get('excel_path_prefix')
        local_path_root = config['import'].get('local_path_root')
        skip_directories = config['import'].get('skip_directories', [])
        log_file = config['logging'].get('log_file')
    else:
        # 从命令行参数读取
        if not args.api_key:
            parser.error("必须提供 --api-key 或 --config 参数（配置文件放在项目根目录，见 --help）")
        api_key = args.api_key
        base_url = args.base_url or 'https://open.baklib.com/api/v1'
        if not args.site_id:
            parser.error("必须提供 --site-id 或 --config 参数（包含 site_id）")
        site_id = args.site_id
    
    # 命令行参数优先（覆盖配置文件）
    if args.base_url:
        base_url = args.base_url
    if args.start_row is not None:
        start_row = args.start_row
    if args.path_column:
        path_column = args.path_column
    if args.site_id:
        site_id = args.site_id
    if args.delay is not None:
        delay = args.delay
    if args.path_prefix:
        path_prefix = args.path_prefix
    if args.log_file:
        log_file = args.log_file
    if args.save_every is not None:
        save_every = args.save_every
    if args.save_interval is not None:
        save_interval = args.save_interval
    
    # 标准化跳过目录列表（统一路径格式）
    # 注意：skip_directories 是相对于 path_prefix 的相对路径，不需要包含 path_prefix
    # 保存原始路径和标准化路径的映射，用于日志显示
    normalized_skip_dirs = []
    skip_dir_mapping = {}  # {normalized: original}
    for skip_dir in skip_directories:
        # 标准化路径分隔符和格式
        normalized = skip_dir.replace('\\', '/')
        # 移除开头和结尾的斜杠
        normalized = normalized.strip('/')
        if normalized:
            normalized_lower = normalized.lower()  # 转换为小写以便比较
            normalized_skip_dirs.append(normalized_lower)
            skip_dir_mapping[normalized_lower] = skip_dir  # 保存原始路径
    
    # 设置日志
    logger = setup_logging(log_file, debug=args.debug)
    
    if args.debug:
        logger.info("=" * 80)
        logger.info("调试模式已启用，将显示详细的 HTTP 请求和响应信息")
        logger.info("=" * 80)
    
    # 初始化模块（用于查询限制参数）
    logger.info("初始化模块并查询系统限制参数...")
    
    # 1. DAM 集合管理器（用于查询限制参数）
    dam_collections = DAMCollections(api_key, base_url, debug=args.debug)
    
    # 2. 站点页面管理器（用于查询限制参数）
    site_pages = None
    if not args.skip_pages:
        site_pages = SitePages(api_key, site_id, base_url, debug=args.debug)
    
    # 3. DAM 文件上传器（用于测试连接）
    dam_upload = DAMUpload(api_key, base_url, debug=args.debug)
    
    # 4. 站点标签管理器（用于创建站点标签和给页面打标签）
    site_tags = None
    if not args.skip_pages:
        site_tags = SiteTags(api_key, site_id, base_url, debug=args.debug)
    
    # 测试 API 连接并查询限制参数
    logger.info("测试 API 连接...")
    try:
        if not dam_upload.test_connection():
            logger.error("API 连接测试失败，请检查 API 密钥和网络连接")
            sys.exit(1)
        logger.info("API 连接测试成功")
    except Exception as e:
        logger.error(f"API 连接测试失败：{e}")
        sys.exit(1)
    
    # 查询限制参数（在参数确认之前）
    logger.info("")
    logger.info("=" * 80)
    logger.info("查询系统限制参数（启动时仅查询一次）...")
    logger.info("=" * 80)
    
    # 查询 DAM 集合限制（force_refresh=True 表示启动时查询）
    dam_limits = dam_collections.get_limits(force_refresh=True)
    if dam_limits:
        # 从系统限制参数中获取目录最大层级（用于路径处理）
        system_max_depth = dam_limits.get('max_depth', max_depth)
        max_depth = system_max_depth  # 使用系统决定的 max_depth
        logger.info(f"✓ DAM 集合限制：")
        logger.info(f"  - 最大数量: {dam_limits.get('max_count', 'N/A')}")
        logger.info(f"  - 最大层级: {dam_limits.get('max_depth', 'N/A')}")
        logger.info(f"  - 当前数量: {dam_limits.get('current_count', 'N/A')}")
        logger.info(f"  - 当前最大层级: {dam_limits.get('current_max_depth', 'N/A')}")
    else:
        logger.warning("⚠ 无法获取 DAM 集合限制，将使用配置值")
    
    # 查询站点限制（force_refresh=True 表示启动时查询）
    max_channel_depth = None
    if site_pages:
        site_limits = site_pages.get_limits(force_refresh=True)
        if site_limits:
            site_max_depth = site_limits.get('max_depth', 6)
            max_channel_depth = site_max_depth - 1  # 站点栏目的最大层级
            logger.info(f"✓ 站点限制：")
            logger.info(f"  - 最大数量: {site_limits.get('max_count', 'N/A')}")
            logger.info(f"  - 最大层级: {site_max_depth}")
            logger.info(f"  - 当前数量: {site_limits.get('current_count', 'N/A')}")
            logger.info(f"  - 当前最大层级: {site_limits.get('current_max_depth', 'N/A')}")
            logger.info(f"  - 站点栏目最大层级: {max_channel_depth}（最大层级 - 1，为资源页面留出空间）")
        else:
            logger.warning("⚠ 无法获取站点限制，将使用默认值")
    
    logger.info("=" * 80)
    logger.info("注意：限制参数已缓存，后续将动态更新计数，不再查询API")
    logger.info("=" * 80)
    logger.info("")
    
    # 显示所有输入参数并等待用户确认
    print("\n" + "=" * 80)
    print("[导入参数确认]")
    print("=" * 80)
    print(f"[文件] Excel 文件路径: {args.excel}")
    if config_path:
        print(f"[配置] 配置文件路径: {config_path}")
    print(f"[API] API 基础地址: {base_url}")
    print(f"[站点] 站点 ID: {site_id}")
    print(f"[行] 开始行: {start_row}")
    print(f"[列] 文件路径列: {path_column}")
    if args.status_column:
        print(f"[状态] 状态列: {args.status_column}")
    if args.dam_id_column:
        print(f"[ID] DAM ID列: {args.dam_id_column}")
    
    # 显示 DAM 集合限制
    print("\n[DAM 集合限制]")
    if dam_limits:
        print(f"  - 最大数量: {dam_limits.get('max_count', 'N/A')}")
        print(f"  - 最大层级: {dam_limits.get('max_depth', 'N/A')}")
        print(f"  - 当前数量: {dam_limits.get('current_count', 'N/A')}")
        print(f"  - 当前最大层级: {dam_limits.get('current_max_depth', 'N/A')}")
        if max_channel_depth is not None:
            print(f"  - 路径处理器最大层级: {max_channel_depth}（由站点栏目最大层级决定，用于创建站点栏目）")
        else:
            print(f"  - 路径处理器最大层级: {max_depth}（由 DAM 集合最大层级决定）")
    else:
        print("  - 无法获取限制信息，使用默认值")
    
    # 显示站点限制
    if site_pages and site_limits:
        print("\n[站点页面限制]")
        print(f"  - 最大数量: {site_limits.get('max_count', 'N/A')}")
        print(f"  - 最大层级: {site_limits.get('max_depth', 'N/A')}")
        print(f"  - 当前数量: {site_limits.get('current_count', 'N/A')}")
        print(f"  - 当前最大层级: {site_limits.get('current_max_depth', 'N/A')}")
        if max_channel_depth is not None:
            print(f"  - 站点栏目最大层级: {max_channel_depth}（最大层级 - 1，为资源页面留出空间）")
    elif site_pages:
        print("\n[站点页面限制]")
        print("  - 无法获取限制信息，使用默认值")
    
    print("\n[其他参数]")
    print(f"[延迟] 行间延迟: {delay} 秒（每条记录主要耗时在上传文件到 DAM，可用 --delay 0 关闭行间延迟以提速）")
    if path_prefix:
        print(f"[前缀] 路径前缀（将被移除）: {path_prefix}")
    else:
        print(f"[前缀] 路径前缀: 无")
    if excel_path_prefix and local_path_root:
        print(f"[映射] Excel 路径前缀: {excel_path_prefix}")
        print(f"[映射] 本机路径根目录: {local_path_root}")
    else:
        print(f"[映射] 路径映射: 无")
    if normalized_skip_dirs:
        print(f"[跳过] 跳过目录数量: {len(normalized_skip_dirs)}")
        for skip_dir in skip_directories:
            print(f"        - {skip_dir}")
    else:
        print(f"[跳过] 跳过目录: 无")
    print(f"[测试] 模拟运行: {'是' if args.dry_run else '否'}")
    print(f"[页面] 跳过页面创建: {'是' if args.skip_pages else '否'}")
    if args.max_rows:
        print(f"[数量] 最大导入行数: {args.max_rows}")
    if log_file:
        print(f"[日志] 日志文件: {log_file}")
    print(f"[调试] 调试模式: {'是' if args.debug else '否'}")
    print(f"[保存] 批量保存间隔: {save_every} 行")
    print(f"[保存] 定时保存间隔: {save_interval} 秒")
    if delay >= 5:
        print(f"\n[注意] 行间延迟为 {delay} 秒，较大；若需提速请设置 --delay 0 或配置 import.delay 为 0")
    print("=" * 80)
    
    # 如果设置了 --skip-confirm，跳过确认提示
    if args.skip_confirm:
        print("\n[自动确认] 跳过参数确认（批量执行模式）\n")
    else:
        print("\n[警告] 请确认以上参数是否正确")
        print("按 Enter 键继续，其他任意键取消...")
        
        try:
            user_input = input().strip()
            if user_input != '':
                print("\n[取消] 操作已取消")
                sys.exit(0)
        except (KeyboardInterrupt, EOFError):
            print("\n\n[取消] 操作已取消")
            sys.exit(0)
        
        print("\n[成功] 继续执行导入...\n")
    
    # 初始化其他模块（在用户确认后）
    logger.info("初始化其他模块...")
    
    # 初始化变量（确保在 finally 块中可访问）
    excel_reader = None
    stats = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'skipped': 0
    }
    imported_files = []
    failed_files = []
    
    # 1. Excel 读取器（使用 try-finally 确保总是被关闭）
    try:
        excel_reader = ExcelReader(args.excel)
        excel_reader.create_backup()
        
        # 确保 max_channel_depth 已设置（如果创建页面）
        if site_pages and max_channel_depth is None:
            max_channel_depth = site_pages.get_max_channel_depth()
        
        # 2. 路径处理器（使用站点栏目的最大层级，而不是 DAM 集合的最大层级）
        # 因为站点栏目的层级限制更严格（需要为资源页面留出空间）
        path_processor_max_depth = max_channel_depth if max_channel_depth is not None else max_depth
        if max_channel_depth is not None:
            logger.info(f"路径处理器使用站点栏目最大层级: {path_processor_max_depth}（站点栏目限制）")
        else:
            logger.info(f"路径处理器使用 DAM 集合最大层级: {path_processor_max_depth}（DAM 集合限制）")
        # 使用 local_path_root 时，路径处理器用本地根作为 path_prefix（用于提取相对路径/标签）
        path_prefix_for_processor = (local_path_root if local_path_root else path_prefix)
        path_processor = PathProcessor(max_depth=path_processor_max_depth, path_prefix=path_prefix_for_processor)
        
        # 3. DAM 标签管理器
        dam_tags = DAMTags(api_key, base_url, debug=args.debug)
        
        # 4. 站点标签管理器（如果创建页面）
        if not args.skip_pages and site_tags is None:
            site_tags = SiteTags(api_key, site_id, base_url, debug=args.debug)
        
        # 读取文件列表
        logger.info("读取文件列表...")
        file_list = excel_reader.read_file_list(
            start_row=start_row,
            path_column=path_column,
            status_column=args.status_column,
            dam_id_column=args.dam_id_column,
            max_rows=args.max_rows
        )
        # 将 Excel 中的路径映射到本机路径（如 Windows 服务器路径 → 本地挂载目录）
        if excel_path_prefix and local_path_root:
            for file_info in file_list:
                file_info['file_path'] = map_excel_path_to_local(
                    file_info['file_path'],
                    excel_path_prefix,
                    local_path_root,
                )
            logger.info(f"已启用路径映射：Excel 前缀 {excel_path_prefix!r} → 本地 {local_path_root!r}")
        logger.info(f"共读取 {len(file_list)} 个文件")
        
        # 更新统计信息
        stats['total'] = len(file_list)
        stats['success'] = 0
        stats['failed'] = 0
        stats['skipped'] = 0
        
        imported_files = []
        failed_files = []

        # 保存节流控制（减少频繁保存导致的性能问题）
        last_save_time = time.time()
        pending_save = False
        processed_since_save = 0

        def mark_dirty():
            nonlocal pending_save
            pending_save = True

        def maybe_save(force: bool = False, reason: str = ''):
            nonlocal last_save_time, pending_save, processed_since_save
            if not pending_save and not force:
                return
            now = time.time()
            if force or processed_since_save >= save_every or (now - last_save_time) >= save_interval:
                excel_reader.save()
                last_save_time = now
                pending_save = False
                processed_since_save = 0
                if reason:
                    logger.debug(f"Excel 已保存（{reason}）")
        
        # 处理每个文件
        for idx, file_info in enumerate(file_list, 1):
            row_idx = file_info['row_idx']
            file_path = file_info['file_path']
            
            logger.info(f"\n[{idx}/{stats['total']}] 处理文件：{file_path}")
            
            # 检查文件是否在跳过目录中（skip_directories 为相对路径，需先去掉路径前缀得到相对路径再比较）
            if normalized_skip_dirs:
                # 标准化文件路径（统一格式以便比较）
                normalized_file_path = file_path.replace('\\', '/')
                # 移除 Windows 盘符
                windows_drive_pattern = r'^([A-Za-z]):[/\\]?'
                match = re.match(windows_drive_pattern, normalized_file_path)
                if match:
                    normalized_file_path = normalized_file_path[2:]
                
                # 移除路径前缀得到相对路径（与 path_processor 一致：有 local_path_root 用本地根，否则用 path_prefix）
                prefix_to_strip = local_path_root if local_path_root else path_prefix
                if prefix_to_strip:
                    normalized_prefix = prefix_to_strip.replace('\\', '/')
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
                        if normalized_file_path.startswith(variant):
                            normalized_file_path = normalized_file_path[len(variant):].lstrip('/')
                            break
                
                normalized_file_path = normalized_file_path.strip('/').lower()
                
                # 检查文件路径是否以任何跳过目录开头
                should_skip = False
                matched_skip_dir = None
                for skip_dir in normalized_skip_dirs:
                    # 检查完整路径是否以跳过目录开头（包括子目录）
                    if normalized_file_path.startswith(skip_dir + '/') or normalized_file_path == skip_dir:
                        should_skip = True
                        matched_skip_dir = skip_dir
                        break
                
                if should_skip:
                    # 获取原始跳过目录路径用于日志显示
                    original_skip_dir = skip_dir_mapping.get(matched_skip_dir, matched_skip_dir)
                    logger.info(f"  ⏭ 跳过：文件在跳过目录中（{original_skip_dir}）")
                    excel_reader.update_status(row_idx, '跳过', '')
                    mark_dirty()
                    processed_since_save += 1
                    maybe_save()
                    stats['skipped'] += 1
                    continue
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"  文件不存在：{file_path}")
                excel_reader.update_status(row_idx, f"失败：文件不存在", '')
                mark_dirty()
                processed_since_save += 1
                maybe_save()
                stats['failed'] += 1
                failed_files.append({
                    'file_path': file_path,
                    'error': '文件不存在'
                })
                continue
            
            # 从路径提取标签和目录
            tags_string = path_processor.extract_tags_from_path(file_path)
            target_dir = path_processor.get_target_directory(file_path)
            file_name = path_processor.get_file_name(file_path)
            
            logger.info(f"  标签：{tags_string}")
            logger.info(f"  目录：{target_dir}")
            
            if args.dry_run:
                logger.info(f"  [模拟] 准备导入到 DAM...")
                if not args.skip_pages:
                    logger.info(f"  [模拟] 准备创建页面...")
                excel_reader.update_status(row_idx, '模拟', '')
                mark_dirty()
                processed_since_save += 1
                maybe_save()
                stats['success'] += 1
                continue
            
            
            try:
                # 1. 创建或获取目录与标签（与 prepare_directories_and_tags 共用逻辑，同路径结果会缓冲，减少重复 API）
                dir_tag_result = ensure_directories_and_tags(
                    tags_string,
                    target_dir,
                    dam_collections=dam_collections,
                    dam_tags=dam_tags,
                    site_pages=site_pages if not args.skip_pages else None,
                    site_tags=site_tags if not args.skip_pages else None,
                )
                tag_ids = dir_tag_result['tag_ids']
                collection_id = dir_tag_result['collection_id']
                site_tag_ids = dir_tag_result['site_tag_ids']
                channel_parent_id = dir_tag_result['channel_parent_id']

                # 2. 上传文件到 DAM（获取 signed_id）；上传可能需数秒至十余秒，期间无其他日志属正常
                logger.info(f"  上传文件到 DAM...（上传中，请稍候）")
                upload_start = time.time()
                upload_result = dam_upload.upload_file(
                    file_path=file_path,
                    name=file_name,
                    tag_ids=tag_ids if tag_ids else None,
                    collection_ids=[int(collection_id)] if collection_id else None,
                    include_signed_id=True,
                    purpose='dynamic_form'
                )
                upload_elapsed = time.time() - upload_start
                # 获取文件 ID 和 signed_id
                file_data = upload_result.get('data', {})
                file_attributes = file_data.get('attributes', {})
                file_id = file_data.get('id', '')
                signed_id = file_attributes.get('signed_id', '')
                
                if not file_id:
                    raise Exception("上传成功但未返回文件 ID")
                
                if not signed_id:
                    raise Exception("上传成功但未返回 signed_id")
                
                logger.info(f"  ✓ DAM 上传成功，耗时 {upload_elapsed:.1f}s，文件 ID: {file_id}, signed_id: {signed_id[:50]}...")
                
                # 重要：在上传成功后立即更新状态为"成功"并保存，防止中断导致重复导入
                # 即使后续创建页面失败，文件也已经成功导入到DAM，不会重复导入
                excel_reader.update_status(row_idx, '成功', file_id)
                mark_dirty()
                processed_since_save += 1
                # 成功状态立即保存，避免 Ctrl+C 导致重复导入
                maybe_save(force=True, reason='成功状态立即保存')
                logger.debug(f"  状态已更新为'成功'并保存（防止中断导致重复导入）")
                
                # 4. 创建站点页面（如果不跳过）；目录/标签已在步骤 1 通过 ensure_directories_and_tags 创建并缓冲
                page_id = None
                if not args.skip_pages and site_pages:
                    # channel_parent_id 为空说明栏目路径未创建成功（无目标目录或创建失败），不能传空给 API
                    if channel_parent_id is None:
                        logger.error(
                            f"  channel_parent_id 为空，说明栏目路径未创建成功（当前目标目录: {target_dir!r}；"
                            "无目录或 ensure_directories_and_tags 中栏目创建失败），跳过创建资源页面"
                        )
                    else:
                        logger.info(f"  创建站点页面...")
                        
                        # 获取文件的创建时间
                        try:
                            file_stat = os.stat(file_path)
                            # 获取文件的创建时间（macOS 使用 st_birthtime，Linux 使用 st_ctime）
                            if hasattr(file_stat, 'st_birthtime'):
                                file_created_time = file_stat.st_birthtime
                            else:
                                file_created_time = file_stat.st_ctime
                            
                            # 格式化为 "YYYY-MM-DD HH:mm" 格式
                            published_at = datetime.fromtimestamp(file_created_time).strftime("%Y-%m-%d %H:%M")
                            logger.info(f"  文件创建时间: {published_at}")
                        except Exception as e:
                            logger.warning(f"  无法获取文件创建时间: {e}，使用当前时间")
                            published_at = datetime.now().strftime("%Y-%m-%d %H:%M")
                        
                        # 创建资源页面（使用 DAM 资源 ID 作为 slug）；site_tag_ids、channel_parent_id 来自步骤 1
                        # 此处 channel_parent_id 已保证非空（为空时已在上方跳过）
                        parent_channel_name = site_pages.get_channel_name(channel_parent_id)
                        if parent_channel_name:
                            logger.info(f"  准备创建资源页面，父级栏目 ID: {channel_parent_id}，栏目名称: '{parent_channel_name}'")
                        else:
                            logger.info(f"  准备创建资源页面，父级栏目 ID: {channel_parent_id}")
                        
                        # 创建页面时直接传入标签ID列表（注意：站点栏目不需要打标签，只给资源页面打标签）
                        page_result = site_pages.create_resource_page(
                            name=file_name,
                            asset_signed_id=signed_id,
                            dam_resource_id=int(file_id),  # 使用 DAM 资源 ID 作为 slug
                            parent_id=channel_parent_id,
                            description=f"资源文件：{file_name}",
                            resource_tags=site_tag_ids if site_tag_ids else None,  # 在创建时传入标签ID列表
                            published=True,
                            published_at=published_at
                        )
                        
                        if page_result:
                            page_data = page_result.get('data', {})
                            page_id = page_data.get('id')
                            if page_id:
                                if site_tag_ids:
                                    logger.info(f"  ✓ 页面创建成功，页面 ID: {page_id}，已打上标签：{site_tag_ids}")
                                else:
                                    logger.info(f"  ✓ 页面创建成功，页面 ID: {page_id}")
                            else:
                                logger.warning(f"  ⚠ 页面创建返回了结果但未包含页面 ID")
                        else:
                            logger.warning(f"  ⚠ 页面创建失败，但 DAM 上传成功（状态已标记为成功，不会重复导入）")
                
                # 注意：状态已在DAM上传成功后立即更新并保存，这里只需要更新统计
                stats['success'] += 1
                imported_files.append({
                    'file_path': file_path,
                    'file_id': file_id,
                    'signed_id': signed_id,
                    'page_id': page_id,
                    'tags': tags_string,
                    'collection_id': collection_id
                })
                
                logger.info(f"  ✓ 处理完成")
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"  ✗ 处理失败：{error_msg}")
                excel_reader.update_status(row_idx, f"失败：{error_msg[:50]}", '')
                mark_dirty()
                processed_since_save += 1
                maybe_save()
                stats['failed'] += 1
                failed_files.append({
                    'file_path': file_path,
                    'error': error_msg
                })
            
            # 行间延迟（可选）；每条记录主要耗时在上传文件到 DAM，非本延迟
            if delay > 0 and idx < stats['total']:
                logger.info(f"  [行间延迟] 等待 {delay} 秒（可用 --delay 0 关闭以提速）")
                time.sleep(delay)
    except KeyboardInterrupt:
        # 捕获 Ctrl+C 中断，确保数据已保存
        logger.warning("\n" + "=" * 80)
        logger.warning("⚠ 用户中断操作（Ctrl+C）")
        logger.warning("=" * 80)
        if stats['total'] > 0:
            logger.warning(f"已处理进度：{stats['success'] + stats['failed']}/{stats['total']}")
            logger.warning(f"成功：{stats['success']}，失败：{stats['failed']}")
        logger.warning("正在保存 Excel 文件...")
        try:
            maybe_save(force=True, reason='用户中断')
        except Exception as e:
            logger.warning(f"保存 Excel 文件时发生错误：{e}")
        # 注意：保存操作在 finally 块中执行
        raise  # 重新抛出异常，让外层处理
    finally:
        # 确保 Excel 文件总是被保存和关闭，即使发生异常（包括 Ctrl+C）
        if excel_reader:
            try:
                # 先保存文件，确保已处理的记录不丢失
                try:
                    maybe_save(force=True, reason='最终保存')
                    logger.info("✓ Excel 文件已保存（防止数据丢失）")
                except NameError:
                    # 当异常发生在 helper 初始化之前，回退到直接保存
                    excel_reader.save()
                    logger.info("✓ Excel 文件已保存（防止数据丢失）")
            except Exception as e:
                logger.warning(f"保存 Excel 文件时发生错误：{e}")
            try:
                excel_reader.close()
                logger.debug("Excel 文件已关闭")
            except Exception as e:
                logger.warning(f"关闭 Excel 文件时发生错误：{e}")
    
    # 输出统计信息
    logger.info(f"\n" + "=" * 80)
    logger.info(f"导入完成！")
    logger.info(f"总计：{stats['total']}")
    logger.info(f"成功：{stats['success']}")
    logger.info(f"失败：{stats['failed']}")
    logger.info(f"跳过：{stats['skipped']}")
    logger.info(f"Excel 文件已更新：{args.excel}")
    logger.info("=" * 80)
    
    # 保存结果
    if log_file:
        result_file = log_file.replace('.log', '_result.json')
        result = {
            'stats': stats,
            'imported_files': imported_files,
            'failed_files': failed_files
        }
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"导入结果已保存到：{result_file}")
    
    # 退出码
    # 注意：即使有部分文件失败，只要 Excel 文件处理完成（所有行都处理过了），
    # 也返回成功（exit_code=0），让批量处理可以继续处理下一个文件
    # 失败信息已经记录在 Excel 文件的状态列中，可以通过日志查看
    if stats['total'] == 0:
        # 如果没有处理任何文件，返回失败
        logger.warning("⚠ 没有处理任何文件，可能 Excel 文件为空或格式错误")
        sys.exit(1)
    else:
        # 只要处理了文件（无论成功或失败），都返回成功，让批量处理继续
        if stats['failed'] > 0:
            logger.warning(f"⚠ 有 {stats['failed']} 个文件处理失败，但 Excel 文件已更新，批量处理将继续")
        sys.exit(0)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        # 捕获 Ctrl+C 中断，确保数据已保存
        print("\n\n[中断] 用户中断操作（Ctrl+C）")
        print("[提示] 已处理的记录已保存到 Excel 文件，可以继续处理")
        sys.exit(130)  # 130 是标准的 Ctrl+C 退出码
    except Exception as e:
        # 捕获其他未预期的异常
        logging.error(f"程序发生未预期的错误：{e}", exc_info=True)
        sys.exit(1)

