# OFFLINE fixture executor. No SSH, no subprocess commands, no browser auto-send.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$')]
    [string]$RequestId,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')]
    [string]$HostId = 'lab-nas'
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$db = Join-Path $env:LOCALAPPDATA 'gpt-local-llm-worker\mock-review.sqlite3'
if (-not (Test-Path -LiteralPath $db)) { throw "Mock approval database not found: $db" }
$python = '.\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Mock Python environment not found. Start the mock server first.' }
Write-Host 'OFFLINE SSH fixture simulation only; no SSH connection or ChatGPT send.'
& $python -m worker.mock_cli --db $db --request-id $RequestId --host-alias $HostId --confirm-mock
if ($LASTEXITCODE -ne 0) { throw "Mock simulation failed with exit code $LASTEXITCODE" }
