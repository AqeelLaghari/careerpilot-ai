# Points the website and the Android app to a (new) backend address.
#
# The address lives in ONE place: frontend/web/config.json (the website and the APK read it at start-up,
# the GitHub workflows read it at build time). This script changes that file, checks the new server
# answers, and pushes the change on a new branch. You then open the pull request link it prints and merge.
#
#   powershell -ExecutionPolicy Bypass -File deploy\set-backend-url.ps1 https://new-server-address
#
# The other scripts (azure-setup.ps1, laptop-server.ps1) call this for you.
param(
    [Parameter(Mandatory = $true)][string]$Url,
    [switch]$NoGit                 # only change the file, no branch/commit/push
)

$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$config = Join-Path $repo "frontend\web\config.json"
$Url = $Url.Trim().TrimEnd("/")
if ($Url -notmatch '^https://[A-Za-z0-9.-]+(:\d+)?$') { Write-Host "STOPPED: the address must look like https://something.example.com (no path)" -ForegroundColor Red; exit 1 }

try { $h = Invoke-RestMethod "$Url/health" -TimeoutSec 60; Write-Host "New server answers: status=$($h.status) firestore=$($h.firestore_connected)" -ForegroundColor Green }
catch { Write-Host "Warning: $Url/health did not answer yet (it may still be starting). Continuing." -ForegroundColor Yellow }

$old = (Get-Content $config -Raw | ConvertFrom-Json).api_url
if ($old -eq $Url) { Write-Host "config.json already points to $Url. Nothing to change."; exit 0 }
[IO.File]::WriteAllText($config, "{`n  `"api_url`": `"$Url`"`n}`n", (New-Object Text.UTF8Encoding $false))
Write-Host "config.json: $old  ->  $Url"
if ($NoGit) { exit 0 }

$ErrorActionPreference = "Continue"      # git prints progress on stderr
Push-Location $repo
try {
    $others = git status --porcelain | Where-Object { $_ -notmatch 'frontend/web/config.json' }
    if ($others) { Write-Host "Other files are changed too, so I did not commit. Commit frontend/web/config.json yourself." -ForegroundColor Yellow; exit 0 }
    $branch = "ops/backend-url-" + (Get-Date -Format "yyyyMMdd-HHmm")
    git switch -c $branch 2>&1 | Out-Null
    git add frontend/web/config.json
    git commit -q -m "Backend address -> $Url" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "Commit failed (see the messages above)." -ForegroundColor Red; exit 1 }
    git push -u origin $branch 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "Push failed: check the internet / GitHub login, then run:  git push -u origin $branch" -ForegroundColor Red; exit 1 }
    $remote = (git remote get-url origin) -replace '\.git$', '' -replace '^git@github.com:', 'https://github.com/'
    Write-Host ""
    Write-Host "LAST STEP: open this link > Create pull request > wait for green > Squash and merge > Delete branch:" -ForegroundColor Green
    Write-Host "  $remote/pull/new/$branch"
    Write-Host "About 5 minutes after merging, the website (and the app on its next start) use the new server."
    git switch main 2>&1 | Out-Null
}
finally { Pop-Location }
