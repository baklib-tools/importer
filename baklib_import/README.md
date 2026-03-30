# Baklib 文件导入（API）

从已填写的 Excel（路径、标签、目标目录）调用 Baklib Open API，完成：

- DAM 集合与标签
- 文件上传到 DAM
- （可选）站点栏目、资源页与站点标签

## 文件说明

| 文件 | 作用 |
|------|------|
| `import_files_to_dam.py` | 入口：仅导入 DAM（不创建站点页面） |
| `import_files_to_site.py` | 入口：导入到站点页面（= DAM + Page） |
| `import_files_to_dam_and_pages.py` | 核心实现（被以上两个入口复用；兼容历史用法） |
| `prepare_directories_and_tags.py` | 可选：仅预创建目录/标签 |
| `excel_reader.py` | 读 Excel |
| `path_processor.py` | 路径规范化、前缀剥离 |
| `create_directories_and_tags.py` | 目录与标签创建共用逻辑 |
| `dam_*.py` | DAM 集合、标签、上传 |
| `site_*.py` | 站点栏目、页面、标签 |
| `batch_import.py` | 批量任务辅助（按需使用） |

## 快速命令

```bash
pip install -r ../requirements.txt
cp config.example.json config.json
# 编辑 config.json
python import_files_to_site.py --excel ./list.xlsx --config config.json
```

完整说明见 `../docs/04-import-quickstart.md` 与 `../docs/05-import-runbook.md`。

---

**最后更新**：2026-03-30
