$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv-mcp\Scripts\python.exe'
$Server = Join-Path $PSScriptRoot 'server.py'

if (-not (Test-Path -LiteralPath $Python)) {
    throw 'MCP environment missing. Run mcp-server\setup_mcp.ps1 first.'
}

Write-Host 'Starting Cinder Connect MCP...'
Write-Host 'Endpoint: http://127.0.0.1:8765/mcp'
Write-Host ''

& $Python $Server
