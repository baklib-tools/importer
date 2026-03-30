# Baklib 导入脚本：快速开始

在 `baklib_import/` 目录下完成配置与执行（所有 `.py` 须在同一目录）。

考虑到不同客户需求，入口拆分为两个脚本：

- `import_files_to_site.py`：导入到站点页面（= **DAM + Page**）
- `import_files_to_dam.py`：仅导入到 DAM（不创建页面）

## 1. 安装依赖

```bash
cd /path/to/importer
pip install -r requirements.txt
```

## 2. 准备 Excel

需包含文件路径列（默认 **E 列**），且与 `extract-file-paths.py` 生成的模板一致时，列号一般为：

- A：打标签
- B：新目录
- E：完整路径

## 3. 配置文件

```bash
cd baklib_import
cp config.example.json config.json
# 编辑 config.json：填写 site_id、access_key、secret_key、path_prefix 等
```

## 4. 执行导入

```bash
# DAM + Page（推荐默认）
python import_files_to_site.py --excel ./your_list.xlsx --config config.json

# 仅 DAM
python import_files_to_dam.py --excel ./your_list.xlsx --config config.json
```

## 常用选项

| 选项 | 说明 |
|------|------|
| `--dry-run` | 不实际上传，仅校验流程 |
| `--max-rows N` | 只处理前 N 行（测试） |
| `--debug` | 打印详细 HTTP 调试信息 |
| `--skip-pages` | 兼容参数：仅上传到 DAM，不创建站点页面（通常直接用 `import_files_to_dam.py` 更直观） |

更完整的参数与配置说明见 `05-import-runbook.md`。

---

**最后更新**：2026-03-30

