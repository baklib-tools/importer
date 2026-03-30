#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件路径处理模块

功能：
- 处理文件路径，提取标签和目录结构
- 标准化路径格式
- 支持路径前缀移除

维护：Baklib Tools
创建日期：2026-01-06
"""

import os
import re
from typing import List, Optional


class PathProcessor:
    """文件路径处理器"""
    
    def __init__(self, max_depth: int = 9, path_prefix: str = None):
        """
        初始化路径处理器
        
        Args:
            max_depth: 目录最大层级（超出层级的目录会作为标签）
            path_prefix: 路径前缀（要去掉的前缀，如 "FileServer/Share"），支持多个前缀用逗号分隔
        """
        self.max_depth = max_depth
        # 处理路径前缀配置（支持多个前缀，用逗号分隔）
        if path_prefix:
            self.path_prefixes = [
                self._normalize_path_prefix(p.strip()) 
                for p in path_prefix.split(',') 
                if p.strip()
            ]
        else:
            # 默认前缀（Windows 客户路径）
            self.path_prefixes = ['FileServer/Share']
    
    @staticmethod
    def _normalize_path_prefix(prefix: str) -> str:
        """
        标准化路径前缀（移除盘符、标准化分隔符）
        
        Args:
            prefix: 路径前缀（可能包含 Windows 盘符和反斜杠）
        
        Returns:
            标准化后的路径前缀（使用正斜杠，无盘符）
        """
        if not prefix:
            return prefix
        
        # 标准化路径分隔符（兼容 Windows 和 Mac/Linux）
        normalized = prefix.replace('\\', '/')
        
        # 移除 Windows 盘符（如 d: 或 C:）
        windows_drive_pattern = r'^([A-Za-z]):[/\\]?'
        match = re.match(windows_drive_pattern, normalized)
        if match:
            normalized = normalized[2:]  # 跳过 "d:" 或 "C:"
        
        # 移除开头和结尾的斜杠，统一格式
        normalized = normalized.strip('/')
        
        return normalized
    
    def extract_tags_from_path(self, file_path: str) -> str:
        """
        从文件路径提取标签
        
        根据客户规则：
        - 去掉前缀 d:\\FileServer\\Share\\
        - 每个目录名称都作为标签
        - 标签用 / 分隔
        
        Args:
            file_path: 文件路径
        
        Returns:
            标签字符串（用 / 分隔）
        """
        # 标准化路径分隔符（兼容 Windows 和 macOS/Linux）
        normalized_path = file_path.replace('\\', '/')
        
        # 移除盘符（Windows，如 d: 或 C:）
        windows_drive_pattern = r'^([A-Za-z]):[/\\]'
        match = re.match(windows_drive_pattern, normalized_path)
        if match:
            normalized_path = normalized_path[2:]  # 跳过 "d:" 或 "C:"
        
        # 去掉配置的路径前缀
        for prefix in self.path_prefixes:
            prefix_variants = [
                f'/{prefix}/',
                f'{prefix}/',
                f'/{prefix}',
                prefix
            ]
            for variant in prefix_variants:
                if normalized_path.startswith(variant):
                    normalized_path = normalized_path[len(variant):].lstrip('/')
                    break
            else:
                continue
            break
        
        # 分割路径
        path_parts = [p for p in normalized_path.split('/') if p]
        
        # 移除文件名，只保留目录
        if path_parts:
            path_parts = path_parts[:-1]
        
        # 用 / 分隔标签
        return '/'.join(path_parts) if path_parts else ''
    
    def get_target_directory(self, file_path: str) -> str:
        """
        获取目标目录（在系统限制内的层级）
        
        根据客户规则：
        - 去掉前缀 d:\\FileServer\\Share\\
        - 保持原目录结构，超出层级的目录被打平
        
        Args:
            file_path: 文件路径
        
        Returns:
            目标目录路径（相对路径）
        """
        # 标准化路径分隔符（兼容 Windows 和 macOS/Linux）
        normalized_path = file_path.replace('\\', '/')
        
        # 移除盘符（Windows，如 d: 或 C:）
        windows_drive_pattern = r'^([A-Za-z]):[/\\]'
        match = re.match(windows_drive_pattern, normalized_path)
        if match:
            normalized_path = normalized_path[2:]  # 跳过 "d:" 或 "C:"
        
        # 去掉配置的路径前缀
        for prefix in self.path_prefixes:
            prefix_variants = [
                f'/{prefix}/',
                f'{prefix}/',
                f'/{prefix}',
                prefix
            ]
            for variant in prefix_variants:
                if normalized_path.startswith(variant):
                    normalized_path = normalized_path[len(variant):].lstrip('/')
                    break
            else:
                continue
            break
        
        # 分割路径
        path_parts = [p for p in normalized_path.split('/') if p]
        
        # 移除文件名
        if path_parts:
            path_parts = path_parts[:-1]
        
        # 只保留前 max_depth 级目录
        if len(path_parts) > self.max_depth:
            path_parts = path_parts[:self.max_depth]
        
        # 重新组合为路径
        return '/'.join(path_parts) if path_parts else ''
    
    def get_file_name(self, file_path: str) -> str:
        """
        获取文件名（不含路径）
        
        Args:
            file_path: 文件路径
        
        Returns:
            文件名
        """
        return os.path.basename(file_path)
    
    def split_path_parts(self, path: str) -> List[str]:
        """
        分割路径为部分列表
        
        Args:
            path: 路径字符串（支持 / 和 \\ 分隔符）
        
        Returns:
            路径部分列表
        """
        normalized = path.replace('\\', '/')
        parts = [p for p in normalized.split('/') if p]
        return parts

