#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量执行文件导入脚本

功能：
- 遍历指定目录下的所有文件（不包含子文件夹）
- 逐个执行 import_files_to_dam_and_pages.py 脚本
- 如果执行成功，将文件移动到"已处理"子文件夹
- 如果执行失败，立即停止并报告错误

使用方式：
    python batch_import.py --directory <目录路径> --config <配置文件路径> [选项]

维护：Baklib Tools
创建日期：2026-01-06
"""

import os
import sys
import argparse
import subprocess
import logging
import shutil
from pathlib import Path
from typing import List, Optional
from datetime import datetime

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


def get_files_in_directory(directory: str) -> List[str]:
    """
    获取目录下的所有 Excel 文件（仅 *.xlsx，不包括子文件夹）
    
    Args:
        directory: 目录路径
        
    Returns:
        Excel 文件路径列表
    """
    files = []
    directory_path = Path(directory)
    
    if not directory_path.exists():
        raise FileNotFoundError(f"目录不存在：{directory}")
    
    if not directory_path.is_dir():
        raise ValueError(f"路径不是目录：{directory}")
    
    # 遍历目录下的所有项目
    for item in directory_path.iterdir():
        # 只处理文件，不包括子文件夹
        if item.is_file():
            # 只处理 .xlsx（大小写不敏感），并跳过 Office 临时锁文件（~$xxx.xlsx）
            if item.suffix.lower() != '.xlsx':
                continue
            if item.name.startswith('~$'):
                continue
            files.append(str(item.absolute()))
    
    # 按文件名排序：先按文件名长度排序，再按文件名排序
    # 这样可以确保 "图片文件路径-第20001-30000个.xlsx" 在 "图片文件路径-第110001-120000个.xlsx" 之前
    # 因为较短的文件名（较小的数字范围）会排在前面，相同长度的文件再按字符串排序
    # 排序键：(文件名长度, 文件名)，例如：(28, "图片文件路径-第20001-30000个.xlsx")
    files.sort(key=lambda f: (len(os.path.basename(f)), os.path.basename(f)))
    
    return files


def ensure_processed_directory(directory: str) -> str:
    """
    确保"已处理"子文件夹存在
    
    Args:
        directory: 主目录路径
        
    Returns:
        "已处理"子文件夹路径
    """
    processed_dir = os.path.join(directory, "已处理")
    os.makedirs(processed_dir, exist_ok=True)
    return processed_dir


def move_file_to_processed(source_file: str, processed_dir: str, logger: logging.Logger) -> bool:
    """
    将文件移动到"已处理"文件夹
    
    Args:
        source_file: 源文件路径
        processed_dir: "已处理"文件夹路径
        logger: 日志记录器
        
    Returns:
        是否成功
    """
    try:
        file_name = os.path.basename(source_file)
        destination = os.path.join(processed_dir, file_name)
        
        # 如果目标文件已存在，添加序号
        if os.path.exists(destination):
            base_name, ext = os.path.splitext(file_name)
            counter = 1
            while os.path.exists(destination):
                new_name = f"{base_name}_{counter}{ext}"
                destination = os.path.join(processed_dir, new_name)
                counter += 1
            logger.warning(f"  目标文件已存在，重命名为：{os.path.basename(destination)}")
        
        shutil.move(source_file, destination)
        logger.info(f"  ✓ 文件已移动到：{destination}")
        return True
    except Exception as e:
        logger.error(f"  ✗ 移动文件失败：{e}")
        return False


def execute_import_script(
    excel_file: str,
    config_file: str,
    script_path: str,
    extra_args: List[str],
    logger: logging.Logger,
    skip_confirm: bool = False
) -> int:
    """
    执行导入脚本
    
    Args:
        excel_file: Excel 文件路径
        config_file: 配置文件路径
        script_path: 导入脚本路径
        extra_args: 额外的命令行参数
        logger: 日志记录器
        skip_confirm: 是否跳过确认提示（用于批量执行）
        
    Returns:
        脚本的退出码（0 表示成功，非0 表示失败）
    """
    # 构建命令
    cmd = [
        sys.executable,
        script_path,
        '--excel', excel_file,
        '--config', config_file
    ]
    
    # 如果设置了跳过确认，添加 --skip-confirm 参数
    if skip_confirm:
        cmd.append('--skip-confirm')
    
    # 添加额外参数
    cmd.extend(extra_args)
    
    logger.info(f"  执行命令：{' '.join(cmd)}")
    
    try:
        # 确保子进程输出不被缓冲，便于定位卡在哪个文件
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")

        # 执行脚本
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(script_path),
            capture_output=False,  # 不捕获输出，让脚本直接输出到控制台
            text=True,
            env=env
        )
        
        return result.returncode
    except Exception as e:
        logger.error(f"  ✗ 执行脚本时发生异常：{e}")
        return 1


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='批量执行文件导入脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 基本用法
  python batch_import.py --directory ./excel_files --config config.json
  
  # 带额外参数
  python batch_import.py --directory ./excel_files --config config.json -- --dry-run
  
  # 启用调试模式
  python batch_import.py --directory ./excel_files --config config.json --debug
        """
    )
    
    parser.add_argument('--directory', required=True, help='包含 Excel 文件的目录路径')
    parser.add_argument(
        '--config',
        required=True,
        help='配置文件路径（JSON）；相对路径相对于项目根目录（与当前工作目录无关）',
    )
    parser.add_argument('--script', 
                       default='import_files_to_dam_and_pages.py',
                       help='导入脚本路径（默认：import_files_to_dam_and_pages.py）')
    parser.add_argument('--log-file', help='日志文件路径（可选）')
    parser.add_argument('--debug', action='store_true',
                       help='启用调试模式')
    parser.add_argument('--skip-move', action='store_true',
                       help='跳过文件移动（即使成功也不移动到"已处理"文件夹）')
    
    # 使用 -- 分隔符来传递额外参数给导入脚本
    args, extra_args = parser.parse_known_args()
    
    # 过滤掉 '--' 分隔符（如果存在）
    if '--' in extra_args:
        extra_args.remove('--')
    
    # 设置日志
    logger = setup_logging(args.log_file, debug=args.debug)

    config_path = resolve_config_path(args.config)

    logger.info("=" * 80)
    logger.info("批量文件导入脚本")
    logger.info("=" * 80)
    logger.info(f"目录路径：{args.directory}")
    logger.info(f"配置文件：{config_path}")
    logger.info(f"导入脚本：{args.script}")
    if extra_args:
        logger.info(f"额外参数：{' '.join(extra_args)}")
    logger.info("=" * 80)
    logger.info("")
    
    # 检查配置文件是否存在
    if not config_path or not os.path.exists(config_path):
        logger.error(f"配置文件不存在：{config_path or args.config}")
        sys.exit(1)
    
    # 检查导入脚本是否存在
    script_path = args.script
    if not os.path.isabs(script_path):
        # 如果是相对路径，相对于当前脚本所在目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(script_dir, script_path)
    
    if not os.path.exists(script_path):
        logger.error(f"导入脚本不存在：{script_path}")
        sys.exit(1)
    
    # 获取目录下的所有文件
    try:
        files = get_files_in_directory(args.directory)
        logger.info(f"找到 {len(files)} 个 .xlsx 文件")
    except Exception as e:
        logger.error(f"获取文件列表失败：{e}")
        sys.exit(1)
    
    if not files:
        logger.warning("目录中没有文件，退出")
        sys.exit(0)
    
    # 确保"已处理"文件夹存在
    processed_dir = None
    if not args.skip_move:
        processed_dir = ensure_processed_directory(args.directory)
        logger.info(f"已处理文件夹：{processed_dir}")
    
    logger.info("")
    logger.info("开始批量处理...")
    logger.info("=" * 80)
    
    # 统计信息
    stats = {
        'total': len(files),
        'success': 0,
        'failed': 0
    }
    
    # 处理每个文件
    interrupted = False
    try:
        for idx, file_path in enumerate(files, 1):
            file_name = os.path.basename(file_path)
            # 用 logger + print 双保险，避免日志配置/缓冲导致“看不到正在处理哪个文件”
            logger.info(f"\n[{idx}/{stats['total']}] 处理文件：{file_name}")
            logger.info(f"  完整路径：{file_path}")
            print(
                f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"[batch] ({idx}/{stats['total']}) 正在处理：{file_path}",
                flush=True
            )
            
            # 第一个文件需要确认，后续文件自动跳过确认
            skip_confirm = (idx > 1)
            if skip_confirm:
                logger.info(f"  [批量模式] 跳过参数确认提示")
            
            # 执行导入脚本
            exit_code = execute_import_script(
                excel_file=file_path,
                config_file=config_path,
                script_path=script_path,
                extra_args=extra_args,
                logger=logger,
                skip_confirm=skip_confirm
            )
            
            # 如果子脚本因 Ctrl+C 被中断（约定退出码 130），视为用户主动正常终止
            if exit_code == 130:
                logger.warning(f"  ⚠ 子脚本因用户 Ctrl+C 中断（退出码：{exit_code}），停止后续批量处理")
                logger.warning("  当前 Excel 中已处理的记录会保留，后续文件将不再处理")
                interrupted = True
                break
            
            # 检查执行结果
            if exit_code == 0:
                logger.info(f"  ✓ 文件处理成功")
                stats['success'] += 1
                
                # 移动到"已处理"文件夹
                if not args.skip_move and processed_dir:
                    if move_file_to_processed(file_path, processed_dir, logger):
                        logger.info(f"  ✓ 文件已移动到已处理文件夹")
                    else:
                        logger.warning(f"  ⚠ 文件处理成功但移动失败，请手动处理")
            else:
                logger.error(f"  ✗ 文件处理失败（退出码：{exit_code}）")
                stats['failed'] += 1
                logger.error("=" * 80)
                logger.error("处理失败，停止批量执行")
                logger.error("=" * 80)
                break
    except KeyboardInterrupt:
        # 用户直接在批处理脚本层面按下 Ctrl+C（例如在等待子脚本或下一轮开始前）
        logger.warning("")
        logger.warning("=" * 80)
        logger.warning("检测到用户按下 Ctrl+C，中断批量执行")
        logger.warning("当前 Excel 文件中已处理的记录会保留，后续文件将不再处理")
        logger.warning("=" * 80)
        interrupted = True
    
    # 输出统计信息
    logger.info("")
    logger.info("=" * 80)
    logger.info("批量处理完成！")
    logger.info(f"总计：{stats['total']}")
    logger.info(f"成功：{stats['success']}")
    logger.info(f"失败：{stats['failed']}")
    logger.info(f"已处理：{stats['success']} 个文件")
    if processed_dir:
        logger.info(f"已处理文件夹：{processed_dir}")
    logger.info("=" * 80)
    
    # 退出码
    # 注意：
    # - 如果是用户 Ctrl+C 主动中断（interrupted=True），视为“正常退出”，返回 0
    # - 只有在非中断情况下存在失败文件时才返回非 0
    if stats['failed'] > 0 and not interrupted:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
