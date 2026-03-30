# Baklib 导入脚本：执行说明（Runbook）

考虑到不同客户需求，导入入口拆分为两个脚本：

- `baklib_import/import_files_to_dam.py`：**仅导入到 DAM**（不创建站点页面）
- `baklib_import/import_files_to_site.py`：**导入到站点页面**（即 **DAM + Page** 都导入）

## 依赖

```bash
pip install openpyxl requests
```

（或与仓库根目录 `requirements.txt` 一致。）

## 文件布局

在 `baklib_import/` 中需包含：

- `import_files_to_dam.py`（入口：仅 DAM）
- `import_files_to_site.py`（入口：DAM + Page）
- `import_files_to_dam_and_pages.py`（核心实现：被以上两个入口复用）
- `excel_reader.py`、`path_processor.py`、`create_directories_and_tags.py`
- `dam_collections.py`、`dam_tags.py`、`dam_upload.py`
- `site_pages.py`、`site_tags.py`
- 可选：`prepare_directories_and_tags.py`（仅预创建目录/标签，不上传文件）

## 配置文件示例

复制 `config.example.json` 为 `config.json`，填写：

- `site_id`：目标站点 ID
- `api.access_key` / `api.secret_key`：Open API 密钥
- `import.path_prefix`：从完整路径中剥掉的前缀（支持多个，逗号分隔），需与实际 Excel 中路径写法一致
- `import.skip_directories`：可选，相对 `path_prefix` 的路径片段列表，匹配到的目录及其子目录将跳过
- `import.columns`：`path` / `tags` / `new_dir` 对应列字母

脚本支持 UTF-8 BOM、GBK 等多种编码读取 JSON（Windows 记事本保存的 UTF-8 BOM 亦可）。

## 命令示例

```bash
# DAM + Page（推荐默认）
python import_files_to_site.py --excel ./file_list.xlsx --config config.json

# 仅 DAM
python import_files_to_dam.py --excel ./file_list.xlsx --config config.json
```

不使用配置文件时：

```bash
python import_files_to_site.py \
  --excel ./file_list.xlsx \
  --api-key "access_key:secret_key" \
  --site-id 123 \
  --base-url "https://open.baklib.com/api/v1"
```

测试：

```bash
python import_files_to_site.py --excel ./file_list.xlsx --config config.json --dry-run
python import_files_to_site.py --excel ./file_list.xlsx --config config.json --max-rows 10
```

## 预创建目录与标签（可选）

在批量上传前减少重复 API 查询：

```bash
python prepare_directories_and_tags.py --excel ./file_list.xlsx --config config.json
# 或目录下全部 xlsx
python prepare_directories_and_tags.py --directory ./excel_dir --config config.json
```

## 执行结果

- 控制台输出成功 / 失败 / 跳过统计。
- 若配置日志文件，会写入日志。
- Excel 可能被更新（状态列、DAM ID 等）；首次读取前会自动备份。

## 注意事项

1. Excel 中的路径必须在运行环境中真实可读；若在笔记本地调试服务器路径，可在配置中使用路径映射相关项（见脚本内说明）。
2. API 密钥需具备 DAM 与站点内容相关权限。
3. 仅 **CMS** 类型站点支持“导入到站点页面”的页面创建逻辑；Wiki 站点请使用 `import_files_to_dam.py`（仅 DAM）。
4. 大文件上传请保持合理 `delay`，避免触发限流。

## API 参考

具体 HTTP 路径与字段以 **Baklib 官方 Open API 文档** 为准；本仓库脚本随产品迭代可能需要对照最新文档调整。

## 常见问题（Windows）

见 `06-windows-troubleshooting.md`。

---

**最后更新**：2026-03-30

