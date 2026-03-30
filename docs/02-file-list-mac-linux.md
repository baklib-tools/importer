# macOS / Linux 下生成文件清单

在本地用 `find` 生成「每行一个绝对路径」的 UTF-8 文本，供 `preprocessing/extract-file-paths.py` 使用。

## 基本示例

```bash
# 将 YOUR_ROOT 换为实际扫描根目录
find /path/to/YOUR_ROOT -type f > ~/file_list.txt
```

## 排除常见目录

```bash
find /path/to/YOUR_ROOT -type f \
  ! -path "*/\.*" \
  ! -path "*/node_modules/*" \
  ! -path "*/.git/*" \
  ! -path "*/__pycache__/*" \
  > ~/file_list.txt
```

## 编码

若源为 GBK，可先转 UTF-8：

```bash
iconv -f GBK -t UTF-8 file_list_gbk.txt > file_list_utf8.txt
```

## 生成 Excel 拆分文件

在仓库 `importer/` 根目录执行：

```bash
cd /path/to/importer
python3 preprocessing/extract-file-paths.py ~/file_list_utf8.txt --split 10000 --format excel
```

---

**最后更新**：2026-03-30

