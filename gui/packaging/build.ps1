# BOSS职位采集器 一键构建脚本（构建机需联网一次）
# 用法: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot           # gui/
$repo = Split-Path -Parent $root                   # 仓库根
$dist = Join-Path $root "dist"
$scratch = Join-Path $dist "scratch"
$stage = Join-Path $dist "BOSS职位采集器"
# dist 根目录可能被杀软/资源管理器握住句柄，只清空 staging 与 scratch，不删 dist 本身
New-Item $stage -ItemType Directory -Force | Out-Null
Get-ChildItem $stage -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
if (Test-Path $scratch) { Remove-Item $scratch -Recurse -Force }
New-Item $scratch -ItemType Directory -Force | Out-Null

# 1) 便携 Python 3.12（版本钉死；官方源失败自动切华为云镜像）
$pyver = "3.12.7"
$zip = Join-Path $scratch "python-embed.zip"
try {
  Invoke-WebRequest "https://www.python.org/ftp/python/$pyver/python-$pyver-embed-amd64.zip" -OutFile $zip -TimeoutSec 60
} catch {
  Write-Host "python.org 下载失败，改用华为云镜像"
  Invoke-WebRequest "https://mirrors.huaweicloud.com/python/$pyver/python-$pyver-embed-amd64.zip" -OutFile $zip -TimeoutSec 120
}
$runtime = Join-Path $stage "runtime"
Expand-Archive $zip $runtime
# 启用 site-packages（embeddable 默认禁用）
$pth = Get-ChildItem $runtime -Filter "python*._pth" | Select-Object -First 1
(Get-Content $pth.FullName) -replace "#import site", "import site" | Set-Content $pth.FullName
# 安装钉死版本的依赖（引擎 + 界面全部第三方库）
Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile (Join-Path $scratch "get-pip.py")
& (Join-Path $runtime "python.exe") (Join-Path $scratch "get-pip.py") --quiet
& (Join-Path $runtime "python.exe") -m pip install --quiet `
  "flask>=3.0,<4" "requests>=2.31,<3" "websocket-client>=1.7,<2"

# 2) 依赖审计：扫描 gui/app 与引擎的全部 import，缺一个直接终止构建
python (Join-Path $PSScriptRoot "audit_imports.py") (Join-Path $repo "gui/app") (Join-Path $repo "scripts")
if ($LASTEXITCODE -ne 0) { throw "依赖审计未通过，停止构建" }

# 3) 引擎与应用（引擎一字不改地复制）
New-Item (Join-Path $stage "engine") -ItemType Directory -Force | Out-Null
Copy-Item (Join-Path $repo "scripts/boss_cdp_raw.py") (Join-Path $stage "engine")
Copy-Item (Join-Path $repo "scripts/job_summary.py") (Join-Path $stage "engine")
New-Item (Join-Path $stage "data") -ItemType Directory -Force | Out-Null
Copy-Item (Join-Path $repo "data/city_codes.json") (Join-Path $stage "data")
New-Item (Join-Path $stage "app") -ItemType Directory -Force | Out-Null
Copy-Item (Join-Path $repo "gui/app/*") (Join-Path $stage "app") -Recurse
Copy-Item (Join-Path $repo "gui/app/static/manual.html") (Join-Path $stage "使用说明.html")

# 4) 启动器 exe（开发机 Python + PyInstaller）
$ico = Join-Path $PSScriptRoot "app.ico"
$iconArgs = if (Test-Path $ico) { " --icon `"$ico`"" } else { "" }
Invoke-Expression ("pyinstaller --onefile --noconsole --name `"启动职位采集器`" --distpath `"$stage`" " + `
  "--workpath `"$scratch\pyinstaller`" --specpath `"$scratch\pyinstaller`"$iconArgs " + `
  "`"$repo\gui\launcher\launcher.py`"")

# 5) bat 入口（与 exe 行为一致）
# 内容必须纯 ASCII：cmd 按 ANSI(GBK) 解析 bat，任何 BOM 或 UTF-8 中文都会变成乱码命令
$bat = Join-Path $stage "启动职位采集器.bat"
$batBody = "@echo off`r`ncd /d `"%~dp0`"`r`nfor %%f in (`"*.exe`") do start `"`" `"%%f`"`r`n"
[System.IO.File]::WriteAllText($bat, $batBody, [System.Text.Encoding]::ASCII)

# 6) 构建信息与归档
$buildInfo = "引擎: boss-zhipin-scraper v2.2.0 (commit 16cc992)`n构建时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm')`nPython: $pyver embeddable"
Set-Content -Path (Join-Path $stage "BUILD-INFO.txt") -Value $buildInfo -Encoding UTF8
Compress-Archive $stage (Join-Path $dist "BOSS职位采集器.zip") -Force
Write-Host "构建完成: $dist"
