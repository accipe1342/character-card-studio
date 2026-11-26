<#
    Builds the portable Character Card Studio: a folder you unzip and double-click, with no Python,
    no Node and no installer on the machine that runs it.

    Nothing here is compiled or packed. python.exe comes from python.org signed by the Python
    Software Foundation, the dependencies are ordinary .py files, and the launcher is a .bat. That is
    deliberate: a PyInstaller or Nuitka single file is an unsigned packed executable, which is the
    shape Windows Defender's heuristics flag and SmartScreen blocks.

    Run from the repository root:   powershell -ExecutionPolicy Bypass -File tools\build_portable.ps1
#>
param(
    # Must be a version python.org publishes an "embeddable package" for (3.8+).
    [string]$PythonVersion = "3.12.8",
    [string]$OutDir        = "dist_portable",
    [switch]$SkipFrontend                      # reuse an existing frontend\dist
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"    # or Invoke-WebRequest crawls
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$short  = ($PythonVersion -split '\.')[0..1] -join ''        # 3.12.8 -> 312
$name   = "Character Card Studio"
$stage  = Join-Path $OutDir $name
$cache  = Join-Path $PSScriptRoot ".cache"

function Step($m) { Write-Host "`n[.] $m" -ForegroundColor Cyan }

# -- 1. the frontend -----------------------------------------------------------------------------
if (-not $SkipFrontend) {
    Step "Building the frontend"
    Push-Location frontend
    if (-not (Test-Path node_modules)) { npm install --silent }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "The frontend build failed." }
    Pop-Location
}
if (-not (Test-Path "frontend\dist\index.html")) { throw "frontend\dist is missing - run without -SkipFrontend." }

# -- 2. embeddable Python ------------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$zip = Join-Path $cache "python-$PythonVersion-embed-amd64.zip"
if (-not (Test-Path $zip)) {
    Step "Downloading embeddable Python $PythonVersion"
    $url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip
}

# -- 3. assemble ---------------------------------------------------------------------------------
Step "Assembling $stage"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

Expand-Archive -Path $zip -DestinationPath (Join-Path $stage "python") -Force

# The ._pth file is what the embeddable uses instead of PYTHONPATH, which it ignores. Paths are
# relative to python.exe, so lib\ and backend\ are one level up.
$pth = Join-Path $stage "python\python$short._pth"
@"
python$short.zip
.
..\lib
..\backend
import site
"@ | Set-Content -Path $pth -Encoding ASCII

Step "Vendoring the dependencies"
# --python-version pins the wheels to the embeddable's interpreter rather than whichever Python is
# on PATH here, so the build is the same whoever runs it. All five dependencies are pure Python.
python -m pip install --target (Join-Path $stage "lib") `
    --python-version $(($PythonVersion -split '\.')[0..1] -join '.') `
    --platform win_amd64 --only-binary=:all: --no-compile -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Vendoring the dependencies failed." }

Copy-Item backend         (Join-Path $stage "backend") -Recurse
Copy-Item frontend\dist   (Join-Path $stage "web")     -Recurse
Copy-Item .env.example    (Join-Path $stage ".env.example")
Copy-Item "$PSScriptRoot\portable\Start Character Card Studio.bat" $stage
Copy-Item "$PSScriptRoot\portable\READ ME FIRST.txt"               $stage
New-Item -ItemType Directory -Force -Path (Join-Path $stage "data") | Out-Null

# Nothing here needs the test suite or bytecode caches along for the ride. -Include is deliberately
# not used: with -Recurse it matches nothing unless the path ends in \*, which fails silently.
if (Test-Path (Join-Path $stage "backend\tests")) { Remove-Item (Join-Path $stage "backend\tests") -Recurse -Force }
Get-ChildItem $stage -Recurse -Directory | Where-Object { $_.Name -eq "__pycache__" } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# -- 4. zip --------------------------------------------------------------------------------------
Step "Zipping"
$ver = (Get-Content frontend\package.json -Raw | ConvertFrom-Json).version
$out = Join-Path $OutDir "CharacterCardStudio-$ver-portable-win64.zip"
if (Test-Path $out) { Remove-Item $out -Force }
Compress-Archive -Path $stage -DestinationPath $out -CompressionLevel Optimal

$mb = [math]::Round((Get-Item $out).Length / 1MB, 1)
$folderMb = [math]::Round(((Get-ChildItem $stage -Recurse -File | Measure-Object Length -Sum).Sum) / 1MB, 1)
Write-Host "`n[OK] $out  ($mb MB zipped, $folderMb MB unzipped)" -ForegroundColor Green
Write-Host "     Test it by unzipping somewhere else and double-clicking the .bat." -ForegroundColor DarkGray
