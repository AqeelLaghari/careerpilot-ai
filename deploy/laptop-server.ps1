# Backup plan: runs the backend on THIS laptop and makes it reachable from the internet through a free
# Cloudflare quick tunnel (no account, no card). Use it when Azure is not available, or on defense day.
#
#   powershell -ExecutionPolicy Bypass -File deploy\laptop-server.ps1
#
# It opens two windows (backend + tunnel), waits until the public address answers /health, then points
# the website and the app to it (config.json on a new branch + pull request link).
# Keep the laptop ON, plugged in and online, with sleep turned off. Closing either window stops the server.
# The tunnel address changes every time, so run this on the day you need it.
param(
    [int]$Port = 7860,
    [switch]$KeepUrl               # start the server but do not switch the website/app to it
)

$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $repo "backend"
function Fail($text) { Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

foreach ($f in ".env", "firebase-key.json", ".venv\Scripts\Activate.ps1") {
    if (-not (Test-Path (Join-Path $backend $f))) { Fail "backend\$f is missing (see deploy\HOSTING.md, section 1)." }
}

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "Installing cloudflared (one time)..."
    winget install -e --id Cloudflare.cloudflared --accept-source-agreements --accept-package-agreements | Out-Null
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) { Fail "cloudflared did not install. Close PowerShell, open it again and re-run." }
}

Write-Host "==> Starting the backend in a new window (first start loads the AI models: about 1 minute)" -ForegroundColor Cyan
$cmd = "cd '$backend'; .\.venv\Scripts\Activate.ps1; `$env:APP_ENV='production'; uvicorn app.main:app --host 127.0.0.1 --port $Port"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd -WindowStyle Normal
$up = $false
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Seconds 5
    try { $h = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 5; $up = $true; break } catch { Write-Host "  starting... ($i)" }
}
if (-not $up) { Fail "The backend did not start. Look at the backend window for the error." }
Write-Host "Backend is up: firestore=$($h.firestore_connected) gemini=$($h.gemini_key_set)" -ForegroundColor Green

Write-Host "==> Opening the Cloudflare tunnel in a new window" -ForegroundColor Cyan
$log = Join-Path $env:TEMP "careerpilot-tunnel.log"
Remove-Item $log -ErrorAction SilentlyContinue
$tunnel = "cloudflared tunnel --url http://127.0.0.1:$Port 2>&1 | Tee-Object -FilePath '$log'"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $tunnel -WindowStyle Normal
$url = $null
for ($i = 1; $i -le 30 -and -not $url; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value }
    }
}
if (-not $url) { Fail "No tunnel address appeared. Look at the tunnel window for the error." }
Write-Host "Public address: $url"
for ($i = 1; $i -le 30; $i++) {
    try { Invoke-RestMethod "$url/health" -TimeoutSec 10 | Out-Null; Write-Host "The public address works." -ForegroundColor Green; break }
    catch { Start-Sleep -Seconds 3 }
}

if ($KeepUrl) { Write-Host "Server running at $url (website not switched: -KeepUrl)"; exit 0 }
& (Join-Path $PSScriptRoot "set-backend-url.ps1") -Url $url
Write-Host ""
Write-Host "To go back to Azure later: powershell -ExecutionPolicy Bypass -File deploy\set-backend-url.ps1 <Azure address>"
