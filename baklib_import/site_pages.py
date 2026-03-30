#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
站点页面管理模块

功能：
- 创建站点页面（栏目和资源页面）
- 管理页面层级结构
- 支持标准创建和智能创建

维护：Baklib Tools
创建日期：2026-01-06
"""

import logging
import json
from typing import Dict, List, Optional
from datetime import datetime
import requests


class SitePages:
    """站点页面管理器"""
    
    def __init__(self, api_key: str, site_id: int, base_url: str = "https://open.baklib.com/api/v1", debug: bool = False):
        """
        初始化页面管理器
        
        Args:
            api_key: API 密钥，格式为 "access_key:secret_key"
            site_id: 站点 ID
            base_url: API 基础地址
            debug: 是否启用调试模式
        """
        self.api_key = api_key
        self.site_id = site_id
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.debug = debug
        self.session.headers.update({
            'Authorization': api_key,
            'Content-Type': 'application/json'
        })
        # 页面路径到ID的映射缓存（路径 -> ID）
        self._page_path_to_id_cache: Dict[str, int] = {}
        # 页面 slug 缓存（slug+parent_id -> 页面ID）
        self._page_slug_cache: Dict[str, int] = {}
        # 栏目 (name, parent_id) 缓存：创建时用 name 判断「是否已存在」更稳定，不依赖 slug（slug 随 collection_id 变化）
        self._page_name_parent_to_id_cache: Dict[tuple, int] = {}
        # 限制信息缓存
        self._limits_cache: Optional[Dict] = None
        # 站点首页 ID（系统默认创建的根页面，其他栏目都在其下）；None 表示未获取
        self._home_page_id: Optional[int] = None

    def get_home_page_id(self) -> Optional[int]:
        """
        获取站点首页 ID。站点根是首页，其他栏目都在首页之下，创建根级栏目时 parent_id 应为首页 ID。

        Returns:
            首页页面 ID，获取失败返回 None
        """
        if self._home_page_id is not None:
            return self._home_page_id
        try:
            # 1) 尝试从站点详情获取（若 API 提供 default_page_id / home_page_id）
            site_url = f"{self.base_url}/sites/{self.site_id}"
            resp = self.session.get(site_url)
            if resp.ok:
                data = resp.json().get("data", {}) or {}
                attrs = data.get("attributes", {}) or {}
                for key in ("default_page_id", "home_page_id", "root_page_id"):
                    val = attrs.get(key)
                    if val is not None:
                        self._home_page_id = int(val)
                        logging.debug(f"站点首页 ID 来自站点详情 {key}: {self._home_page_id}")
                        return self._home_page_id
            # 2) 从页面列表中查找首页（template_name=='home' 或 名称为「首页」）
            url = f"{self.base_url}/sites/{self.site_id}/pages"
            resp = self.session.get(url, params={
                "page[size]": 100,
                "page[number]": 1,
                "fields[pages]": "id,name,parent_id,template_name,calculated_link_text,seo_title"
            })
            if not resp.ok:
                return None
            pages = resp.json().get("data", []) or []
            candidates = []
            for p in pages:
                pid = p.get("id")
                if not pid:
                    continue
                pid_int = int(pid)
                attrs = p.get("attributes", {}) or {}
                tpl = attrs.get("template_name") or ""
                name = (attrs.get("calculated_link_text") or attrs.get("name") or attrs.get("seo_title") or "").strip()
                if tpl == "home" or name == "首页":
                    candidates.append((pid_int, p))
            if candidates:
                candidates.sort(key=lambda x: x[0])
                self._home_page_id = candidates[0][0]
                logging.info(f"站点首页 ID 来自页面列表（template_name=home 或 名称=首页）: {self._home_page_id}")
                return self._home_page_id
            # 3) 约定：取所有页面中最小的 parent_id（通常为首页 id，且首页 id 最小）
            parent_ids = set()
            for p in pages:
                attrs = (p.get("attributes") or {}).get("parent_id")
                if attrs is not None:
                    parent_ids.add(int(attrs))
            if parent_ids:
                self._home_page_id = min(parent_ids)
                logging.info(f"站点首页 ID 约定取最小 parent_id: {self._home_page_id}")
                return self._home_page_id
            logging.warning("无法获取站点首页 ID，根级栏目创建可能失败")
            return None
        except Exception as e:
            logging.warning(f"获取站点首页 ID 失败: {e}")
            return None

    def get_limits(self, force_refresh: bool = False) -> Optional[Dict]:
        """
        获取站点的限制参数（仅在首次调用时查询API，之后使用缓存）
        
        Args:
            force_refresh: 是否强制刷新（默认 False，只在启动时使用）
        
        Returns:
            限制信息字典，包含 max_count, max_depth, current_count, current_max_depth
        """
        if self._limits_cache is not None and not force_refresh:
            return self._limits_cache
        
        try:
            url = f"{self.base_url}/sites/{self.site_id}/limits"
            response = self.session.get(url)
            response.raise_for_status()
            
            result = response.json()
            limits_data = result.get('data', {})
            self._limits_cache = limits_data
            if force_refresh:
                logging.info(f"站点限制：最大数量={limits_data.get('max_count')}, 最大层级={limits_data.get('max_depth')}, "
                            f"当前数量={limits_data.get('current_count')}, 当前最大层级={limits_data.get('current_max_depth')}")
            return limits_data
        except Exception as e:
            logging.warning(f"查询站点限制失败：{e}")
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
    
    def get_max_channel_depth(self) -> int:
        """
        获取站点栏目的最大层级（max_depth - 1，为资源页面留出空间）
        
        Returns:
            站点栏目的最大层级
        """
        limits = self.get_limits()
        if limits:
            max_depth = limits.get('max_depth', 2)
            # 站点栏目的层级不能达到最大层级限制，否则下面无法创建页面
            # 所以最大层级是 max_depth - 2
            return max_depth - 2
        # 默认值：如果查询失败，使用 4（假设 max_depth 是 6）
        return 2
    
    @staticmethod
    def format_slug_from_id(id_value: int) -> str:
        """
        将 ID 格式化为 slug（至少两个字符，用 0 补全）
        
        Args:
            id_value: ID 值（整数）
        
        Returns:
            格式化后的 slug（字符串，至少两位）
        """
        return str(id_value).zfill(2)
    
    def create_channel(self, name: str, collection_id: int = None, parent_id: Optional[int] = None,
                      description: str = None, published: bool = True, published_at: str = None) -> Optional[Dict]:
        """
        创建栏目（频道）页面
        
        Args:
            name: 栏目名称
            collection_id: DAM 集合 ID（用于生成 slug，必需）
            parent_id: 父页面 ID（None 表示根级/站点首页下，内部会转为首页 ID；非根为具体父页面 ID）
            description: 栏目描述（可选）
            published: 是否发布（默认 True）
            published_at: 发布时间（格式：YYYY-MM-DD HH:mm，可选，默认当前时间）
        
        Returns:
            创建的页面信息，如果失败返回 None
        """
        if collection_id is None:
            raise ValueError("collection_id 是必需的，用于生成 slug")
        
        try:
            url = f"{self.base_url}/sites/{self.site_id}/pages"
            
            # 使用集合 ID 生成 slug（至少两个字符，用 0 补全）
            slug = self.format_slug_from_id(collection_id)
            
            # 如果没有提供发布时间，使用当前时间
            if published_at is None:
                published_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # 根级：站点根是首页，parent_id=None 转为首页 ID；非根用父页面 ID
            home_id = self.get_home_page_id() if parent_id is None else None
            parent_for_key = home_id if parent_id is None else int(parent_id)
            name_parent_key = (name, parent_for_key)
            page_id = self._page_name_parent_to_id_cache.get(name_parent_key)
            if page_id is not None:
                logging.info(f"✓ 栏目已存在（name: {name}, parent: {parent_id}），ID: {page_id}")
                try:
                    get_url = f"{self.base_url}/sites/{self.site_id}/pages/{page_id}"
                    response = self.session.get(get_url, params={"fields[pages]": "id,name,full_path,parent_id,slug"})
                    response.raise_for_status()
                    return response.json()
                except Exception:
                    return {'data': {'id': str(page_id)}}
            
            # 再检查 (slug, parent_id) 缓存；根级为首页 ID
            cache_key = f"{slug}:{parent_for_key}"
            if cache_key in self._page_slug_cache:
                page_id = self._page_slug_cache[cache_key]
                logging.info(f"✓ 栏目已存在（slug: {slug}, parent: {parent_id}），ID: {page_id}")
                # 返回已存在的页面信息（需要查询获取完整信息）
                try:
                    get_url = f"{self.base_url}/sites/{self.site_id}/pages/{page_id}"
                    response = self.session.get(get_url, params={"fields[pages]": "id,name,full_path,parent_id,slug"})
                    response.raise_for_status()
                    return response.json()
                except:
                    # 如果查询失败，返回 None，让调用者知道页面已存在
                    return {'data': {'id': str(page_id)}}
            
            # 根级传首页 ID，非根传父页面 ID（站点根是首页，不传 null/0）
            parent_for_api = parent_for_key
            attributes = {
                'name': name,
                'template_name': 'channel',
                'parent_id': parent_for_api,
                'published': published,
                'published_at': published_at,
                'slug': slug
            }
            
            if description:
                attributes['template_variables'] = {
                    'title': name,
                    'description': description
                }
            else:
                attributes['template_variables'] = {
                    'title': name
                }
            
            # SEO 设置
            attributes['seo_title'] = name
            attributes['seo_keywords'] = name
            attributes['seo_description'] = description or name
            
            data = {
                'data': {
                    'type': 'pages',
                    'attributes': attributes
                }
            }
            
            if self.debug:
                logging.debug(f"创建栏目请求: {json.dumps(data, indent=2, ensure_ascii=False)}")
            
            # 先检查限制，判断是否应该创建
            limits = self.get_limits()
            if limits:
                max_count = limits.get('max_count')
                current_count = limits.get('current_count', 0)
                if max_count and current_count >= max_count:
                    logging.warning(f"⚠ 站点页面数量已达到上限（当前: {current_count}, 最大: {max_count}），跳过创建栏目 '{name}'")
                    return {'data': {'id': str(parent_for_key), '_count_limit': True}} if parent_for_key is not None else None
            
            # 先通过 parent_id 和 name 查询是否存在；根级用首页 ID 查询（站点根是首页）
            try:
                check_url = f"{self.base_url}/sites/{self.site_id}/pages"
                if parent_for_key is not None:
                    check_params = {
                        'parent_id': str(parent_for_key),
                        'page[size]': 100,
                        'fields[pages]': 'id,name,full_path,parent_id,calculated_link_text,seo_title'
                    }
                    check_response = self.session.get(check_url, params=check_params)
                    if check_response.ok:
                        pages = check_response.json().get('data', [])
                        for page in pages:
                            page_attrs = page.get('attributes', {}) or {}
                            page_name = page_attrs.get('name', '') or page_attrs.get('calculated_link_text', '') or page_attrs.get('seo_title', '')
                            page_parent_raw = page_attrs.get('parent_id')
                            page_parent_norm = None if page_parent_raw is None else int(page_parent_raw)
                            if page_name == name and page_parent_norm == parent_for_key:
                                existing_page_id = page.get('id')
                                self._page_slug_cache[cache_key] = int(existing_page_id)
                                self._page_name_parent_to_id_cache[(name, parent_for_key)] = int(existing_page_id)
                                full_path = page_attrs.get('full_path', '')
                                if full_path:
                                    self._page_path_to_id_cache[full_path] = int(existing_page_id)
                                logging.info(f"✓ 栏目已存在（name: {name}, parent: {parent_for_key}, full_path: {full_path}），ID: {existing_page_id}")
                                return {'data': page}
            except Exception as e:
                logging.debug(f"通过 parent_id 和 name 查询页面是否存在时出错：{e}")
            
            # 如果通过 parent_id 和 name 查询不到，尝试通过 full_path 查询
            # 需要先获取父级页面的 full_path（根级时父级为首页）
            expected_full_path = None
            if parent_for_api is not None:
                try:
                    # 获取父级页面的 full_path
                    parent_url = f"{self.base_url}/sites/{self.site_id}/pages/{parent_for_api}"
                    parent_response = self.session.get(parent_url, params={"fields[pages]": "id,name,full_path"})
                    if parent_response.ok:
                        parent_data = parent_response.json()
                        parent_full_path = parent_data.get('data', {}).get('attributes', {}).get('full_path', '')
                        if parent_full_path:
                            # 构建预期的 full_path（使用 slug）
                            expected_full_path = f"{parent_full_path}/{slug}"
                        else:
                            # 如果父级没有 full_path，使用 slug
                            expected_full_path = f"/{slug}"
                    else:
                        # 如果获取父级失败，使用 slug
                        expected_full_path = f"/{slug}"
                except Exception as e:
                    logging.debug(f"获取父级页面 full_path 时出错：{e}")
                    expected_full_path = f"/{slug}"
            else:
                # 根级页面
                expected_full_path = f"/{slug}"
            
            # 通过 full_path 查询是否存在
            if expected_full_path:
                try:
                    check_url = f"{self.base_url}/sites/{self.site_id}/pages"
                    check_params = {
                        'full_path': expected_full_path,
                        'page[size]': 10,
                        'fields[pages]': 'id,name,full_path,parent_id,slug'
                    }
                    check_response = self.session.get(check_url, params=check_params)
                    if check_response.ok:
                        check_result = check_response.json()
                        pages = check_result.get('data', [])
                        # 查找匹配的页面（通过 full_path）
                        for page in pages:
                            page_attrs = page.get('attributes', {})
                            page_full_path = page_attrs.get('full_path', '')
                            if page_full_path == expected_full_path:
                                existing_page_id = page.get('id')
                                # 缓存结果（含 name+parent）；首页下栏目 parent_id 为首页 id
                                pname = page_attrs.get('name', '')
                                pparent = None if page_attrs.get('parent_id') is None else int(page_attrs.get('parent_id'))
                                self._page_slug_cache[cache_key] = int(existing_page_id)
                                if pname:
                                    self._page_name_parent_to_id_cache[(pname, pparent)] = int(existing_page_id)
                                if page_full_path:
                                    self._page_path_to_id_cache[page_full_path] = int(existing_page_id)
                                logging.info(f"✓ 栏目已存在（full_path: {expected_full_path}），ID: {existing_page_id}")
                                return {'data': page}
                except Exception as e:
                    logging.debug(f"通过 full_path 查询页面是否存在时出错：{e}")
            
            response = self.session.post(url, json=data)
            
            # 如果返回 422 错误，检查是否是层级超出限制
            if response.status_code == 422:
                try:
                    error_data = response.json()
                    errors = error_data.get('errors', [])
                    for error in errors:
                        error_detail = str(error.get('detail', '')).lower()
                        # 检查是否是层级超出限制
                        if '层级' in error_detail or 'depth' in error_detail or 'level' in error_detail or '超出' in error_detail or 'limit' in error_detail:
                            # 层级超出限制，返回父级ID（通过特殊标记）
                            logging.info(f"⚠ 栏目层级超出限制：'{name}'（父级: {parent_for_key}），使用父级栏目")
                            return {'data': {'id': str(parent_for_key), '_depth_limit': True}} if parent_for_key is not None else None
                        elif '已经存在' in error_detail or '记录已经存在' in error_detail or 'full_path' in str(error.get('source', {})).lower():
                            # 记录已存在（通过 full_path），应该已经在创建前查询到了，这里再次查询确认
                            logging.warning(f"⚠ 创建栏目时返回'记录已经存在'，但创建前查询未找到，再次查询...")
                            # 再次通过 parent_id 和 name 查询；根级用首页 ID
                            try:
                                check_url = f"{self.base_url}/sites/{self.site_id}/pages"
                                if parent_for_key is not None:
                                    check_params = {
                                        'parent_id': str(parent_for_key),
                                        'page[size]': 100,
                                        'fields[pages]': 'id,name,full_path,parent_id,calculated_link_text,seo_title'
                                    }
                                else:
                                    check_params = {
                                        'page[size]': 100,
                                        'page[number]': 1,
                                        'fields[pages]': 'id,name,full_path,parent_id,calculated_link_text,seo_title'
                                    }
                                check_response = self.session.get(check_url, params=check_params)
                                if check_response.ok:
                                    check_result = check_response.json()
                                    pages = check_result.get('data', [])
                                    for page in pages:
                                        page_attrs = page.get('attributes', {})
                                        page_name = page_attrs.get('name', '')
                                        page_parent_raw = page_attrs.get('parent_id')
                                        page_parent_norm = None if page_parent_raw is None else int(page_parent_raw)
                                        if page_name == name and page_parent_norm == parent_for_key:
                                            existing_page_id = page.get('id')
                                            self._page_slug_cache[cache_key] = int(existing_page_id)
                                            self._page_name_parent_to_id_cache[(name, parent_for_key)] = int(existing_page_id)
                                            full_path = page_attrs.get('full_path', '')
                                            if full_path:
                                                self._page_path_to_id_cache[full_path] = int(existing_page_id)
                                            logging.info(f"✓ 栏目已存在（记录已存在，name: {name}, parent: {parent_id}, full_path: {full_path}），ID: {existing_page_id}")
                                            return {'data': page}
                            except Exception as e:
                                logging.debug(f"再次查询已存在页面时出错：{e}")
                            # 如果还是找不到，记录错误但不抛出异常
                            logging.error(f"✗ 创建栏目失败：记录已存在，但查询不到对应页面（name: {name}, parent: {parent_id}）")
                            return None
                except Exception as e:
                    logging.error(f"✗ 创建栏目失败，解析错误信息时出错：{e}")
                    return None
            
            # 检查响应状态
            if not response.ok:
                try:
                    error_data = response.json()
                    errors = error_data.get('errors', [])
                    error_messages = [str(e.get('detail', '')) for e in errors]
                    logging.error(f"✗ 创建栏目失败：{', '.join(error_messages)}")
                except:
                    logging.error(f"✗ 创建栏目失败：HTTP {response.status_code}")
                return None
            
            response.raise_for_status()
            
            result = response.json()
            page_data = result.get('data', {})
            page_id = page_data.get('id')
            
            if page_id:
                # 缓存页面路径、slug、name+parent；根级为 None，从不使用 0
                self._page_slug_cache[cache_key] = int(page_id)
                self._page_name_parent_to_id_cache[(name, parent_for_key)] = int(page_id)
                full_path = page_data.get('attributes', {}).get('full_path', '')
                if full_path:
                    self._page_path_to_id_cache[full_path] = int(page_id)
                
                # 更新限制参数中的当前数量计数
                self.update_limits_count(1)
                
                logging.info(f"✓ 成功创建栏目 '{name}'，ID: {page_id}")
                return result
            else:
                logging.warning(f"创建栏目 '{name}' 成功但未返回 ID")
                return None
            
        except Exception as e:
            logging.error(f"创建栏目失败：{e}")
            if self.debug:
                import traceback
                logging.error(traceback.format_exc())
                if 'response' in locals():
                    logging.error(f"响应状态码: {response.status_code}")
                    logging.error(f"响应内容: {response.text[:500]}")
            return None
    
    def create_resource_page(self, name: str, asset_signed_id: str, 
                           dam_resource_id: int = None, parent_id: Optional[int] = None,
                           description: str = None, resource_tags: List[int] = None,
                           published: bool = True, published_at: str = None) -> Optional[Dict]:
        """
        创建资源页面
        
        Args:
            name: 页面名称
            asset_signed_id: 资源文件的 signed_id
            dam_resource_id: DAM 资源 ID（用于生成 slug，必需）
            parent_id: 父页面 ID（None 表示根级/站点首页下，内部会转为首页 ID；非根为具体父页面 ID）
            description: 页面描述（可选）
            resource_tags: 资源标签ID列表（可选，整数列表，来源于 site.scope_tags）
            published: 是否发布（默认 True）
            published_at: 发布时间（格式：YYYY-MM-DD HH:mm，可选）
        
        Returns:
            创建的页面信息，如果失败返回 None
        """
        if dam_resource_id is None:
            raise ValueError("dam_resource_id 是必需的，用于生成 slug")
        
        try:
            url = f"{self.base_url}/sites/{self.site_id}/pages"
            
            # 先检查限制，判断是否应该创建
            limits = self.get_limits()
            if limits:
                max_count = limits.get('max_count')
                current_count = limits.get('current_count', 0)
                if max_count and current_count >= max_count:
                    logging.warning(f"⚠ 站点页面数量已达到上限（当前: {current_count}, 最大: {max_count}），跳过创建资源页面 '{name}'")
                    return None
            
            # 使用 DAM 资源 ID 生成 slug（至少两个字符，用 0 补全）
            slug = self.format_slug_from_id(dam_resource_id)
            
            # 根级：站点根是首页，parent_id=None 转为首页 ID；非根用父页面 ID
            parent_for_key = self.get_home_page_id() if parent_id is None else int(parent_id)
            cache_key = f"{slug}:{parent_for_key}"
            if cache_key in self._page_slug_cache:
                page_id = self._page_slug_cache[cache_key]
                logging.info(f"✓ 资源页面已存在（slug: {slug}, parent: {parent_id}），ID: {page_id}")
                # 返回已存在的页面信息（仅取必要字段以减小响应）
                try:
                    get_url = f"{self.base_url}/sites/{self.site_id}/pages/{page_id}"
                    response = self.session.get(get_url, params={"fields[pages]": "id,name,full_path,slug,parent_id"})
                    response.raise_for_status()
                    return response.json()
                except:
                    # 如果查询失败，返回 None，让调用者知道页面已存在
                    return {'data': {'id': str(page_id)}}
            
            template_variables = {
                'title': name,
                'asset': asset_signed_id
            }
            
            if description:
                template_variables['content'] = f"<p>{description}</p>"
            
            if resource_tags:
                template_variables['resource_tags'] = resource_tags
            
            # 根级传首页 ID，非根传父页面 ID（站点根是首页）
            parent_for_api = parent_for_key
            
            # 检查父级栏目的层级是否已达到限制
            if parent_for_api is not None:
                try:
                    # 查询父级栏目的信息，获取其层级
                    parent_url = f"{self.base_url}/sites/{self.site_id}/pages/{parent_for_api}"
                    parent_response = self.session.get(parent_url, params={"fields[pages]": "id,name,full_path"})
                    if parent_response.ok:
                        parent_data = parent_response.json()
                        parent_attrs = parent_data.get('data', {}).get('attributes', {})
                        parent_full_path = parent_attrs.get('full_path', '')
                        parent_name = parent_attrs.get('name', '')
                        # 通过 full_path 计算层级（路径中的 / 数量）
                        if parent_full_path:
                            parent_depth = parent_full_path.count('/')
                            max_depth = self.get_limits().get('max_depth', 6) if self.get_limits() else 6
                            # 如果父级栏目的层级已经达到 max_depth - 1，则无法创建资源页面
                            if parent_depth >= max_depth - 1:
                                if parent_name:
                                    logging.warning(f"⚠ 父级栏目（ID: {parent_for_api}，名称: '{parent_name}'）的层级已达到限制（{parent_depth} >= {max_depth - 1}），无法在此栏目下创建资源页面")
                                else:
                                    logging.warning(f"⚠ 父级栏目（ID: {parent_for_api}）的层级已达到限制（{parent_depth} >= {max_depth - 1}），无法在此栏目下创建资源页面")
                                logging.warning(f"⚠ 资源页面 '{name}' 无法创建，父级栏目层级超出限制")
                                return None
                except Exception as e:
                    logging.debug(f"检查父级栏目层级时出错（继续创建）：{e}")
            
            logging.info(f"创建资源页面 '{name}'，父级栏目 ID: {parent_for_api}")
            
            attributes = {
                'name': name,
                'template_name': 'page',
                'parent_id': parent_for_api,  # 根级为 null，非根为 int
                'template_variables': template_variables,
                'published': published,
                'slug': slug
            }
            
            if published_at:
                attributes['published_at'] = published_at
            
            # 先检查是否已存在（通过查询）；根级不传 parent_id_eq（API 为 null）
            try:
                check_url = f"{self.base_url}/sites/{self.site_id}/pages"
                list_fields = 'id,slug,parent_id,full_path'
                if parent_for_api is None:
                    check_params = {'q[slug_eq]': slug, 'page[size]': 100, 'fields[pages]': list_fields}
                else:
                    check_params = {'q[slug_eq]': slug, 'q[parent_id_eq]': str(parent_for_api), 'page[size]': 100, 'fields[pages]': list_fields}
                check_response = self.session.get(check_url, params=check_params)
                if check_response.ok:
                    check_result = check_response.json()
                    pages = check_result.get('data', [])
                    for page in pages:
                        page_attrs = page.get('attributes', {})
                        page_parent_raw = page_attrs.get('parent_id')
                        page_parent_ok = (page_parent_raw is None and parent_for_api is None) or (page_parent_raw is not None and parent_for_api is not None and int(page_parent_raw) == parent_for_api)
                        if page_attrs.get('slug') == slug and page_parent_ok:
                            existing_page_id = page.get('id')
                            # 缓存结果
                            self._page_slug_cache[cache_key] = int(existing_page_id)
                            full_path = page_attrs.get('full_path', '')
                            if full_path:
                                self._page_path_to_id_cache[full_path] = int(existing_page_id)
                            logging.info(f"✓ 资源页面已存在（slug: {slug}, parent: {parent_for_api}），ID: {existing_page_id}")
                            return {'data': page}
            except Exception as e:
                logging.debug(f"检查页面是否存在时出错（继续创建）：{e}")
            
            # SEO 设置
            attributes['seo_title'] = name
            attributes['seo_keywords'] = name
            attributes['seo_description'] = description or name
            
            data = {
                'data': {
                    'type': 'pages',
                    'attributes': attributes
                }
            }
            
            if self.debug:
                logging.debug(f"创建资源页面请求: {json.dumps(data, indent=2, ensure_ascii=False)}")
                logging.debug(f"请求中的 parent_id: {parent_for_api} (类型: {type(parent_for_api).__name__})")
            
            response = self.session.post(url, json=data)
            
            # 如果返回 422 错误，检查是否是 slug 冲突或层级限制
            if response.status_code == 422:
                try:
                    error_data = response.json()
                    errors = error_data.get('errors', [])
                    error_details = [str(e.get('detail', '')).lower() for e in errors]
                    all_error_text = ' '.join(error_details)
                    
                    # 先尝试查询是否已存在（可能是 slug 冲突）
                    try:
                        check_url = f"{self.base_url}/sites/{self.site_id}/pages"
                        list_fields = 'id,slug,parent_id,full_path'
                        if parent_for_api is None:
                            check_params = {'q[slug_eq]': slug, 'page[size]': 100, 'fields[pages]': list_fields}
                        else:
                            check_params = {'q[slug_eq]': slug, 'q[parent_id_eq]': str(parent_for_api), 'page[size]': 100, 'fields[pages]': list_fields}
                        check_response = self.session.get(check_url, params=check_params)
                        if check_response.ok:
                            check_result = check_response.json()
                            pages = check_result.get('data', [])
                            for page in pages:
                                page_attrs = page.get('attributes', {})
                                page_parent_raw = page_attrs.get('parent_id')
                                page_parent_ok = (page_parent_raw is None and parent_for_api is None) or (page_parent_raw is not None and parent_for_api is not None and int(page_parent_raw) == parent_for_api)
                                if page_attrs.get('slug') == slug and page_parent_ok:
                                    existing_page_id = page.get('id')
                                    self._page_slug_cache[cache_key] = int(existing_page_id)
                                    full_path = page_attrs.get('full_path', '')
                                    if full_path:
                                        self._page_path_to_id_cache[full_path] = int(existing_page_id)
                                    logging.info(f"✓ 资源页面已存在（slug: {slug}, parent: {parent_for_api}），ID: {existing_page_id}")
                                    return {'data': page}
                    except Exception as e:
                        logging.debug(f"查询已存在页面时出错：{e}")
                    
                    # 如果是层级限制，记录详细错误信息
                    if '层级' in all_error_text or 'depth' in all_error_text or 'level' in all_error_text or '超出' in all_error_text or 'limit' in all_error_text:
                        error_messages = [str(e.get('detail', '')) for e in errors]
                        logging.error(f"✗ 创建资源页面失败（层级限制）：{', '.join(error_messages)}")
                        logging.warning(f"⚠ 资源页面无法创建在父级栏目（ID: {parent_for_api}）下，可能是系统层级限制")
                    else:
                        error_messages = [str(e.get('detail', '')) for e in errors]
                        logging.error(f"✗ 创建资源页面失败：{', '.join(error_messages)}")
                    
                    return None
                except Exception as e:
                    logging.error(f"✗ 创建资源页面失败，解析错误信息时出错：{e}")
                    return None
            
            # 检查响应状态
            if not response.ok:
                try:
                    error_data = response.json()
                    errors = error_data.get('errors', [])
                    error_messages = [str(e.get('detail', '')) for e in errors]
                    logging.error(f"✗ 创建资源页面失败：{', '.join(error_messages)}")
                except:
                    logging.error(f"✗ 创建资源页面失败：HTTP {response.status_code}")
                return None
            
            # 响应成功，处理结果
            result = response.json()
            page_data = result.get('data', {})
            page_id = page_data.get('id')
            
            if page_id:
                # 缓存页面路径和 slug
                self._page_slug_cache[cache_key] = int(page_id)
                full_path = page_data.get('attributes', {}).get('full_path', '')
                if full_path:
                    self._page_path_to_id_cache[full_path] = int(page_id)
                
                # 更新限制参数中的当前数量计数
                self.update_limits_count(1)
                
                logging.info(f"✓ 成功创建资源页面 '{name}'，ID: {page_id}")
                return result
            else:
                logging.warning(f"创建资源页面 '{name}' 成功但未返回 ID")
                return None
            
        except Exception as e:
            logging.error(f"创建资源页面失败：{e}")
            if self.debug:
                import traceback
                logging.error(traceback.format_exc())
                if 'response' in locals():
                    logging.error(f"响应状态码: {response.status_code}")
                    logging.error(f"响应内容: {response.text[:500]}")
            return None
    
    def get_channel_name(self, page_id: int) -> Optional[str]:
        """
        获取栏目名称（通过页面ID）
        
        Args:
            page_id: 页面ID
        
        Returns:
            栏目名称，如果获取失败返回None
        """
        if page_id <= 0:
            return None
        
        try:
            get_url = f"{self.base_url}/sites/{self.site_id}/pages/{page_id}"
            response = self.session.get(get_url, params={"fields[pages]": "id,name"})
            if response.ok:
                result = response.json()
                page_data = result.get('data', {})
                page_attrs = page_data.get('attributes', {})
                return page_attrs.get('name', '')
        except Exception as e:
            logging.debug(f"获取栏目名称失败（page_id: {page_id}）：{e}")
        
        return None
    
    def get_or_create_channel_path(self, path: str, collection_id_getter=None) -> Optional[int]:
        """
        根据路径创建层级栏目，返回最深层级的栏目ID
        
        例如：路径 "00-共享盘/00-素材库/03-产品展示图"
        会创建：
        - 栏目1：00-共享盘（根级）
        - 栏目2：00-素材库（父级：栏目1）
        - 栏目3：03-产品展示图（父级：栏目2）
        
        返回栏目3的ID
        
        Args:
            path: 目录路径（支持 Windows 的 \\ 和 Mac/Linux 的 / 分隔符）
            collection_id_getter: 函数，接收 (路径部分, 父集合ID) 返回集合ID（可选）
        
        Returns:
            最深层级栏目的ID，如果路径为空则返回None
        """
        if not path or not path.strip():
            return None
        
        # 标准化路径分隔符（兼容 Windows 和 Mac/Linux）
        normalized_path = path.replace('\\', '/')
        
        # 分割路径（使用正斜线）
        path_parts = [p.strip() for p in normalized_path.split('/') if p.strip()]
        if not path_parts:
            return None
        
        # 检查缓存
        cache_key = '/' + '/'.join(path_parts)
        if cache_key in self._page_path_to_id_cache:
            cached_id = self._page_path_to_id_cache[cache_key]
            logging.info("✓ 从缓冲命中栏目路径: %s，ID: %s", cache_key, cached_id)
            return cached_id
        
        # 获取站点栏目的最大层级（max_depth - 1，为资源页面留出空间）
        max_channel_depth = self.get_max_channel_depth()
        logging.debug(f"站点栏目最大层级限制：{max_channel_depth}（站点最大层级 - 2）")
        
        # 逐级创建栏目；站点根是首页，从首页 ID 开始
        current_parent_id = self.get_home_page_id()  # 从站点首页开始
        if current_parent_id is None:
            logging.warning("无法获取站点首页 ID，无法创建栏目路径")
            return None
        current_collection_parent_id = None  # 当前集合的父级ID
        current_depth = 0  # 当前层级（0 是首页）
        
        for i, part in enumerate(path_parts):
            # 计算当前层级（从1开始，因为0是首页）
            current_depth = i + 1
            
            # 检查是否超过最大层级限制（在检查缓存之前先检查层级）
            if current_depth > max_channel_depth:
                # 获取父级栏目名称用于日志
                parent_channel_name = None
                if current_parent_id is not None:
                    parent_channel_name = self.get_channel_name(current_parent_id)
                if parent_channel_name:
                    logging.info(f"⚠ 栏目路径 '{path}' 在 '{part}' 处超过最大层级限制（当前层级: {current_depth}, 最大层级: {max_channel_depth}），父级栏目: '{parent_channel_name}'（ID: {current_parent_id}），停止创建")
                else:
                    logging.info(f"⚠ 栏目路径 '{path}' 在 '{part}' 处超过最大层级限制（当前层级: {current_depth}, 最大层级: {max_channel_depth}），停止创建")
                # 缓存当前路径和后续所有路径到最深层级栏目ID的映射
                if current_parent_id is not None:
                    current_path = '/' + '/'.join(path_parts[:i+1])
                    self._page_path_to_id_cache[current_path] = current_parent_id
                    for j in range(i + 1, len(path_parts)):
                        remaining_path = '/' + '/'.join(path_parts[:j+1])
                        self._page_path_to_id_cache[remaining_path] = current_parent_id
                    return current_parent_id
                return None
            
            # 检查当前路径是否已缓存
            current_path = '/' + '/'.join(path_parts[:i+1])
            if current_path in self._page_path_to_id_cache:
                cached_parent_id = self._page_path_to_id_cache[current_path]
                # 如果缓存的路径层级已经达到或超过限制，不应该继续使用
                if current_depth >= max_channel_depth:
                    # 获取缓存的栏目名称用于日志
                    cached_channel_name = self.get_channel_name(cached_parent_id) if cached_parent_id is not None else None
                    if cached_channel_name:
                        logging.info(f"⚠ 栏目路径 '{path}' 在 '{part}' 处已达到最大层级限制（当前层级: {current_depth}, 最大层级: {max_channel_depth}），使用缓存的父级栏目 ID: {cached_parent_id}，栏目名称: '{cached_channel_name}'")
                    else:
                        logging.info(f"⚠ 栏目路径 '{path}' 在 '{part}' 处已达到最大层级限制（当前层级: {current_depth}, 最大层级: {max_channel_depth}），使用缓存的父级栏目 ID: {cached_parent_id}")
                    # 返回缓存的父级栏目 ID（这是最深层级）
                    current_parent_id = cached_parent_id
                    # 缓存后续所有路径到最深层级栏目ID的映射
                    for j in range(i + 1, len(path_parts)):
                        remaining_path = '/' + '/'.join(path_parts[:j+1])
                        self._page_path_to_id_cache[remaining_path] = cached_parent_id
                    return cached_parent_id
                else:
                    # 缓存的路径层级未达到限制，可以继续使用
                    current_parent_id = cached_parent_id
                    continue
            
            # 获取当前路径部分对应的集合 ID
            collection_id = None
            if collection_id_getter:
                try:
                    collection_id = collection_id_getter(part, current_collection_parent_id)
                    if collection_id:
                        collection_id = int(collection_id)
                except Exception as e:
                    logging.warning(f"获取集合 ID 失败（路径部分：{part}）：{e}")
            
            # 创建栏目（使用当前时间作为发布时间）
            published_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # 在创建栏目之前，再次检查层级（防止在创建过程中层级发生变化）
            if current_depth > max_channel_depth:
                logging.info(f"⚠ 栏目路径 '{path}' 在 '{part}' 处超过最大层级限制（当前层级: {current_depth}, 最大层级: {max_channel_depth}），停止创建")
                if current_parent_id is not None:
                    self._page_path_to_id_cache[current_path] = current_parent_id
                    for j in range(i + 1, len(path_parts)):
                        remaining_path = '/' + '/'.join(path_parts[:j+1])
                        self._page_path_to_id_cache[remaining_path] = current_parent_id
                    return current_parent_id
                return None
            
            channel_result = self.create_channel(
                name=part,
                collection_id=collection_id if collection_id else 0,  # 如果没有集合 ID，使用 0
                parent_id=current_parent_id,
                published=True,
                published_at=published_at
            )
            
            if not channel_result:
                # 如果创建失败，可能是层级超出限制
                # 根据需求，返回上一级栏目ID（最深层级），并停止后续层级创建
                if current_parent_id is not None:
                    logging.info(f"⚠ 栏目路径 '{path}' 在 '{part}' 处无法继续创建（可能是层级超出限制），使用上一级栏目 ID: {current_parent_id}，停止后续层级创建")
                    # 缓存当前路径到最深层级栏目ID的映射
                    self._page_path_to_id_cache[current_path] = current_parent_id
                    # 缓存后续所有路径到最深层级栏目ID的映射，避免重复尝试
                    for j in range(i + 1, len(path_parts)):
                        remaining_path = '/' + '/'.join(path_parts[:j+1])
                        self._page_path_to_id_cache[remaining_path] = current_parent_id
                    return current_parent_id
                else:
                    logging.warning(f"无法创建栏目路径 '{path}'，在 '{part}' 处失败")
                    return None
            
            page_data = channel_result.get('data', {})
            page_id = page_data.get('id')
            
            # 检查是否是数量/层级限制的特殊标记
            if page_data.get('_count_limit'):
                # 站点页面数量已达上限：不缓存、不返回父级，该路径视为未创建，调用方可据此判断失败
                if current_parent_id is not None:
                    logging.info(f"⚠ 站点页面数量已达上限，路径 '{path}' 未创建，不缓存、返回 None")
                return None
            if page_data.get('_depth_limit'):
                # 栏目层级超出限制：返回父级 ID 并缓存，供后续使用父级栏目
                if current_parent_id is not None:
                    logging.info(f"⚠ 栏目层级超出限制，使用父级栏目 ID: {current_parent_id}，停止后续层级创建")
                    self._page_path_to_id_cache[current_path] = current_parent_id
                    for j in range(i + 1, len(path_parts)):
                        remaining_path = '/' + '/'.join(path_parts[:j+1])
                        self._page_path_to_id_cache[remaining_path] = current_parent_id
                    return current_parent_id
                return None
            
            if page_id:
                current_parent_id = int(page_id)
                # 获取栏目名称用于日志（API 可能返回空字符串，用 part 兜底）
                channel_name = (page_data.get('attributes', {}) or {}).get('name') or part
                # 缓存路径
                self._page_path_to_id_cache[current_path] = current_parent_id
                # 更新限制参数中的当前最大层级
                self.update_limits_depth(current_depth)
                # 更新当前集合的父级ID（用于下一级）
                if collection_id:
                    current_collection_parent_id = collection_id
                
                # 检查是否已达到最大层级限制（创建完这一层后，下一层会超出限制）
                if current_depth >= max_channel_depth:
                    logging.info(f"⚠ 栏目路径 '{path}' 在 '{part}'（栏目名称: '{channel_name}'，ID: {current_parent_id}）处已达到最大层级限制（当前层级: {current_depth}, 最大层级: {max_channel_depth}），停止创建后续层级")
                    # 缓存后续所有路径到最深层级栏目ID的映射
                    for j in range(i + 1, len(path_parts)):
                        remaining_path = '/' + '/'.join(path_parts[:j+1])
                        self._page_path_to_id_cache[remaining_path] = current_parent_id
                    return current_parent_id
            else:
                logging.warning(f"创建栏目 '{part}' 成功但未返回 ID")
                return current_parent_id if current_parent_id is not None else None
        
        # 返回最深层级栏目的ID
        # 获取最深层级栏目的名称用于日志
        final_channel_name = None
        if current_parent_id is not None:
            final_channel_name = self.get_channel_name(current_parent_id)
        if final_channel_name:
            logging.debug(f"栏目路径 '{path}' 创建完成，最深层级栏目 ID: {current_parent_id}，栏目名称: '{final_channel_name}'")
        else:
            logging.debug(f"栏目路径 '{path}' 创建完成，最深层级栏目 ID: {current_parent_id}")
        return current_parent_id

