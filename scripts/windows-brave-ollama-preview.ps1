# Start Ollama analysis preview on loopback only. No SSH execution.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^[a-p]{32}$')]
    [string]$ExtensionId
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$root = Join-Path $env:LOCALAPPDATA 'gpt-local-llm-worker'
$config = Join-Path $root 'ollama-profiles.json'
$targets = Join-Path $root 'brave-preview-targets.json'
$db = Join-Path $root 'brave-preview.sqlite3'
$origin = "chrome-extension://$ExtensionId"

if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
    throw "Ollama-Profil fehlt: $config"
}
$profile = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
if (-not $profile.active -or -not $profile.profiles) {
    throw 'Ollama-Profilkonfiguration unvollständig'
}

$listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    throw 'Port 8765 bereits belegt. Bestehenden Worker bewusst beenden; nichts wird automatisch gestoppt.'
}

# Create the disposable preview allowlist once, never overwrite operator files.
if (-not (Test-Path -LiteralPath $targets)) {
    $key = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJJ6ml7zbtSC8jwBsz/Pg/3zwvWrLUSK0coMUxgbMKBq'
    $entries = @('nas','backup-nas','vserver') | ForEach-Object {
        @{
            host_id = $_
            hostname = "$_.example.invalid"
            port = 22
            username = 'preview'
            host_public_key = $key
        }
    }
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($targets, ($entries | ConvertTo-Json -Depth 5), $utf8)
}

# Generate a fresh authentication secret. Only process memory + extension storage.
$tokenBytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($tokenBytes) } finally { $rng.Dispose() }
$env:BRIDGE_LIVE_TOKEN = [BitConverter]::ToString($tokenBytes).Replace('-','').ToLowerInvariant()

Write-Host ''
Write-Host '=== BRAVE OLLAMA LIVE-VORSCHAU ==='
Write-Host "Extension-Origin: $origin"
Write-Host "Test-Allowlist: $targets (nur *.example.invalid)"
Write-Host "Datenbank: $db"
Write-Host "Profil: $($profile.active)"
Write-Host 'SSH: DEAKTIVIERT | Freigabe: DEAKTIVIERT | Auto-Send: DEAKTIVIERT'
Write-Host 'TOKEN FUER BRAVE-SEITENPANEL (nicht in Chats posten):'
Write-Host $env:BRIDGE_LIVE_TOKEN
Write-Host 'Mit Strg+C stoppen.'
Push-Location $repo
try {
    py -m worker.live_capture_api --db $db --targets $targets --extension-origin $origin --ollama-profiles $config --port 8765
} finally {
    Pop-Location
    Remove-Item Env:BRIDGE_LIVE_TOKEN -ErrorAction SilentlyContinue
}
