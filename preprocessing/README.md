# 文件清单预处理脚本

在将大量文件迁入 Baklib 之前，通常需要：

1. 从客户环境导出「每行一个路径」的文本清单（Windows `dir /s`、macOS/Linux `find` 等）。
2. **可选**：用 `analyze_file_list.py` 做统计与目录结构分析。
3. 用 `extract-file-paths.py` 按类型拆分并生成带「打标签 / 新目录」列的 Excel，供业务人员在本地填写。

本目录脚本**不调用 Baklib API**，仅做本地数据处理。依赖见仓库根目录 `requirements.txt`（Excel 输出需要 `openpyxl`）。

## 用法（在仓库 `importer` 根目录执行）

```bash
cd /path/to/importer

# 分析清单（可选）
python3 preprocessing/analyze_file_list.py /path/to/file_list.txt

# 按类型导出并生成拆分 Excel
python3 preprocessing/extract-file-paths.py /path/to/file_list.txt --split 10000 --format excel
```

输入文件需为 **UTF-8** 文本（每行一条路径）。若来自 Windows GBK 导出，请先转码。

更完整的流程说明见仓库 `docs/01-workflow-sop.md` 与 `docs/03-excel-guide.md`。
