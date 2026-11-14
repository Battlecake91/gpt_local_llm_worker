# Mock-only fixture: adds an immutable, read-only SSH proposal to the review UI.
# This script NEVER connects to SSH, runs a command or grants auto-send.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$ConversationId,
    [Parameter(Mandatory=$true)][ValidateRange(1,2147483647)][int]$TabId,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')][string]$HostId = 'lab-nas',
    [string]$Token = 'mock-test-token'
)
$ErrorActionPreference = 'Stop'
$requestId = "review-$([guid]::NewGuid().ToString('N'))"
$proposal = @{
    schema_version = 1
    kind = 'ssh_batch'
    request_id = $requestId
    target = $HostId
    working_directory = '/tmp'
    description = 'Mock-Freigabeprüfung: keine Ausführung. Nur read-only Befehle.'
    commands = @(
        @{ id = 'host'; command = 'uname -a'; timeout_seconds = 15 }
        @{ id = 'user'; command = 'id'; timeout_seconds = 15 }
    )
}
$text = ConvertTo-Json -InputObject $proposal -Depth 8 -Compress
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $messageId = [Convert]::ToHexString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text))).ToLowerInvariant()
} finally {
    $sha.Dispose()
}
$body = @{
    schema_version = 1
    message_id = $messageId
    conversation_id = $ConversationId
    tab_id = $TabId
    text = $text
    observed_at = [DateTimeOffset]::UtcNow.ToString('o')
} | ConvertTo-Json -Depth 6 -Compress
$response = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/bridge/v1/captures' -Method Post -Headers @{
    Authorization = "Bearer $Token"
} -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
if ($response.status -ne 'accepted') { throw "Capture not accepted: $($response | ConvertTo-Json -Compress)" }
Write-Host "Mock SSH proposal submitted: $requestId"
Write-Host 'Brave side panel -> SSH-Auftragsfreigabe -> Aufträge prüfen.'
Write-Host 'Confirming records a mock decision only. It executes no SSH and sends no ChatGPT message.'
