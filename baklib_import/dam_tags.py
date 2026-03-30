#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DAM 标签管理模块

功能：
- 创建和管理 DAM 标签
- 缓存标签 ID

维护：Baklib Tools
创建日期：2026-01-06
"""

import logging
from typing import Dict, Optional, List
import requests


class DAMTags:
    """DAM 标签管理器"""
    
    def __init__(self, api_key: str, base_url: str = "https://open.baklib.com/api/v1", debug: bool = False):
        """
        初始化标签管理器
        
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
        # 标签的映射缓存（名称 -> ID）
        self._tag_name_to_id_cache: Dict[str, str] = {}
        # 标签串缓存（标签串 -> ID列表）
        self._tag_string_to_ids_cache: Dict[str, List[int]] = {}

    def get_or_create_tag(self, tag_name: str) -> Optional[str]:
        """
        获取或创建标签，返回标签ID
        
        使用 API 查询参数：
        - q[name_eq]: 名称完全匹配查询
        
        Args:
            tag_name: 标签名称
        
        Returns:
            标签ID，如果创建失败返回None
        """
        # 先检查缓存
        if tag_name in self._tag_name_to_id_cache:
            return self._tag_name_to_id_cache[tag_name]
        
        try:
            # 使用名称完全匹配查询（只取 1 条以减小响应体，name_eq 最多一条匹配）
            url = f"{self.base_url}/dam/tags"
            params = {'q[name_eq]': tag_name, 'page[size]': 1}
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            result = response.json()
            tags = result.get('data', [])
            
            # 查找匹配的标签（精确匹配）
            for tag in tags:
                attrs = tag.get('attributes', {})
                if attrs.get('name') == tag_name:
                    tag_id = tag.get('id')
                    # 缓存结果
                    self._tag_name_to_id_cache[tag_name] = tag_id
                    logging.info(f"找到标签 '{tag_name}'，ID: {tag_id}")
                    return tag_id
            
            # 如果没找到，尝试创建标签
            logging.info(f"标签 '{tag_name}' 不存在，尝试创建...")
            created_id = self._create_tag(tag_name)
            if created_id:
                self._tag_name_to_id_cache[tag_name] = created_id
                logging.info(f"成功创建标签 '{tag_name}'，ID: {created_id}")
                return created_id
            else:
                logging.warning(f"无法创建标签：{tag_name}，将跳过标签设置")
                return None
            
        except Exception as e:
            logging.error(f"获取标签失败：{e}")
            if self.debug:
                import traceback
                logging.error(traceback.format_exc())
            return None
    
    def _create_tag(self, tag_name: str) -> Optional[str]:
        """
        创建标签
        
        Args:
            tag_name: 标签名称
        
        Returns:
            标签ID，如果创建失败返回None
        """
        try:
            url = f"{self.base_url}/dam/tags"
            data = {
                'data': {
                    'type': 'dam_tags',
                    'attributes': {
                        'name': tag_name
                    }
                }
            }
            response = self.session.post(url, json=data)
            
            if response.status_code == 201 or response.status_code == 200:
                result = response.json()
                tag_id = result.get('data', {}).get('id')
                if tag_id:
                    return tag_id
            
            # 如果 POST 失败，记录错误但不抛出异常
            if self.debug:
                logging.debug(f"POST /dam/tags 失败: {response.status_code} - {response.text}")
            
            return None
            
        except Exception as e:
            if self.debug:
                logging.debug(f"创建标签异常：{e}")
            return None
    
    def get_or_create_tags_from_string(self, tags_string: str) -> List[int]:
        """
        从标签字符串（用 / 分隔）获取或创建标签，返回标签ID列表
        
        Args:
            tags_string: 标签字符串（用 / 分隔，如 "标签1/标签2/标签3"）
        
        Returns:
            标签ID列表（整数列表）
        """
        if not tags_string:
            return []

        normalized = '/'.join([t.strip() for t in tags_string.split('/') if t.strip()])
        if normalized in self._tag_string_to_ids_cache:
            return self._tag_string_to_ids_cache[normalized]

        tags_list = [t.strip() for t in normalized.split('/') if t.strip()]
        tag_ids = []
        
        for tag_name in tags_list:
            tag_id = self.get_or_create_tag(tag_name)
            if tag_id:
                tag_ids.append(int(tag_id))
            else:
                logging.warning(f"无法获取或创建标签：{tag_name}，将跳过该标签")
        
        self._tag_string_to_ids_cache[normalized] = tag_ids
        return tag_ids

