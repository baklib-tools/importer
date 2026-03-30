#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件列表分析程序

功能说明：
==========

本程序用于分析 Windows 系统下通过 `dir /s` 命令导出的文件列表，提供详细的统计和分析功能。

主要功能：
----------

1. **文件编码自动检测**
   - 自动检测文件列表的编码格式（支持 GBK、GB18030、GB2312、UTF-8 等）
   - 智能处理 Windows 系统导出的 GBK 编码文件

2. **目录树构建**
   - 使用哈希树结构构建完整的目录树
   - 每个节点包含：层级、完整路径、文件数、子目录信息
   - 一次遍历即可构建完整树结构，性能高效

3. **文件类型统计**
   - 自动识别文件扩展名（排除目录名中的小数点）
   - 统计各文件类型的数量和占比
   - 支持中文扩展名过滤（如 .黑米纯蛋糕 不会被误识别为扩展名）

4. **目录结构分析**
   - 统计每个目录的文件数和子目录数
   - 按文件数排序，文件数多的目录排在前面
   - 自动过滤文件数为0的目录（根目录除外）

5. **目录树格式输出**
   - 以目录树格式展示目录结构
   - 一行显示：目录名、文件数、子目录数
   - 支持递归层级限制（默认4层）

使用方法：
----------

基本用法：
    python3 preprocessing/analyze_file_list.py <文件列表路径> [根目录] [最大层级]

参数说明：
    - 文件列表路径：Windows dir /s 导出的文件列表文件路径
    - 根目录（可选）：默认 'd:\\FileServer\\Share'
    - 最大层级（可选）：默认 4，限制目录树的递归深度

示例：
    # 使用默认根目录和层级
    python3 preprocessing/analyze_file_list.py ~/Downloads/文件列表-3000.txt

    # 指定根目录和最大层级
    python3 preprocessing/analyze_file_list.py ~/Downloads/文件列表-3000.txt 'd:\\FileServer\\Share' 4

    # 只指定最大层级（使用默认根目录）
    python3 preprocessing/analyze_file_list.py ~/Downloads/文件列表-3000.txt 4

输出内容：
----------

1. **文件类型统计**
   - 总文件数
   - 文件类型清单（按数量排序，显示前50个）
   - 每种文件类型的数量和占比

2. **目录树统计**
   - 目录树格式展示（缩进表示层级）
   - 每个目录显示：目录名、文件数、子目录数
   - 按文件数从大到小排序

3. **汇总统计**
   - 总目录数
   - 总子目录关系数
   - 平均每个目录的文件数
   - 各层级统计

输出文件：
----------

程序会在输入文件同目录下生成：
- `文件列表分析结果.txt`：详细的统计结果（包含所有文件类型和目录树）

技术特点：
----------

1. **高性能**
   - 使用哈希树结构，O(n×m) 复杂度（n=路径数，m=平均路径深度）
   - 一次遍历构建完整树结构，无需多次扫描

2. **智能识别**
   - 自动识别文件和目录（通过路径结构和扩展名）
   - 排除目录名中的小数点（如 2022.9月、.黑米纯蛋糕 等）

3. **编码兼容**
   - 自动检测文件编码
   - 支持 Windows GBK 编码文件在 macOS 上处理

4. **灵活配置**
   - 支持自定义根目录
   - 支持限制递归层级
   - 支持原始顺序或排序处理

作者：AI Assistant
创建时间：2026-01-02
最后更新：2026-01-02
位置：preprocessing/analyze_file_list.py
"""

import os
import sys
from collections import defaultdict


def detect_file_encoding(file_path):
    """检测文件编码，优先尝试常见编码"""
    encodings = ['utf-8', 'gbk', 'gb18030', 'gb2312', 'utf-16', 'latin1']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                # 尝试读取前几行来验证编码
                for i, line in enumerate(f):
                    if i >= 10:  # 读取前10行验证
                        break
                return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            continue
    
    # 如果都失败，返回 utf-8 并使用 errors='ignore'
    return 'utf-8'


def get_file_extension(path):
    """获取文件扩展名"""
    # 获取路径的最后一部分（文件名或目录名）
    normalized = normalize_path(path)
    if '\\' in normalized:
        last_part = normalized.split('\\')[-1]
    elif '/' in normalized:
        last_part = normalized.split('/')[-1]
    else:
        last_part = normalized
    
    # 获取扩展名
    ext = os.path.splitext(last_part)[1].lower()
    
    # 排除明显不是扩展名的情况
    if ext:
        # 移除开头的点
        ext_without_dot = ext[1:] if ext.startswith('.') else ext
        
        # 扩展名应该满足以下条件：
        # 1. 长度在1-10个字符之间（常见扩展名如 .txt, .exe, .xlsx 等）
        # 2. 只包含 ASCII 字母和数字（排除中文、特殊字符等）
        # 3. 不能全是数字（排除像 .9月 这样的情况）
        # 4. 必须至少包含一个字母（扩展名通常是字母开头或字母数字组合）
        if (1 <= len(ext_without_dot) <= 10 and 
            ext_without_dot.isascii() and  # 只包含 ASCII 字符（排除中文）
            ext_without_dot.isalnum() and  # 只包含字母和数字
            not ext_without_dot.isdigit() and  # 不能全是数字
            any(c.isalpha() for c in ext_without_dot)):  # 必须至少包含一个字母
            return ext
        else:
            # 不符合扩展名特征，可能是目录名的一部分（如 2022.9月、.黑米纯蛋糕）
            return ''
    
    return ''


def normalize_path(path):
    """标准化路径（统一使用反斜杠）"""
    return path.replace('/', '\\')


def get_directory_level(path, root_dir):
    """计算目录层级（相对于根目录）"""
    root_dir_norm = normalize_path(root_dir).lower()
    path_norm = normalize_path(path).lower()
    
    if not path_norm.startswith(root_dir_norm):
        return -1
    
    # 移除根目录前缀
    relative_path = path_norm[len(root_dir_norm):].strip('\\')
    if not relative_path:
        return 0
    
    # 计算层级（分隔符数量 + 1）
    level = relative_path.count('\\')
    return level


def build_directory_tree(valid_lines):
    """构建目录树结构
    
    树结构：{节点名: {level: 层级, full_path: 完整路径, children: {子节点}}}
    
    Args:
        valid_lines: 有效路径列表（不需要排序，树结构不依赖顺序）
    
    Returns:
        tuple: (tree, directory_set)
            - tree: 目录树结构
            - directory_set: 目录路径集合
    """
    # 根树：{根目录名: {level, full_path, children}}
    tree = {}
    directory_set = set()
    
    def get_or_create_node(parent_node, name, level, full_path):
        """获取或创建节点"""
        if name not in parent_node:
            parent_node[name] = {
                'level': level,
                'full_path': full_path,
                'files': 0,  # 文件数统计
                'subdirs': set(),  # 子目录集合（用于后续构建关系）
                'children': {}
            }
        return parent_node[name]
    
    for i, line in enumerate(valid_lines):
        if (i + 1) % 100000 == 0:
            print(f"   ⏳ 已处理: {i + 1:,} / {len(valid_lines):,} 条路径...", end='\r')
        
        line_norm = normalize_path(line).lower()
        
        # 解析路径
        parts = line_norm.split('\\')
        if not parts:
            continue
        
        # 处理 Windows 路径（如 d:\...）
        if parts[0].endswith(':'):
            # 根目录（如 d:）
            root_name = parts[0]
            root_path = root_name + '\\'
            
            # 获取或创建根节点
            root_node = get_or_create_node(tree, root_name, 1, root_path)
            directory_set.add(root_path)  # 根目录是目录
            
            # 遍历路径的各个部分，构建树结构
            current_node = root_node
            current_path = root_path
            level = 2
            
            # 判断最后一个部分是否是文件（通过扩展名判断）
            # 使用 get_file_extension 来判断，因为它有更完善的扩展名验证逻辑
            ext = get_file_extension(line)
            last_part_is_file = (ext != '')
            
            # 处理目录部分（除了最后一个，如果是文件的话）
            max_index = len(parts) - 1 if last_part_is_file else len(parts)
            
            for j in range(1, max_index):
                if not parts[j]:  # 跳过空部分
                    continue
                
                # 构建当前路径
                if current_path.endswith('\\'):
                    current_path = current_path + parts[j]
                else:
                    current_path = current_path + '\\' + parts[j]
                
                # 是目录，添加到树中
                current_node = get_or_create_node(current_node['children'], parts[j], level, current_path)
                directory_set.add(current_path)  # 目录添加到集合
                level += 1
        else:
            # 处理相对路径或其他格式
            current_node = None
            current_path = ''
            level = 1
            
            # 判断最后一个部分是否是文件（通过扩展名判断）
            # 使用 get_file_extension 来判断，因为它有更完善的扩展名验证逻辑
            ext = get_file_extension(line)
            last_part_is_file = (ext != '')
            max_index = len(parts) - 1 if last_part_is_file else len(parts)
            
            for j, part in enumerate(parts[:max_index]):
                if not part:  # 跳过空部分
                    continue
                
                # 构建当前路径
                if current_path:
                    current_path = current_path + '\\' + part
                else:
                    current_path = part
                
                # 是目录，添加到树中
                if current_node is None:
                    # 创建根节点
                    current_node = get_or_create_node(tree, part, level, current_path)
                else:
                    current_node = get_or_create_node(current_node['children'], part, level, current_path)
                directory_set.add(current_path)  # 目录添加到集合
                level += 1
    
    return tree, directory_set


def find_node_in_tree(tree, full_path, root_dir='d:\\FileServer\\Share'):
    """在目录树中查找指定路径的节点"""
    if not full_path:
        return None
    
    path_norm = normalize_path(full_path).lower()
    root_dir_norm = normalize_path(root_dir).lower()
    
    if not path_norm.startswith(root_dir_norm):
        return None
    
    # 解析路径
    parts = path_norm.split('\\')
    if not parts:
        return None
    
    # 处理 Windows 路径（如 d:\...）
    if parts[0].endswith(':'):
        # 根目录（如 d:）
        root_name = parts[0]
        if root_name not in tree:
            return None
        
        current_node = tree[root_name]
        
        # 遍历路径的各个部分
        for j in range(1, len(parts)):
            if not parts[j]:  # 跳过空部分
                continue
            
            if parts[j] not in current_node['children']:
                return None
            
            current_node = current_node['children'][parts[j]]
        
        return current_node
    else:
        # 处理相对路径或其他格式
        current_node = None
        for j, part in enumerate(parts):
            if not part:  # 跳过空部分
                continue
            
            if current_node is None:
                if part not in tree:
                    return None
                current_node = tree[part]
            else:
                if part not in current_node['children']:
                    return None
                current_node = current_node['children'][part]
        
        return current_node


def find_root_node_in_tree(tree, root_dir):
    """在目录树中查找根目录节点（支持多种查找策略）"""
    if not tree:
        return None
    
    root_dir_norm = normalize_path(root_dir).lower()
    
    def find_node_by_path(node, target_path):
        """递归查找指定路径的节点"""
        if not node:
            return None
        
        node_path_norm = normalize_path(node['full_path']).lower()
        if node_path_norm == target_path:
            return node
        
        # 递归查找子节点
        for child_name, child_node in node['children'].items():
            found = find_node_by_path(child_node, target_path)
            if found:
                return found
        
        return None
    
    # 策略1：精确匹配
    for root_name, root_node_candidate in tree.items():
        found_node = find_node_by_path(root_node_candidate, root_dir_norm)
        if found_node:
            return found_node
    
    # 策略2：逐步向上查找父目录
    root_parts = root_dir_norm.rstrip('\\').split('\\')
    for i in range(len(root_parts), 0, -1):
        search_path = '\\'.join(root_parts[:i])
        if not search_path.endswith('\\') and i > 1:
            search_path += '\\'
        
        for root_name, root_node_candidate in tree.items():
            found_node = find_node_by_path(root_node_candidate, search_path)
            if found_node:
                return found_node
    
    # 策略3：使用第一个根节点，尝试查找目标路径
    first_root = list(tree.values())[0]
    found_node = find_node_by_path(first_root, root_dir_norm)
    if found_node:
        return found_node
    
    # 策略4：如果都找不到，返回第一个根节点
    return first_root


def analyze_file_list(file_path, root_dir='d:\\FileServer\\Share', max_level=4):
    """分析文件列表"""
    
    # 统计变量
    total_files = 0
    file_types = defaultdict(int)
    
    print(f"📊 开始分析文件列表...")
    print(f"📁 根目录: {root_dir}")
    print(f"📏 最大递归层级: {max_level}")
    print()
    
    processed = 0
    
    # 检测文件编码
    detected_encoding = detect_file_encoding(file_path)
    print(f"📝 检测到文件编码: {detected_encoding}")
    print()
    
    try:
        # 第一步：读取所有行到内存
        print("📖 读取文件内容...")
        all_lines = []
        with open(file_path, 'r', encoding=detected_encoding, errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line:
                    all_lines.append(line)
        
        print(f"✅ 共读取 {len(all_lines):,} 行")
        print()
        
        # 检查是否在根目录下
        root_dir_norm = normalize_path(root_dir).lower()
        
        # 第二步：过滤有效路径（在根目录下的路径）
        print("🔍 第一步：过滤有效路径...")
        valid_lines = []
        
        for line in all_lines:
            line_norm = normalize_path(line).lower()
            if line_norm.startswith(root_dir_norm):
                valid_lines.append(line)
        
        print(f"   有效路径: {len(valid_lines):,} 条")
        print()
        
        # 第三步：识别目录：构建嵌套树结构
        # 注意：使用哈希树结构，不需要排序，无论路径顺序如何都能正确构建
        print("   构建目录树...")
        tree, directory_set = build_directory_tree(valid_lines)
        print(f"\n✅ 识别完成，共 {len(directory_set):,} 个目录")
        print()
        
        # 第四步：根据目录集合进行统计
        print("📊 第二步：统计分析...")
        for line in valid_lines:
            processed += 1
            if processed % 100000 == 0:
                print(f"⏳ 已处理: {processed:,} / {len(valid_lines):,} 条路径...", end='\r')
            
            line_norm = normalize_path(line).lower()
            
            # 判断是文件还是目录
            is_file_path = line_norm not in directory_set
            
            # 根据判断结果处理文件和目录
            if is_file_path:
                # 统计文件
                total_files += 1
                ext = get_file_extension(line)
                file_types[ext] += 1
                
                # 获取文件所在目录（使用原始路径，因为需要保持大小写）
                line_original = normalize_path(line)
                if '\\' in line_original:
                    file_dir_norm = '\\'.join(line_original.split('\\')[:-1])
                elif '/' in line_original:
                    file_dir_norm = '/'.join(line_original.split('/')[:-1])
                else:
                    file_dir_norm = line_original
                
                # 更新文件所在目录及其所有父目录的统计（直接在树中更新）
                # 从文件所在目录开始，向上遍历到根目录
                current_dir = file_dir_norm
                
                while current_dir.lower().startswith(root_dir_norm):
                    dir_level = get_directory_level(current_dir, root_dir)
                    if 0 <= dir_level <= max_level:
                        # 在树中查找节点并更新文件计数
                        node = find_node_in_tree(tree, current_dir, root_dir)
                        if node:
                            node['files'] += 1
                    
                    # 获取父目录
                    if current_dir.lower() == root_dir_norm:
                        break
                    # 手动获取父目录
                    if '\\' in current_dir:
                        parts = current_dir.split('\\')
                        if len(parts) > 1:
                            current_dir = '\\'.join(parts[:-1])
                        else:
                            break
                    else:
                        break
    
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    print(f"\n✅ 处理完成，共处理 {processed:,} 行")
    print()
    
    # 从树中提取目录统计信息（用于兼容现有代码）
    print("🔗 从树中提取目录统计...")
    directory_stats = {}
    
    def extract_stats_from_tree(node, parent_path="", max_level=4):
        """从树节点递归提取统计信息"""
        if not node:
            return
        
        full_path = node['full_path']
        level = node['level']
        
        if level > max_level:
            return
        
        # 构建子目录集合
        subdirs = set()
        for child_name, child_node in node['children'].items():
            if child_node['level'] <= max_level:
                subdirs.add(child_node['full_path'])
        
        # 添加到统计中
        directory_stats[full_path] = {
            'files': node['files'],
            'subdirs': subdirs,
            'level': level
        }
        
        # 递归处理子节点
        for child_name, child_node in node['children'].items():
            extract_stats_from_tree(child_node, full_path, max_level)
    
    # 从根节点开始提取
    root_dir_norm = normalize_path(root_dir).lower()
    for root_name, root_node in tree.items():
        extract_stats_from_tree(root_node, "", max_level)
    
    print("✅ 目录统计提取完成")
    print()
    
    return {
        'total_files': total_files,
        'file_types': dict(file_types),
        'directory_stats': directory_stats,
        'tree': tree  # 也返回树结构，方便后续使用
    }


def print_statistics(results, root_dir='d:\\FileServer\\Share', max_level=4):
    """打印统计结果"""
    if not results:
        print("❌ 没有统计数据")
        return
    
    print("=" * 80)
    print("📊 文件列表分析结果")
    print("=" * 80)
    print()
    
    # 1. 总文件数
    print(f"📁 **总文件数**: {results['total_files']:,}")
    print()
    
    # 2. 文件类型统计
    file_types = results['file_types']
    print(f"📋 **文件类型数**: {len(file_types)}")
    print()
    print("📝 **文件类型清单** (按数量排序，显示前50个):")
    print()
    
    # 按数量排序
    sorted_types = sorted(file_types.items(), key=lambda x: x[1], reverse=True)
    
    # 显示前50个最常见的类型
    for i, (ext, count) in enumerate(sorted_types[:50], 1):
        percentage = (count / results['total_files'] * 100) if results['total_files'] > 0 else 0
        # 如果扩展名为空字符串，显示为 "(无扩展名)"
        ext_display = ext if ext else '(无扩展名)'
        print(f"  {i:2d}. {ext_display:20s} : {count:>10,} 个 ({percentage:>5.2f}%)")
    
    if len(sorted_types) > 50:
        print(f"\n  ... 还有 {len(sorted_types) - 50} 种文件类型")
    
    print()
    print("=" * 80)
    print()
    
    # 3. 目录统计（目录树格式）
    print("📂 **目录统计** (以 d:\\FileServer\\Share 为根目录，递归4层)")
    print()
    
    tree = results.get('tree', {})
    root_dir_norm = normalize_path(root_dir).lower()
    
    def print_directory_tree_from_node(node, indent="", max_level=4, is_root=False):
        """从树节点递归打印目录树"""
        if not node:
            return
        
        level = node['level']
        full_path = node['full_path']
        
        # 如果超过最大层级，不显示
        if level > max_level:
            return
        
        # 获取子节点列表
        children = list(node['children'].items())
        
        # 递归计算节点的总文件数（包括所有子目录的文件）
        def get_total_files_recursive(child_node):
            """递归计算节点及其所有子节点的文件总数"""
            total = child_node['files']
            for sub_child_name, sub_child_node in child_node['children'].items():
                total += get_total_files_recursive(sub_child_node)
            return total
        
        # 过滤：只显示有文件的目录（直接文件或子目录有文件），并按总文件数排序
        children_with_files = []
        for child_name, child_node in children:
            total_files = get_total_files_recursive(child_node)
            if total_files > 0:
                children_with_files.append((child_name, child_node, total_files))
        
        # 按总文件数排序（从大到小）
        children_with_files.sort(key=lambda x: x[2], reverse=True)
        # 移除总文件数，只保留节点信息
        children_with_files = [(name, node) for name, node, _ in children_with_files]
        
        # 获取目录名
        if '\\' in full_path:
            dir_name = full_path.split('\\')[-1]
        elif '/' in full_path:
            dir_name = full_path.split('/')[-1]
        else:
            dir_name = full_path
        
        # 如果是根目录，显示完整路径
        if is_root:
            dir_name = full_path
        
        file_count = node['files']
        subdir_count = len(children_with_files)
        
        # 显示目录（根目录始终显示，其他目录显示：文件数>0 或 有子目录）
        should_display = is_root or file_count > 0 or subdir_count > 0
        if should_display:
            print(f"{indent}{dir_name}  [文件: {file_count:,} | 子目录: {subdir_count}]")
        
        # 递归打印子目录
        for child_name, child_node in children_with_files:
            print_directory_tree_from_node(child_node, indent + "  ", max_level, False)
    
    # 从树中查找根目录节点
    root_node = find_root_node_in_tree(tree, root_dir)
    root_dir_norm_check = normalize_path(root_dir).lower()
    
    if root_node:
        # 调试信息：显示找到的根节点信息
        root_path_found = root_node['full_path']
        root_path_found_norm = normalize_path(root_path_found).lower()
        if root_path_found_norm != root_dir_norm_check:
            if root_path_found_norm == normalize_path(list(tree.values())[0]['full_path']).lower():
                print(f"⚠️  注意: 未找到精确匹配 '{root_dir}'，使用树中的第一个根节点 '{root_path_found}' 作为起始点")
                print(f"   提示: 将从 '{root_path_found}' 开始显示目录树")
            else:
                print(f"ℹ️  从节点 '{root_path_found}' 开始显示目录树（目标: '{root_dir}'）")
        print_directory_tree_from_node(root_node, "", max_level, True)
    else:
        print("⚠️  警告: 无法找到根目录，跳过目录树显示")
    print()
    
    print("=" * 80)
    
    # 4. 汇总统计
    print()
    print("📈 **汇总统计**:")
    print()
    directory_stats = results['directory_stats']
    total_dirs = len(directory_stats)
    total_subdirs = sum(len(stats['subdirs']) for stats in directory_stats.values())
    avg_files = results['total_files'] / total_dirs if total_dirs > 0 else 0
    print(f"  - 总目录数: {total_dirs:,}")
    print(f"  - 总子目录关系数: {total_subdirs:,}")
    print(f"  - 平均每个目录的文件数: {avg_files:.2f}")
    
    # 各层级统计
    print()
    print("📊 **各层级统计**:")
    dirs_by_level = defaultdict(list)
    for path, stats in directory_stats.items():
        level = stats['level']
        if 0 <= level <= max_level:
            dirs_by_level[level].append((path, stats))
    
    for level in sorted(dirs_by_level.keys()):
        dirs = dirs_by_level[level]
        total_files_in_level = sum(stats['files'] for _, stats in dirs)
        total_subdirs_in_level = sum(len(stats['subdirs']) for _, stats in dirs)
        print(f"  第 {level} 层: {len(dirs):,} 个目录, {total_files_in_level:,} 个文件, {total_subdirs_in_level:,} 个子目录")


def save_results_to_file(results, output_file, root_dir, max_level=4):
    """保存结果到文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("文件列表分析结果\n")
        f.write("=" * 80 + "\n\n")
        
        # 总文件数
        f.write(f"总文件数: {results['total_files']:,}\n\n")
        
        # 文件类型
        f.write(f"文件类型数: {len(results['file_types'])}\n\n")
        f.write("文件类型清单 (按数量排序):\n\n")
        
        sorted_types = sorted(results['file_types'].items(), key=lambda x: x[1], reverse=True)
        for i, (ext, count) in enumerate(sorted_types, 1):
            percentage = (count / results['total_files'] * 100) if results['total_files'] > 0 else 0
            # 如果扩展名为空字符串，显示为 "(无扩展名)"
            ext_display = ext if ext else '(无扩展名)'
            f.write(f"  {i:4d}. {ext_display:30s} : {count:>12,} 个 ({percentage:>6.2f}%)\n")
        
        f.write("\n" + "=" * 80 + "\n\n")
        
        # 目录统计（目录树格式）
        f.write("目录统计 (以 d:\\FileServer\\Share 为根目录，递归4层):\n\n")
        
        tree = results.get('tree', {})
        root_dir_norm = normalize_path(root_dir).lower()
        
        def write_directory_tree_from_node(f, node, indent="", max_level=4, is_root=False):
            """从树节点递归写入目录树"""
            if not node:
                return
            
            level = node['level']
            full_path = node['full_path']
            
            # 如果超过最大层级，不显示
            if level > max_level:
                return
            
            # 获取子节点列表
            children = list(node['children'].items())
            
            # 过滤：只显示文件数大于0的目录，并按文件数排序
            children_with_files = []
            for child_name, child_node in children:
                if child_node['files'] > 0:
                    children_with_files.append((child_name, child_node))
            
            # 按文件数排序（从大到小）
            children_with_files.sort(key=lambda x: x[1]['files'], reverse=True)
            
            # 获取目录名
            if '\\' in full_path:
                dir_name = full_path.split('\\')[-1]
            elif '/' in full_path:
                dir_name = full_path.split('/')[-1]
            else:
                dir_name = full_path
            
            # 如果是根目录，显示完整路径
            if is_root:
                dir_name = full_path
            
            file_count = node['files']
            subdir_count = len(children_with_files)
            
            # 显示目录（根目录始终显示，其他目录只显示文件数大于0的）
            if is_root or file_count > 0:
                f.write(f"{indent}{dir_name}  [文件: {file_count:,} | 子目录: {subdir_count}]\n")
            
            # 递归写入子目录
            for child_name, child_node in children_with_files:
                write_directory_tree_from_node(f, child_node, indent + "  ", max_level, False)
        
        # 从树中查找根目录节点
        root_node = find_root_node_in_tree(tree, root_dir)
        
        if root_node:
            write_directory_tree_from_node(f, root_node, "", max_level, True)
        else:
            f.write("⚠️  警告: 无法找到根目录，跳过目录树显示\n")
        f.write("\n")
        
        # 汇总统计
        f.write("=" * 80 + "\n\n")
        f.write("汇总统计:\n\n")
        directory_stats = results['directory_stats']
        total_dirs = len(directory_stats)
        total_subdirs = sum(len(stats['subdirs']) for stats in directory_stats.values())
        avg_files = results['total_files'] / total_dirs if total_dirs > 0 else 0
        f.write(f"  - 总目录数: {total_dirs:,}\n")
        f.write(f"  - 总子目录关系数: {total_subdirs:,}\n")
        f.write(f"  - 平均每个目录的文件数: {avg_files:.2f}\n")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python3 preprocessing/analyze_file_list.py <文件列表路径> [根目录] [最大层级]")
        print("示例: python3 preprocessing/analyze_file_list.py ~/Downloads/文件列表.txt")
        print("示例: python3 preprocessing/analyze_file_list.py ~/Downloads/文件列表.txt 'd:\\FileServer\\Share' 4")
        print("示例: python3 preprocessing/analyze_file_list.py ~/Downloads/文件列表.txt 4  # 只指定最大层级，使用默认根目录")
        sys.exit(1)
    
    file_path = os.path.expanduser(sys.argv[1])
    
    # 智能识别参数：如果第二个参数是纯数字，则当作 max_level；否则当作 root_dir
    if len(sys.argv) > 2:
        arg2 = sys.argv[2]
        # 检查是否是纯数字
        if arg2.isdigit():
            # 第二个参数是数字，当作 max_level
            root_dir = 'd:\\FileServer\\Share'
            max_level = int(arg2)
        else:
            # 第二个参数是路径，当作 root_dir
            root_dir = arg2
            max_level = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    else:
        root_dir = 'd:\\FileServer\\Share'
        max_level = 4
    
    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        sys.exit(1)
    
    # 分析文件
    results = analyze_file_list(file_path, root_dir, max_level)
    
    if results:
        # 打印统计结果
        print_statistics(results, root_dir, max_level)
        
        # 保存结果到文件
        output_file = os.path.join(os.path.dirname(file_path), '文件列表分析结果.txt')
        save_results_to_file(results, output_file, root_dir, max_level)
        print()
        print(f"💾 详细结果已保存到: {output_file}")


if __name__ == '__main__':
    main()
