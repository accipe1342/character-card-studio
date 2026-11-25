param([string]$Url = "http://localhost:5173")

# Opens the app in its own window (Edge or Chrome app mode) once the backend answers.
# start.bat runs this in the background. A normal browser tab is the fallback.

# 1. Wait for Flask, so the window does not open on "can't reach this page".
for ($i = 0; $i -lt 240; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:5000/api/backups" | Out-Null
        break
    } catch {
        Start-Sleep -Milliseconds 500
    }
}

# 2. OPEN_AS in .env decides: app (the default) or tab.
$mode = "app"
$envFile = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
if (Test-Path -LiteralPath $envFile) {
    $line = Get-Content -LiteralPath $envFile | Where-Object { $_ -match "^\s*OPEN_AS\s*=" } | Select-Object -First 1
    if ($line) { $mode = ($line -replace "^\s*OPEN_AS\s*=\s*", "").Trim().ToLower() }
}

# 3. Find a browser. Only a real file counts: handing Start-Process a folder opens Explorer.
$exe = $null
if ($mode -ne "tab") {
    $candidates = New-Object System.Collections.Generic.List[string]
    foreach ($name in @("msedge", "chrome")) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found -and $found.Source) { $candidates.Add($found.Source) }
    }
    foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
        if ([string]::IsNullOrWhiteSpace($root)) { continue }
        $candidates.Add((Join-Path $root "Microsoft\Edge\Application\msedge.exe"))
        $candidates.Add((Join-Path $root "Google\Chrome\Application\chrome.exe"))
    }
    foreach ($c in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($c) -and (Test-Path -LiteralPath $c -PathType Leaf)) { $exe = $c; break }
    }
}

# 4. Open it.
if ($exe) {
    Start-Process -FilePath $exe -ArgumentList "--app=$Url", "--window-size=1400,900"
} else {
    Start-Process $Url
}
