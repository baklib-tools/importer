#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DAM 文件上传模块

功能：
- 上传文件到 DAM
- 获取文件 signed_id（用于页面创建）
- 支持标签和集合设置

维护：Baklib Tools
创建日期：2026-01-06
"""

import os
import json
import logging
import time
from typing import List, Dict, Optional, Tuple
import requests


class DAMUpload:
    """DAM 文件上传器"""
    
    def __init__(self, api_key: str, base_url: str = "https://open.baklib.com/api/v1", debug: bool = False):
        """
        初始化上传器
        
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
        # 文件上传缓存（文件名+集合ID -> 文件ID和signed_id）
        self._file_upload_cache: Dict[str, Dict] = {}
    
    def find_file_by_name_and_collection(self, name: str, collection_id: int = None) -> Optional[Dict]:
        """
        通过文件名和集合ID查找已存在的文件
        
        Args:
            name: 文件名
            collection_id: 集合ID（可选）
        
        Returns:
            文件信息（包含 id 和 signed_id），如果未找到返回 None
        """
        # 检查缓存
        cache_key = f"{name}:{collection_id}" if collection_id else name
        if cache_key in self._file_upload_cache:
            cached_result = self._file_upload_cache[cache_key]
            logging.debug(f"从缓存获取文件 '{name}'（集合: {collection_id}），ID: {cached_result.get('id')}")
            return cached_result
        
        try:
            url = f"{self.base_url}/dam/entities"
            params = {'q[name_eq]': name}
            
            # 如果指定了集合ID，也查询集合关系
            if collection_id:
                params['q[collection_ids_any]'] = str(collection_id)
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            result = response.json()
            entities = result.get('data', [])
            
            # 查找匹配的文件（精确匹配名称）
            for entity in entities:
                attrs = entity.get('attributes', {})
                if attrs.get('name') == name:
                    # 如果指定了集合ID，验证集合关系
                    if collection_id:
                        entity_collections = attrs.get('collections', [])
                        collection_ids = [c.get('id') for c in entity_collections if isinstance(c, dict)]
                        if str(collection_id) not in [str(cid) for cid in collection_ids]:
                            continue  # 集合不匹配，继续查找
                    
                    entity_id = entity.get('id')
                    # 获取 signed_id（如果需要）
                    signed_id = entity_id  # 默认使用 ID 作为 signed_id
                    
                    file_info = {
                        'id': entity_id,
                        'signed_id': signed_id
                    }
                    
                    # 缓存结果
                    self._file_upload_cache[cache_key] = file_info
                    logging.info(f"✓ 找到已存在的文件 '{name}'（集合: {collection_id}），ID: {entity_id}")
                    return file_info
            
            return None
            
        except Exception as e:
            logging.warning(f"查找文件失败：{e}")
            if self.debug:
                import traceback
                logging.debug(traceback.format_exc())
            return None
    
    def upload_file(self, file_path: str, name: str = None, description: str = None, 
                   tag_ids: List[int] = None, collection_ids: List[int] = None,
                   include_signed_id: bool = True, purpose: str = 'dynamic_form') -> Dict:
        """
        上传文件到 DAM
        
        Args:
            file_path: 本地文件路径
            name: 文件名称（可选，默认使用文件名）
            description: 文件描述（可选）
            tag_ids: 标签ID列表（整数列表，可选）
            collection_ids: 集合ID列表（整数列表，可选，支持多个集合）
            include_signed_id: 是否在响应中包含 signed_id（默认 True）
            purpose: signed_id 的用途（默认 'dynamic_form'）
        
        Returns:
            上传结果，包含文件 ID 和 signed_id 等信息
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在：{file_path}")
        
        if name is None:
            name = os.path.basename(file_path)
        
        # 检查文件是否已存在（通过文件名和集合ID）
        collection_id_for_check = collection_ids[0] if collection_ids else None
        existing_file = self.find_file_by_name_and_collection(name, collection_id_for_check)
        if existing_file:
            # 如果已存在，需要获取 signed_id（如果需要）
            signed_id = existing_file.get('signed_id')
            if include_signed_id and not signed_id:
                # 尝试通过查询实体获取 signed_id
                try:
                    entity_url = f"{self.base_url}/dam/entities/{existing_file['id']}"
                    entity_response = self.session.get(entity_url, params={'include_signed_id': 'true', 'purpose': purpose})
                    if entity_response.ok:
                        entity_result = entity_response.json()
                        entity_data = entity_result.get('data', {})
                        entity_attrs = entity_data.get('attributes', {})
                        signed_id = entity_attrs.get('signed_id', existing_file['id'])
                        existing_file['signed_id'] = signed_id
                except:
                    # 如果获取失败，使用 ID 作为 signed_id
                    signed_id = existing_file['id']
            else:
                signed_id = existing_file.get('signed_id', existing_file['id'])
            
            logging.info(f"✓ 文件已存在，跳过上传：{name}，ID: {existing_file['id']}")
            # 返回格式化的结果
            return {
                'data': {
                    'id': existing_file['id'],
                    'attributes': {
                        'signed_id': signed_id
                    }
                }
            }
        
        url = f"{self.base_url}/dam/files"
        
        # 先读取文件内容到内存（避免文件指针问题）
        with open(file_path, 'rb') as f:
            file_buffer = f.read()
        
        # 使用 JSON API 格式
        files = {
            'data[attributes][file]': (name, file_buffer, self._get_content_type(file_path))
        }
        
        # 准备其他参数（使用 JSON API 格式）
        data = {
            'data[type]': 'dam_files'
        }
        
        if description:
            data['data[attributes][description]'] = description
        
        # 如果需要 signed_id，添加参数
        if include_signed_id:
            data['include_signed_id'] = 'true'
            data['purpose'] = purpose
        
        # 处理标签：如果提供了标签ID列表，直接设置
        if tag_ids:
            tag_id_str_list = [str(tid) for tid in tag_ids]
            data['data[attributes][tag_ids]'] = json.dumps(tag_id_str_list, ensure_ascii=False)
        
        # 处理集合：如果提供了集合ID列表，直接设置（支持多个集合）
        if collection_ids:
            collection_id_list = [str(cid) for cid in collection_ids]
            data['data[attributes][collection_ids]'] = json.dumps(collection_id_list, ensure_ascii=False)
        
        # 文件上传需要使用 multipart/form-data
        headers = {
            'Authorization': self.api_key
        }
        
        # 临时移除 session 的 Content-Type，让 requests 自动处理 multipart/form-data
        original_content_type = self.session.headers.pop('Content-Type', None)
        
        # 调试信息
        if self.debug:
            logging.info("=" * 80)
            logging.info(f"[HTTP 请求调试]")
            logging.info(f"URL: {url}")
            logging.info(f"文件大小: {len(file_buffer)} 字节 ({len(file_buffer) / 1024:.2f} KB)")
            logging.info(f"Headers: {json.dumps(headers, indent=2, ensure_ascii=False)}")
            logging.info(f"Data 参数:")
            for key, value in data.items():
                logging.info(f"  {key} = {value}")
            if tag_ids:
                logging.info(f"Tag IDs: {tag_ids}")
            if collection_ids:
                logging.info(f"Collection IDs: {collection_ids}")
            logging.info("=" * 80)
        
        try:
            response = self.session.post(
                url,
                files=files,
                data=data,
                headers=headers
            )
        finally:
            # 恢复原始的 Content-Type（如果存在）
            if original_content_type:
                self.session.headers['Content-Type'] = original_content_type
        
        # 调试信息：输出响应
        if self.debug:
            logging.info("=" * 80)
            logging.info(f"[HTTP 响应调试]")
            logging.info(f"状态码: {response.status_code}")
            try:
                response_text = response.text
                if response.ok:
                    logging.info(f"响应内容 (前1000字符):")
                    logging.info(response_text[:1000])
                    if len(response_text) > 1000:
                        logging.info(f"... (共 {len(response_text)} 字符)")
                else:
                    logging.error(f"[HTTP 错误] 响应内容 (前200字符): {response_text[:200]}")
            except Exception as e:
                logging.info(f"响应内容: (无法读取: {e})")
            logging.info("=" * 80)
        
        if not response.ok:
            logging.error(f"[HTTP 错误] 状态码: {response.status_code}")
            try:
                error_text = response.text
                logging.error(f"[HTTP 错误] 响应内容: {error_text[:200]}")
            except:
                logging.error(f"[HTTP 错误] 无法读取响应内容")
        
        response.raise_for_status()
        result = response.json()
        
        # 缓存上传结果
        file_data = result.get('data', {})
        file_id = file_data.get('id', '')
        signed_id = file_data.get('attributes', {}).get('signed_id', file_id)
        
        if file_id:
            cache_key = f"{name}:{collection_id_for_check}" if collection_id_for_check else name
            self._file_upload_cache[cache_key] = {
                'id': file_id,
                'signed_id': signed_id
            }
        
        return result
    
    def _get_content_type(self, file_path: str) -> str:
        """根据文件扩展名获取 Content-Type"""
        ext = os.path.splitext(file_path)[1].lower()
        content_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp',
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.wmv': 'video/x-ms-wmv',
            '.flv': 'video/x-flv',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        }
        return content_types.get(ext, 'application/octet-stream')
    
    def get_file_url(self, entity_id: str, purpose: str = None, expires_in: int = None) -> Optional[Dict]:
        """
        生成 DAM 文件 URL
        
        Args:
            entity_id: 文件实体 ID（支持数字 ID 或 signed_id）
            purpose: URL 的用途标识（可选）
            expires_in: URL 的有效期（秒数，可选）
        
        Returns:
            包含 url 和 expires_at 的字典，如果失败返回 None
        """
        try:
            url = f"{self.base_url}/dam/entities/{entity_id}/urls"
            
            data = {}
            if purpose:
                data['purpose'] = purpose
            if expires_in:
                data['expires_in'] = expires_in
            
            response = self.session.post(url, json=data)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logging.error(f"生成文件 URL 失败：{e}")
            if self.debug:
                import traceback
                logging.error(traceback.format_exc())
            return None
    
    def test_connection(self) -> bool:
        """测试 API 连接"""
        try:
            url = f"{self.base_url}/dam/entities"
            response = self.session.get(url, params={'page[size]': 1})
            response.raise_for_status()
            return True
        except Exception as e:
            logging.error(f"API 连接测试失败：{e}")
            return False

