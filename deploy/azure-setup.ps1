# Creates (or repairs) the whole CareerPilot AI backend on an Azure account with ONE command.
#
# Use it when:
#   - moving the backend to another Azure account (e.g. a teammate's Azure for Students), or
#   - the old one was deleted / disabled and you start again.
# Running it on an account where everything already exists is safe: it only fixes what is missing.
#
# What it does:
#   1. creates the resource group, the Container Apps environment and the app (2 vCPU, 4 GB,
#      sleeps when unused = scale to zero), using the public image from GitHub Container Registry
#   2. copies the keys from backend/.env and backend/firebase-key.json into Azure as SECRETS
#      (never printed, never sent anywhere else)
#   3. waits until the server answers /health with Firestore connected
#   4. lets GitHub Actions deploy to this account without a password (OpenID Connect)
#   5. prints the 3 values to paste into GitHub secrets and the new server address
#
# Run it from the repo folder in PowerShell:
#   powershell -ExecutionPolicy Bypass -File deploy\azure-setup.ps1
# Other region (if Azure says "RequestDisallowedByPolicy"):
#   powershell -ExecutionPolicy Bypass -File deploy\azure-setup.ps1 -Location centralindia
param(
    [string]$ResourceGroup = "careerpilot-rg",
    [string]$AppName = "careerpilot-api",
    [string]$EnvName = "careerpilot-env",
    [string]$Location = "uaenorth",
    [string]$Image = "ghcr.io/aqeellaghari/careerpilot-backend:latest",
    [string]$Repo = "AqeelLaghari/careerpilot-ai",
    [string]$DeployAppName = "careerpilot-github-deploy",
    [switch]$SkipGitHub,           # only create the server (no GitHub deploy access)
    [switch]$Yes                   # do not ask "this subscription?"
)

$ErrorActionPreference = "Stop"
$backend = Join-Path (Split-Path $PSScriptRoot -Parent) "backend"

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

# --- Azure CLI ------------------------------------------------------------------------------
$azCmd = Get-Command az -ErrorAction SilentlyContinue
$az = if ($azCmd) { $azCmd.Source } else { "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" }
if (-not (Test-Path $az)) {
    Fail "Azure CLI is not installed. Run:  winget install -e --id Microsoft.AzureCLI   then close and reopen PowerShell."
}

# Runs az, returns its text output, stops with a clear message if it fails.
function Az {
    $ErrorActionPreference = "Continue"     # az prints warnings on stderr; only the exit code counts
    $out = & $az @args 2>&1
    if ($LASTEXITCODE -ne 0) {
        $msg = ($out | Out-String).Trim()
        if ($msg -match "RequestDisallowedByPolicy") {
            Fail "This Azure account does not allow region '$Location'. Run the script again with -Location centralindia (or polandcentral, southeastasia, austriaeast)."
        }
        Fail "az $($args[0]) $($args[1]) failed:`n$msg"
    }
    return ($out | Where-Object { $_ -is [string] } | Out-String).Trim()
}
function AzOk { $ErrorActionPreference = "Continue"; & $az @args 2>&1 | Out-Null; return ($LASTEXITCODE -eq 0) }

# --- Keys from the backend folder (values are never printed) -------------------------------
Step "Reading keys from backend\.env and backend\firebase-key.json"
$envFile = Join-Path $backend ".env"
$keyFile = Join-Path $backend "firebase-key.json"
if (-not (Test-Path $envFile)) { Fail "backend\.env not found. Copy it from the old laptop (it is never in GitHub)." }
if (-not (Test-Path $keyFile)) { Fail "backend\firebase-key.json not found. Copy it from the old laptop (it is never in GitHub)." }
$vars = @{}
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') { $vars[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'") }
}
if (-not $vars["GEMINI_API_KEY"]) { Fail "GEMINI_API_KEY is missing in backend\.env" }
try { $firebaseJson = (Get-Content $keyFile -Raw | ConvertFrom-Json | ConvertTo-Json -Compress -Depth 5) }
catch { Fail "backend\firebase-key.json is not valid JSON" }
# secret name in Azure -> (environment variable in the app, value)
$secrets = [ordered]@{ "gemini-key" = @("GEMINI_API_KEY", $vars["GEMINI_API_KEY"]); "firebase-key-json" = @("FIREBASE_KEY_JSON", $firebaseJson) }
if ($vars["YOUTUBE_API_KEY"]) { $secrets["youtube-key"] = @("YOUTUBE_API_KEY", $vars["YOUTUBE_API_KEY"]) }
if ($vars["ADMIN_UIDS"]) { $secrets["admin-uids"] = @("ADMIN_UIDS", $vars["ADMIN_UIDS"]) }
if ($vars["HIMALAYAS_API_KEY"]) { $secrets["himalayas-key"] = @("HIMALAYAS_API_KEY", $vars["HIMALAYAS_API_KEY"]) }
Write-Host "Found: $($secrets.Keys -join ', ')"

# --- Login ----------------------------------------------------------------------------------
Step "Checking the Azure login"
if (-not (AzOk account show)) { & $az login | Out-Null }
$account = Az account show --query "{name:name, user:user.name, sub:id, tenant:tenantId}" -o json | ConvertFrom-Json
Write-Host "Subscription: $($account.name)   Signed in as: $($account.user)"
$answer = if ($Yes) { "y" } else { Read-Host "Create the CareerPilot backend in THIS subscription? (y/n)" }
if ($answer -ne "y") { Fail "Cancelled. To use another account run:  az login   (or  az account set -s <subscription name>)" }

Step "Preparing Azure (first time on an account takes 1-3 minutes)"
AzOk extension add --name containerapp --upgrade --yes | Out-Null
foreach ($p in "Microsoft.App", "Microsoft.OperationalInsights") { Az provider register -n $p --wait -o none | Out-Null }

# --- Server ---------------------------------------------------------------------------------
Step "Resource group '$ResourceGroup' in $Location"
if (AzOk group show -n $ResourceGroup) { Write-Host "already exists" }
else { Az group create -n $ResourceGroup -l $Location -o none | Out-Null; Write-Host "created" }

Step "Container Apps environment '$EnvName' (2-5 minutes the first time)"
if (AzOk containerapp env show -n $EnvName -g $ResourceGroup) { Write-Host "already exists" }
else { Az containerapp env create -n $EnvName -g $ResourceGroup -l $Location --logs-destination none -o none | Out-Null; Write-Host "created" }

Step "Container app '$AppName'"
if (AzOk containerapp show -n $AppName -g $ResourceGroup) { Write-Host "already exists" }
else {
    Az containerapp create -n $AppName -g $ResourceGroup --environment $EnvName --image $Image `
        --cpu 2 --memory 4Gi --min-replicas 0 --max-replicas 1 --ingress external --target-port 7860 -o none | Out-Null
    Write-Host "created"
}

Step "Saving the keys as Azure secrets"
$tmp = Join-Path $env:TEMP ("cp_secret_" + [guid]::NewGuid().ToString("N") + ".txt")
try {
    foreach ($name in $secrets.Keys) {
        # written to a temporary file and passed as @file, so no value appears on a command line
        [IO.File]::WriteAllText($tmp, "$name=$($secrets[$name][1])", (New-Object Text.UTF8Encoding $false))
        Az containerapp secret set -n $AppName -g $ResourceGroup --secrets "@$tmp" -o none | Out-Null
        Write-Host "  $name saved"
    }
}
finally { Remove-Item $tmp -ErrorAction SilentlyContinue }

Step "Connecting the secrets to the app (the app restarts)"
$envArgs = @($secrets.Keys | ForEach-Object { "$($secrets[$_][0])=secretref:$_" }) + "WHISPER_THREADS=2"
Az containerapp update -n $AppName -g $ResourceGroup --image $Image --set-env-vars @envArgs -o none | Out-Null
Az containerapp ingress update -n $AppName -g $ResourceGroup --target-port 7860 -o none | Out-Null
$fqdn = Az containerapp show -n $AppName -g $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv
$url = "https://$fqdn"
Write-Host "Server address: $url"

Step "Waiting for the server to answer (first start downloads the image: up to 10 minutes)"
$healthy = $false
for ($i = 1; $i -le 60; $i++) {
    try {
        $h = Invoke-RestMethod "$url/health" -TimeoutSec 30
        if ($h.firestore_connected -and $h.gemini_key_set) { $healthy = $true; break }
        Write-Host "  answered, but firestore_connected=$($h.firestore_connected) gemini_key_set=$($h.gemini_key_set)"
    }
    catch { Write-Host "  not ready yet ($i/60)" }
    Start-Sleep -Seconds 10
}
if (-not $healthy) { Fail "The server did not become healthy. Open $url/health in a browser and see deploy\HOSTING.md > Problems." }
Write-Host "Server is up: Firestore connected, Gemini key set" -ForegroundColor Green

if ($SkipGitHub) { Write-Host ""; Write-Host "Done (GitHub part skipped). Server: $url"; exit 0 }

# --- GitHub Actions deploy access (OpenID Connect, no password) -----------------------------
Step "Giving GitHub Actions permission to deploy to this resource group"
$appId = Az ad app list --display-name $DeployAppName --query "[0].appId" -o tsv
if (-not $appId) { $appId = Az ad app create --display-name $DeployAppName --query appId -o tsv; Write-Host "app registration created" }
else { Write-Host "app registration already exists" }
if (-not (AzOk ad sp show --id $appId)) { Az ad sp create --id $appId -o none | Out-Null }

$gh = Invoke-RestMethod "https://api.github.com/repos/$Repo"
$owner = $Repo.Split("/")[0]; $name = $Repo.Split("/")[1]
# GitHub sends either the name style or the ID style subject, so trust both
$subjects = [ordered]@{
    "github-main"               = "repo:${Repo}:ref:refs/heads/main"
    "github-production-env"     = "repo:${Repo}:environment:production"
    "github-main-ids"           = "repo:${owner}@$($gh.owner.id)/${name}@$($gh.id):ref:refs/heads/main"
    "github-production-env-ids" = "repo:${owner}@$($gh.owner.id)/${name}@$($gh.id):environment:production"
}
$existing = Az ad app federated-credential list --id $appId --query "[].subject" -o tsv
foreach ($k in $subjects.Keys) {
    if ($existing -match [regex]::Escape($subjects[$k])) { continue }
    $fc = Join-Path $env:TEMP "cp_fc_$k.json"
    $json = @{ name = $k; issuer = "https://token.actions.githubusercontent.com"; subject = $subjects[$k]; audiences = @("api://AzureADTokenExchange") } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($fc, $json, (New-Object Text.UTF8Encoding $false))
    Az ad app federated-credential create --id $appId --parameters "@$fc" -o none | Out-Null
    Remove-Item $fc
    Write-Host "  trusted: $($subjects[$k])"
}
$rgId = Az group show -n $ResourceGroup --query id -o tsv
$hasRole = Az role assignment list --assignee $appId --scope $rgId --query "[?roleDefinitionName=='Contributor'] | length(@)" -o tsv
if ($hasRole -eq "0") {
    # a brand-new app registration can take a minute to become visible
    for ($i = 1; $i -le 6; $i++) {
        if (AzOk role assignment create --assignee $appId --role Contributor --scope $rgId) { break }
        Start-Sleep -Seconds 15
    }
}
Write-Host "GitHub can now deploy to '$ResourceGroup' (and nothing else)"

Write-Host ""
Write-Host "=================================== DONE ===================================" -ForegroundColor Green
Write-Host "1) GitHub > repo > Settings > Secrets and variables > Actions > update these 3 secrets:"
Write-Host "     AZURE_CLIENT_ID        = $appId"
Write-Host "     AZURE_TENANT_ID        = $($account.tenant)"
Write-Host "     AZURE_SUBSCRIPTION_ID  = $($account.sub)"
Write-Host "2) In GitHub, edit frontend/web/config.json so it says:"
Write-Host "     {""api_url"": ""$url""}"
Write-Host "   (commit it on a new branch, open the pull request, merge it when green)"
Write-Host "3) Check: $url/health"
Write-Host "Full guide: deploy\HOSTING.md"
