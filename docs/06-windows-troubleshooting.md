# Windows 常见问题

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

**最后更新**：2026-03-30

