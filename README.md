# Baklib Importer

面向「海量文件迁入 Baklib」的一套开源工具：**先在本地把路径清单变成可协作填写的 Excel，再通过 Open API 批量导入 DAM 与站点**。

本仓库从内部客户实施流程整理而来，已去除客户专属信息与密钥，便于在 GitHub 上公开使用。

## 包含什么

| 目录 | 内容 |
|------|------|
| `preprocessing/` | `analyze_file_list.py`：清单统计；`extract-file-paths.py`：按类型拆分并生成带「打标签 / 新目录」的 Excel。**不访问网络。** |
| `baklib_import/` | 基于 Excel 调用 Baklib API，上传 DAM 并创建站点资源页等。需配置 API 密钥。 |
| `docs/` | 流程说明、Excel 列说明、Windows 排障等。 |

## 环境要求

- Python 3.8+（建议 3.10+）
- 依赖：`pip install -r requirements.txt`（`openpyxl`、`requests`）

## 典型流程

1. **导出路径清单**：每行一个文件路径的 UTF-8 文本（Windows / macOS / Linux 均可）。  
2. **预处理**（在仓库根目录 `importer/` 下执行）：

   ```bash
   python3 preprocessing/extract-file-paths.py ./file_list.txt --split 10000 --format excel
   ```

3. **业务填写 Excel**：在「打标签」「新目录」列中完成分类与目录规划（见 `docs/03-excel-guide.md`）。  
4. **API 导入**：

   ```bash
   cd baklib_import
   cp config.example.json config.json
   # 编辑 config.json：site_id、密钥、path_prefix 等
   # DAM + Page
   python import_files_to_site.py --excel ./your.xlsx --config config.json

   # 仅 DAM
   python import_files_to_dam.py --excel ./your.xlsx --config config.json
   ```

首次建议 `--dry-run` 或 `--max-rows 10` 试跑。

## 文档索引

- `docs/00-index.md` — 文档入口（按阅读顺序）  
- `docs/01-workflow-sop.md` — 端到端流程  
- `docs/03-excel-guide.md` — Excel 列含义与填写约定  
- `docs/02-file-list-mac-linux.md` — macOS/Linux 生成路径清单  
- `docs/04-import-quickstart.md` — API 导入快速开始  
- `docs/05-import-runbook.md` — 导入脚本参数与行为说明  
- `docs/06-windows-troubleshooting.md` — Windows 常见问题  
- `preprocessing/README.md` — 预处理脚本说明  

## 安全与隐私

- **切勿**将真实 `config.json`、日志或含内部路径的客户 Excel 提交到公开仓库。  
- 仓库内仅保留 `config.example.json` 占位符。

## 许可证

发布前请在仓库根目录补充 `LICENSE`（若组织有统一许可证策略，由维护者添加）。

---

**维护**：Baklib 工具开源整理 · **最后更新**：2026-03-30
