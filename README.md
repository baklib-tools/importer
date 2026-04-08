

# Baklib Importer

**把本机、NAS 或挂载盘上的海量文件，按原有文件夹层级迁入 Baklib 资源库（DAM），并可选同步创建站点资源页。**

适合：资料盘、共享盘、归档目录一次性整理进知识库；清单可协作、导入可断点、规则可配置。

---

## 这套工具解决什么问题？


| 场景                | 说明                                                                                                                                           |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| 📂 **目录结构要保留**    | 去掉盘符/共享根等「路径前缀」后，按剩余路径在 Baklib 里建 **DAM 集合（目录）**；层级过深时按系统限制做截断（见配置 `max_depth`）。                                                             |
| 🏷️ **标签与目录可定制**  | 预处理生成的 Excel 含 **「打标签」「新目录」**；可在表里批量填，覆盖/补充仅靠路径自动推导的结果。                                                                                      |
| 🖥️ **NAS / 多环境** | 支持 **路径前缀**（`path_prefix`）、**跳过部分子目录**（`skip_directories`）；Excel 里是服务器路径、实际在本机挂载目录读文件时，可用 **路径映射**（`excel_path_prefix` + `local_path_root`）。 |
| 📤 **先整理、再上传**    | **预处理脚本全程离线**；导入脚本走 **Open API**，需密钥。可先 `--dry-run` / `--max-rows` 小批量试跑。                                                                    |
| 🔄 **长周期导入后的增量** | 导入耗时数周时，磁盘可能继续新增文件；用 `preprocessing/compare_file_lists.py` 对比「开始时清单」与「重新扫描」可列出仅新增路径，便于第二轮导入。                                        |


一句话：**从「路径清单 → 可编辑 Excel → API 批量导入」**，把文件搬进 Baklib，并尽量让线上目录与你磁盘上的组织方式一致。

---

## 工作流程（四步）

```
导出路径清单（每行一个绝对路径，UTF-8）
        ↓
预处理：分类、拆表、生成带「打标签 / 新目录」的 Excel（可选：先做统计）
        ↓
在 Excel 中填写或批量调整标签与目标目录
        ↓
配置 API → 导入到 DAM（必选） / 同时创建站点页面（可选）
```

- **仅资源库**：`baklib_import/import_files_to_dam.py`  
- **DAM + 站点页面**：`baklib_import/import_files_to_site.py`（CMS 站点；Wiki 站点请仅用 DAM 导入）

---

## 仓库里有什么？


| 路径                    | 作用                                                      |
| --------------------- | ------------------------------------------------------- |
| `preprocessing/`      | 📊 清单分析、按类型拆分、生成 Excel；**不访问网络**。                       |
| `baklib_import/`      | 🚀 读 Excel、调 Baklib Open API：上传文件、建目录/标签、（可选）建栏目与资源页。   |
| `docs/`               | 📖 流程、Excel 列说明、导入参数、排障等。                               |
| `config.example.json` | ⚙️ 配置模板；复制为项目根目录的 `config.json` 后填写密钥与 `path_prefix` 等。 |


---

## 环境要求

- Python **3.8+**（建议 3.10+）
- 依赖：`pip install -r requirements.txt`（含 `openpyxl`、`requests`）

---

## 快速开始（在项目根目录 `importer/`）

**1）准备路径清单**（每行一条路径，**UTF-8** 最稳妥）

- **macOS / Linux**：例如 `find /你的根目录 -type f > file_list.txt`（见 `docs/02-file-list-mac-linux.md`）
- **Windows**：建议用 **PowerShell** 导出为 UTF-8，避免中文路径乱码；命令与注意事项见 `docs/06-windows-troubleshooting.md`（「生成路径清单」一节）

```powershell
# 在 PowerShell 中执行：将 D:\你的根目录 换成实际路径
Get-ChildItem -Path "D:\你的根目录" -File -Recurse -ErrorAction SilentlyContinue |
  ForEach-Object { $_.FullName } |
  Set-Content -Path ".\file_list.txt" -Encoding utf8
```

**2）预处理 → 得到 Excel**

```bash
python3 preprocessing/extract-file-paths.py ./file_list.txt --split 10000 --format excel
```

**3）填写 Excel**  
打开生成目录下的 `.xlsx`，按需填写「打标签」「新目录」（见 `docs/03-excel-guide.md`）

**4）配置并导入**（`config.json` 放在**项目根目录**；`--config` 的相对路径相对项目根，可在任意目录执行命令）

```bash
cp config.example.json config.json
# 编辑 config.json：site_id、access_key、secret_key、import.path_prefix 等

python3 baklib_import/import_files_to_site.py --excel ./your.xlsx --config config.json
# 仅 DAM：python3 baklib_import/import_files_to_dam.py --excel ./your.xlsx --config config.json
```

首次建议：`--dry-run` 或 `--max-rows 10` 试跑。

更多参数（跳过确认、列映射、延迟、预创建目录等）见 `docs/05-import-runbook.md`。

---

## 文档索引


| 文档                                   | 内容                 |
| ------------------------------------ | ------------------ |
| `docs/00-index.md`                   | 总入口与阅读顺序           |
| `docs/01-workflow-sop.md`            | 端到端流程（SOP）         |
| `docs/03-excel-guide.md`             | Excel 列含义与填写约定     |
| `docs/02-file-list-mac-linux.md`     | macOS / Linux 生成清单 |
| `docs/04-import-quickstart.md`       | API 导入快速开始         |
| `docs/05-import-runbook.md`          | 命令行参数与行为说明         |
| `docs/06-windows-troubleshooting.md` | Windows：路径清单、常见问题与排障 |
| `preprocessing/README.md`            | 预处理脚本说明（含清单对比 `compare_file_lists.py`） |
| `baklib_import/README.md`            | 导入模块文件说明           |


---

## 安全与隐私

- 🔒 **切勿**将真实 `config.json`、运行日志或含内部路径的客户 Excel 提交到公开仓库。  
- 仓库内仅保留 `config.example.json`；本地密钥文件为项目根目录的 `config.json`（已被 `.gitignore`）。

---

## 许可证

本项目采用 **MIT License**，详见仓库根目录 `[LICENSE](LICENSE)` 文件。

---

## 相关链接

- [Baklib 官网](https://www.baklib.com)
- [Baklib 模板库（GitHub）](https://github.com/baklib-templates) — CMS / Wiki / 社区主题与示例站点
- [Baklib 技能库](https://github.com/baklib-tools/skills) 提供基于 Baklib 使用的 AI 技能

---

**维护**：Baklib 工具开源整理 · **最后更新**：2026-04-08