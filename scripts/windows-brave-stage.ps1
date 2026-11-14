# Stage-only browser smoke fixture. This endpoint cannot create auto-send grants.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$ConversationId,
    [Parameter(Mandatory=$true)][ValidateRange(1,2147483647)][int]$TabId,
    [string]$Text = "Brave Bridge Test`nZweite Zeile`nKein automatischer Versand.",
    [string]$Token = 'mock-test-token'
)
$ErrorActionPreference = 'Stop'
$body = @{
    id = "stage-$([guid]::NewGuid().ToString('N'))"
    conversation_id = $ConversationId
    tab_id = $TabId
    text = $Text
} | ConvertTo-Json -Compress
$response = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/bridge/v1/mock/enqueue-stage' -Method Post -Headers @{
    Authorization = "Bearer $Token"
} -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
if ($response.status -ne 'queued') { throw "Unexpected response: $($response | ConvertTo-Json -Compress)" }
Write-Host "STAGE_ONLY queued: $($response.id)"
Write-Host 'Open the side panel and click Jetzt synchronisieren. Nothing will be submitted automatically.'
