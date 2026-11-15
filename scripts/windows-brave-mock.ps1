# Launch an isolated loopback mock for Windows Brave. No SSH and no automatic sending.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^[a-p]{32}$')]
    [string]$ExtensionId,
    [string]$Token = 'mock-test-token',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')]
    [string[]]$ReviewHosts = @()
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    & py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3 environment creation failed' }
}
& .\.venv\Scripts\python.exe -m pip install fastapi uvicorn httpx
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies failed to install' }
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_mock.py' -v
if ($LASTEXITCODE -ne 0) { throw 'Mock backend tests failed; refusing to launch' }

$env:BRIDGE_MOCK_TOKEN = $Token
$env:BRIDGE_EXTENSION_ORIGIN = "chrome-extension://$ExtensionId"
$env:BRIDGE_MOCK_FIXTURES = '1'

if ($ReviewHosts.Count -gt 0) {
    $env:BRIDGE_ALLOWED_HOSTS = ($ReviewHosts -join ',')
    $dir = Join-Path $env:LOCALAPPDATA 'gpt-local-llm-worker'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $env:BRIDGE_APPROVAL_DB = Join-Path $dir 'mock-review.sqlite3'
    Write-Host "Mock SSH review enabled for aliases: $env:BRIDGE_ALLOWED_HOSTS"
    Write-Host 'Approvals are mock records only: no SSH execution or auto-send.'
} else {
    Remove-Item Env:BRIDGE_ALLOWED_HOSTS -ErrorAction SilentlyContinue
    Remove-Item Env:BRIDGE_APPROVAL_DB -ErrorAction SilentlyContinue
}

Write-Host 'Starting isolated mock on http://127.0.0.1:8765'
Write-Host 'Do not close this terminal until testing is finished. Press Ctrl+C to stop.'
& .\.venv\Scripts\python.exe -m uvicorn mock.backend:app --host 127.0.0.1 --port 8765
if ($LASTEXITCODE -ne 0) { throw "Mock backend failed with exit code $LASTEXITCODE" }
