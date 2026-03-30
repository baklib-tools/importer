#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DAM 集合管理模块

功能：
- 创建和管理 DAM 集合
- 支持层级集合创建
- 缓存集合 ID

维护：Baklib Tools
创建日期：2026-01-06
"""

import logging
import json
from typing import Dict, List, Optional, Tuple
import requests


class DAMCollections:
    """DAM 集合管理器"""
    
    def __init__(self, api_key: str, base_url: str = "https://open.baklib.com/api/v1", debug: bool = False):
        """
        初始化集合管理器
        
        Args:
            api_key: API 密钥，格式为 "access_key:secret_key"
            base_url: API 基础地址
            debug: 是否启用调试模式
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.debug = debug
        self.session.headers.update({
            'Authorization': api_key,
            'Content-Type': 'application/json'
        })
        # 集合的映射缓存（名称 -> ID）
        self._collection_name_to_id_cache: Dict[str, str] = {}
        # 集合路径缓存（完整路径 -> 最深层级ID）
        self._collection_path_to_id_cache: Dict[str, str] = {}
        # 限制信息缓存
        self._limits_cache: Optional[Dict] = None

    def get_limits(self, force_refresh: bool = False) -> Optional[Dict]:
        """
        获取 DAM 集合的限制参数（仅在首次调用时查询API，之后使用缓存）
        
        Args:
            force_refresh: 是否强制刷新（默认 False，只在启动时使用）
        
        Returns:
            限制信息字典，包含 max_count, max_depth, current_count, current_max_depth
        """
        if self._limits_cache is not None and not force_refresh:
            return self._limits_cache
        
        try:
            url = f"{self.base_url}/dam/collections/limits"
            response = self.session.get(url)
            response.raise_for_status()
            
            result = response.json()
            limits_data = result.get('data', {})
            self._limits_cache = limits_data
            if force_refresh:
                logging.info(f"DAM 集合限制：最大数量={limits_data.get('max_count')}, 最大层级={limits_data.get('max_depth')}, "
                            f"当前数量={limits_data.get('current_count')}, 当前最大层级={limits_data.get('current_max_depth')}")
            return limits_data
        except Exception as e:
            logging.warning(f"查询 DAM 集合限制失败：{e}")
            return None
    
    def update_limits_count(self, increment: int = 1):
        """
        更新限制参数中的当前数量计数（创建成功后调用）
        
        Args:
            increment: 增加的数量（默认 1）
        """
        if self._limits_cache:
            current_count = self._limits_cache.get('current_count', 0)
            self._limits_cache['current_count'] = current_count + increment
    
    def update_limits_depth(self, new_depth: int):
        """
        更新限制参数中的当前最大层级（创建成功后调用）
        
        Args:
            new_depth: 新的最大层级
        """
        if self._limits_cache:
            current_max_depth = self._limits_cache.get('current_max_depth', 0)
            if new_depth > current_max_depth:
                self._limits_cache['current_max_depth'] = new_depth
    
    def get_or_create_collection(self, collection_name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """
        获取或创建集合，返回集合ID
        
        Args:
            collection_name: 集合名称
            parent_id: 父集合ID（可选，用于创建层级关系）
        
        Returns:
            集合ID，如果创建失败返回None
        """
        # 使用完整路径作为缓存键（包含父ID，确保同一名称在不同父级下是不同的集合）
        cache_key = f"{parent_id}:{collection_name}" if parent_id else collection_name
        
        # 先检查缓存
        if cache_key in self._collection_name_to_id_cache:
            cached_id = self._collection_name_to_id_cache[cache_key]
            logging.debug(f"从缓存获取集合 '{collection_name}'（父级: {parent_id}），ID: {cached_id}")
            return cached_id
        
        try:
            # 步骤1：先查询集合是否存在（只取 1 条以减小响应体，name_eq 最多一条匹配）
            url = f"{self.base_url}/dam/collections"
            params = {'q[name_eq]': collection_name, 'page[size]': 1}
            
            # 如果指定了父ID，也需要查询父级关系
            if parent_id:
                params['q[parent_id_eq]'] = str(parent_id)
            
            logging.debug(f"查询集合 '{collection_name}'（父级: {parent_id}）...")
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            result = response.json()
            collections = result.get('data', [])
            
            # 查找匹配的集合（精确匹配名称和父级）
            for collection in collections:
                attrs = collection.get('attributes', {})
                if attrs.get('name') == collection_name:
                    # 如果指定了父ID，需要验证父级关系
                    if parent_id:
                        collection_parent_id = attrs.get('parent_id')
                        if collection_parent_id is not None and str(collection_parent_id) != str(parent_id):
                            continue  # 父级不匹配，继续查找
                    elif attrs.get('parent_id') is not None:
                        # 如果没指定父ID，但集合有父级，说明不是根级集合，不匹配
                        continue
                    
                    # 找到匹配的集合
                    collection_id = collection.get('id')
                    # 缓存结果
                    self._collection_name_to_id_cache[cache_key] = collection_id
                    logging.info(f"✓ 找到已存在的集合 '{collection_name}'（父级: {parent_id}），ID: {collection_id}")
                    return collection_id
            
            # 步骤2：检查限制，判断是否应该创建
            limits = self.get_limits()
            if limits:
                max_count = limits.get('max_count')
                current_count = limits.get('current_count', 0)
                if max_count and current_count >= max_count:
                    logging.warning(f"⚠ DAM 集合数量已达到上限（当前: {current_count}, 最大: {max_count}），跳过创建集合 '{collection_name}'")
                    return parent_id if parent_id else None
            
            # 步骤3：如果没找到，尝试创建集合
            logging.info(f"集合 '{collection_name}'（父级: {parent_id}）不存在，开始创建...")
            created_id, error_type = self._create_collection(collection_name, parent_id)
            if created_id:
                self._collection_name_to_id_cache[cache_key] = created_id
                # 更新限制参数中的当前数量计数
                self.update_limits_count(1)
                logging.info(f"✓ 成功创建集合 '{collection_name}'（父级: {parent_id}），ID: {created_id}")
                return created_id
            elif error_type == 'depth_limit':
                # 层级超出限制，这是允许的，返回父级ID
                logging.info(f"⚠ 集合层级超出限制，使用父级集合：{parent_id}")
                return parent_id
            else:
                logging.warning(f"✗ 无法创建集合：{collection_name}（父级: {parent_id}），将跳过集合设置")
                return None
            
        except Exception as e:
            logging.error(f"获取集合失败：{e}")
            if self.debug:
                import traceback
                logging.error(traceback.format_exc())
            return None
    
    def _create_collection(self, collection_name: str, parent_id: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        创建集合
        
        Args:
            collection_name: 集合名称
            parent_id: 父集合ID（可选，用于创建层级关系）
        
        Returns:
            (创建的集合ID, 错误类型)
            - 如果成功：返回 (collection_id, None)
            - 如果失败且是层级超出限制：返回 (None, 'depth_limit')
            - 如果失败且是其他原因：返回 (None, 'other')
        """
        try:
            url = f"{self.base_url}/dam/collections"
            attributes = {'name': collection_name}
            
            # 如果指定了父ID，添加到属性中
            if parent_id:
                attributes['parent_id'] = str(parent_id)
            
            data = {
                'data': {
                    'type': 'dam_collections',
                    'attributes': attributes
                }
            }
            
            if self.debug:
                logging.debug(f"创建集合请求: {json.dumps(data, indent=2, ensure_ascii=False)}")
            
            response = self.session.post(url, json=data)
            
            if response.status_code == 201 or response.status_code == 200:
                result = response.json()
                collection_id = result.get('data', {}).get('id')
                if collection_id:
                    return collection_id, None
            
            # 如果 POST 失败，检查是否是层级超出限制
            error_type = 'other'
            try:
                error_text = response.text.lower()
                # 检查错误消息中是否包含层级/深度相关的关键词
                depth_keywords = ['depth', '层级', 'level', 'max', 'limit', '超出', 'exceed', 'maximum']
                if any(keyword in error_text for keyword in depth_keywords):
                    error_type = 'depth_limit'
                    logging.info(f"⚠ 集合层级超出限制：'{collection_name}'（父级: {parent_id}）")
                else:
                    error_msg = f"POST /dam/collections 失败: {response.status_code}"
                    if len(response.text) > 200:
                        error_msg += f" - {response.text[:200]}..."
                    else:
                        error_msg += f" - {response.text}"
                    logging.warning(error_msg)
            except:
                error_type = 'other'
                logging.warning(f"POST /dam/collections 失败: {response.status_code}")
            
            if self.debug:
                logging.debug(f"完整响应: {response.text}")
            
            return None, error_type
            
        except Exception as e:
            logging.error(f"创建集合异常：{e}")
            if self.debug:
                import traceback
                logging.error(traceback.format_exc())
            return None, 'other'
    
    def get_or_create_collection_path(self, path: str) -> Optional[str]:
        """
        根据路径创建层级集合，返回最深层级的集合ID
        
        例如：路径 "00-共享盘/00-素材库/03-产品展示图"
        会创建：
        - 集合1：00-共享盘（根级）
        - 集合2：00-素材库（父级：集合1）
        - 集合3：03-产品展示图（父级：集合2）
        
        返回集合3的ID
        
        如果层级超出系统限制，会在超出限制的层级处停止，返回上一级集合的ID
        
        Args:
            path: 目录路径（支持 Windows 的 \\ 和 Mac/Linux 的 / 分隔符）
        
        Returns:
            最深层级集合的ID，如果路径为空则返回None
            如果层级超出限制，返回上一级集合的ID
        """
        if not path or not path.strip():
            return None
        
        # 标准化路径分隔符（兼容 Windows 和 Mac/Linux）
        normalized_path = path.replace('\\', '/')
        normalized_path = '/' + '/'.join([p.strip() for p in normalized_path.split('/') if p.strip()])
        if normalized_path in self._collection_path_to_id_cache:
            cached_id = self._collection_path_to_id_cache[normalized_path]
            logging.info("✓ 从缓冲命中集合路径: %s，ID: %s", normalized_path, cached_id)
            return cached_id
        
        # 分割路径（使用正斜线）
        path_parts = [p.strip() for p in normalized_path.split('/') if p.strip()]
        if not path_parts:
            return None
        
        # 获取 DAM 集合的最大层级限制
        limits = self.get_limits()
        max_depth = (limits.get('max_depth', 2) if limits else 2) - 2
        logging.debug(f"DAM 集合最大层级限制：{max_depth}")
        
        # 逐级创建集合
        current_parent_id = None
        current_depth = 0  # 当前层级（从0开始）
        
        for i, part in enumerate(path_parts):
            # 计算当前层级
            current_depth = i + 1
            
            # 检查是否超过最大层级限制
            if current_depth > max_depth:
                logging.info(f"⚠ 集合路径 '{path}' 在 '{part}' 处超过最大层级限制（当前层级: {current_depth}, 最大层级: {max_depth}），停止创建")
                if current_parent_id:
                    # 缓存当前路径与后续路径
                    for j in range(i, len(path_parts)):
                        remaining_path = '/' + '/'.join(path_parts[:j+1])
                        self._collection_path_to_id_cache[remaining_path] = current_parent_id
                    return current_parent_id
                else:
                    return None
            
            new_parent_id = self.get_or_create_collection(part, current_parent_id)
            if not new_parent_id:
                # 如果创建失败，可能是层级超出限制
                # 返回上一级集合ID，并停止后续层级创建
                if current_parent_id:
                    logging.info(f"⚠ 集合路径 '{path}' 在 '{part}' 处无法继续创建（可能是层级超出限制），使用上一级集合 ID: {current_parent_id}，停止后续层级创建")
                    # 缓存当前路径与后续路径
                    for j in range(i, len(path_parts)):
                        remaining_path = '/' + '/'.join(path_parts[:j+1])
                        self._collection_path_to_id_cache[remaining_path] = current_parent_id
                    return current_parent_id
                else:
                    logging.warning(f"无法创建集合路径 '{path}'，在 '{part}' 处失败")
                    return None
            
            # 检查是否返回的是父级ID（层级超出限制的情况）
            # 如果 new_parent_id == current_parent_id，说明层级超出限制，返回了父级ID
            if current_parent_id and str(new_parent_id) == str(current_parent_id):
                logging.info(f"⚠ 集合路径 '{path}' 在 '{part}' 处层级超出限制，使用上一级集合 ID: {current_parent_id}，停止后续层级创建")
                # 缓存当前路径与后续路径
                for j in range(i, len(path_parts)):
                    remaining_path = '/' + '/'.join(path_parts[:j+1])
                    self._collection_path_to_id_cache[remaining_path] = current_parent_id
                return current_parent_id
            
            # 更新限制参数中的当前最大层级
            self.update_limits_depth(current_depth)
            
            current_parent_id = new_parent_id

            # 缓存当前路径到最深层级ID（逐步缓存）
            current_path = '/' + '/'.join(path_parts[:i+1])
            self._collection_path_to_id_cache[current_path] = current_parent_id

        # 缓存完整路径
        self._collection_path_to_id_cache[normalized_path] = current_parent_id
        return current_parent_id

