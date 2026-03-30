#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建目录与标签（共享逻辑 + 结果缓冲）

本模块封装「根据标签串和目录路径，创建/获取 DAM 标签、DAM 集合、站点标签、站点栏目」的统一逻辑，
供「预创建脚本」和「导入脚本」共用，保证行为一致。

对 (tags_string, target_dir) 的调用结果会缓存在进程内：同一目录/标签组合只请求一次 API，
后续相同路径直接返回缓存，减少大量同目录文件时的重复查询与创建。

维护：Baklib Tools
创建日期：2026-01-29
"""

import copy
import logging
from typing import Any, Callable, Dict, Optional, Tuple

# 类型：DAMCollections / DAMTags / SitePages / SiteTags 由调用方传入，此处不强制类型依赖

# 结果缓冲：key = (tags_string, target_dir)，value = 返回的 result dict（深拷贝后返回给调用方）
_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}


def clear_cache() -> None:
    """清空结果缓冲（例如新开一次批量任务前如需要可调用，一般不必）。"""
    _cache.clear()


def ensure_directories_and_tags(
    tags_string: str,
    target_dir: str,
    *,
    dam_collections: Any = None,
    dam_tags: Any = None,
    site_pages: Any = None,
    site_tags: Any = None,
    collection_id_getter: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
) -> Dict[str, Any]:
    """
    为给定的标签串和目录路径，创建或获取 DAM 标签、DAM 集合、站点标签、站点栏目。

    调用方可以只传入需要的管理器（例如只传 dam_* 不传 site_*），未传入的部分不会执行。

    Args:
        tags_string: 标签串（路径规则提取，用 / 分隔，如 "一级/二级/三级"）
        target_dir: 目标目录路径（路径规则提取，如 "00-共享盘/00-素材库"）
        dam_collections: DAM 集合管理器实例（可选）
        dam_tags: DAM 标签管理器实例（可选）
        site_pages: 站点页面管理器实例（可选）
        site_tags: 站点标签管理器实例（可选）
        collection_id_getter: 站点栏目创建时用于根据路径部分获取集合 ID 的函数 (part, parent_id) -> id。
            若不传且需要创建站点栏目，则内部用 dam_collections.get_or_create_collection 构造。

    Returns:
        dict，包含：
        - tag_ids: List[int]，DAM 标签 ID 列表
        - collection_id: Optional[str]，最深层 DAM 集合 ID
        - site_tag_ids: List[int]，站点标签 ID 列表
        - channel_parent_id: Optional[int]，最深层站点栏目 ID。有目录且创建成功时为最深层栏目 ID；无目录或栏目路径创建失败时为 None（调用方可据此判断失败）。创建栏目时在 site_pages 内传入 API 的 parent_id 始终为首页 ID 或具体父栏目 ID，从不传空。
    """
    # 标准化 key，避免同一目录/标签因首尾空格等导致重复请求
    key = (tags_string.strip() if tags_string else '', target_dir.strip() if target_dir else '')
    if key in _cache:
        logging.info("✓ 从缓冲命中目录/标签（目录=%s，标签=%s），跳过创建", key[1] or '(无)', key[0] or '(无)')
        return copy.deepcopy(_cache[key])

    result: Dict[str, Any] = {
        'tag_ids': [],
        'collection_id': None,
        'site_tag_ids': [],
        'channel_parent_id': None,
    }

    # 1. DAM 标签
    if dam_tags and tags_string:
        result['tag_ids'] = dam_tags.get_or_create_tags_from_string(tags_string)

    # 2. DAM 集合路径
    if dam_collections and target_dir:
        result['collection_id'] = dam_collections.get_or_create_collection_path(target_dir)

    # 3. 站点标签
    if site_tags and tags_string:
        result['site_tag_ids'] = site_tags.get_or_create_tags_from_string(tags_string)

    # 4. 站点栏目路径（依赖 DAM 集合 ID 生成 slug）。创建栏目时 site_pages 内传入 API 的 parent_id 始终有值（首页 ID 或父栏目 ID），不传空；此处仅在有目录且创建成功时写入 channel_parent_id，失败则保持 None 便于调用方判断。
    if site_pages and target_dir:
        getter = collection_id_getter
        if getter is None and dam_collections:
            def _default_getter(part: str, parent_id: Optional[str]) -> Optional[str]:
                return dam_collections.get_or_create_collection(part, parent_id)
            getter = _default_getter
        if getter is not None:
            channel_id = site_pages.get_or_create_channel_path(
                target_dir,
                collection_id_getter=getter
            )
            result['channel_parent_id'] = int(channel_id) if channel_id is not None else None

    _cache[key] = result
    return copy.deepcopy(result)
