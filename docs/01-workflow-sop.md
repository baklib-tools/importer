# 文件导入：标准工作流程（SOP）

> 从「文件路径清单」到「Baklib DAM + 站点页面」的推荐流程概览。

## 一、工具目标

- 分析客户提供的文件路径清单（可能数百万行）。
- 按类型分类，生成便于筛选、批量填写标签与目标目录的 **Excel**。
- 在 Excel 中填写「打标签」「新目录」后，使用 `baklib_import/` 下脚本通过 **Baklib Open API** 上传至 DAM，并创建站点资源页（可选）。

## 二、流程概览

```
接收文件路径清单（TXT）
  ↓
（可选）analyze_file_list.py 分析统计
  ↓
extract-file-paths.py 分类导出 + Excel 拆分
  ↓
业务在 Excel 中填写「打标签」「新目录」
  ↓
import_files_to_site.py（DAM + Page） / import_files_to_dam.py（仅 DAM）导入 Baklib
```

## 三、接收文件清单

- **Windows**：建议用 PowerShell 导出 UTF-8 清单；亦可用 `dir /s /b`（详见 `docs/06-windows-troubleshooting.md`「生成路径清单」）。
- **macOS / Linux**：例如 `find /path/to/root -type f > file_list.txt`（详见 `02-file-list-mac-linux.md`）。
- **编码**：建议统一为 **UTF-8**。
- **格式**：每行一个文件路径。

## 四、分析清单（可选）

在仓库 `importer/` 根目录：

```bash
python3 preprocessing/analyze_file_list.py <文件列表路径> [根目录] [最大层级]
```

- `根目录`（可选）：用于过滤有效路径（按实际改为你的根路径）。
- `最大层级`（可选）：目录树展示深度，默认 `4`。

同目录会生成 `文件列表分析结果.txt`。

## 五、分类导出与 Excel 拆分

```bash
python3 preprocessing/extract-file-paths.py <输入文件路径> --split <每文件行数> --format excel
```

示例：

```bash
python3 preprocessing/extract-file-paths.py ./file_list.txt --split 10000 --format excel
```

输出在输入文件同目录下、以输入文件名为名的文件夹中：各类汇总 TXT，以及按行数拆分的 xlsx。Excel 列说明见 `03-excel-guide.md`。

## 六、交付与填写

将生成的 Excel 交给业务方，按列说明填写「打标签」「新目录」，保存后用于 API 导入。

## 七、注意事项

- **编码**：输入尽量为 UTF-8。
- **体量**：清单很大时用 `--split` 控制单个 Excel 行数。
- **未归类扩展名**：默认仅导出图片 / 视频 / 音频 / Office 等类别，其余不会进入分类文件；可在脚本中扩展扩展名表。

## 八、质量检查（摘要）

- [ ] 输入路径文件可读、编码正确
- [ ] 各类型汇总与拆分文件数量合理
- [ ] Excel 能打开且含「打标签」「新目录」等列
- [ ] 导入前已在测试环境用 `--dry-run` / `--max-rows` 验证

---

**文档版本**：v1.0（开源整理版）  
**最后更新**：2026-03-30

