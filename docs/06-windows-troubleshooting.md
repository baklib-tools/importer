# Windows 常见问题

## 生成路径清单

与 macOS / Linux 的 `find` 类似，需要得到「每行一个**完整路径**」的文本文件，供 `preprocessing/extract-file-paths.py` 等脚本使用。

### PowerShell（推荐）

- 只列出**文件**（不含子文件夹本身），且默认输出 **UTF-8**，适合含中文的路径。
- 请将 `D:\你的根目录` 换成要扫描的盘符或文件夹；`-ErrorAction SilentlyContinue` 用于跳过无权限目录，避免整批中断。

```powershell
Get-ChildItem -Path "D:\你的根目录" -File -Recurse -ErrorAction SilentlyContinue |
  ForEach-Object { $_.FullName } |
  Set-Content -Path "D:\path\to\file_list.txt" -Encoding utf8
```

若路径极长或含特殊字符，可对根路径使用 `-LiteralPath`。

### 命令提示符（CMD）

`dir /s /b` 会列出**文件与子目录**；无扩展名的目录行在后续预处理里通常不会被当作「待分类文件」，但清单会更「脏」。输出编码多为系统 ANSI（简体中文系统常为 GBK）；本仓库 `analyze_file_list.py`、`compare_file_lists.py` 等会尝试自动识别 GBK/UTF-8，**仍建议优先用 PowerShell 导出 UTF-8**。

```cmd
dir /s /b "D:\你的根目录" > D:\path\to\file_list.txt
```

导出后若 Excel 或脚本里中文乱码，用 VS Code / Notepad++ 将 `file_list.txt` 转为 **UTF-8** 再处理。

---

## JSON 配置文件 BOM

若出现 `Unexpected UTF-8 BOM` 等解析错误：本仓库导入脚本已尝试用 `utf-8-sig`、`utf-8`、GBK 等编码读取配置。若仍失败，请用 VS Code / Notepad++ 将 `config.json` 存为 **UTF-8**（可选「无 BOM」）。

PowerShell 检查是否含 UTF-8 BOM：

```powershell
$bytes = [System.IO.File]::ReadAllBytes("config.json")
if ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    Write-Host "文件包含 UTF-8 BOM"
} else {
    Write-Host "文件不包含 BOM"
}
```

## 路径前缀

Windows 路径在 JSON 中可写为转义反斜杠或正斜杠，例如：

```json
"path_prefix": "d:\\FileServer\\Share"
```

或

```json
"path_prefix": "d:/FileServer/Share"
```

## Python 与依赖

```cmd
python --version
pip install openpyxl requests
python -m pip install openpyxl requests
```

镜像示例：

```cmd
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple openpyxl requests
```

## 权限

确保对 Excel、日志输出目录有读写权限；必要时以管理员身份打开终端。

---

**最后更新**：2026-04-08

