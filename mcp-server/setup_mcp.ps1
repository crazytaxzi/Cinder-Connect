$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $RepoRoot '.venv-mcp'
$Python = Join-Path $Venv 'Scripts\python.exe'
$Requirements = Join-Path $PSScriptRoot 'requirements.txt'

if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host 'Creating Cinder Connect MCP virtual environment...'
    py -3.12 -m venv $Venv
}

Write-Host 'Installing the official MCP Python SDK...'
& $Python -m pip install -r $Requirements

Write-Host ''
Write-Host 'Cinder Connect MCP setup complete.'
Write-Host "Python:   $Python"
Write-Host 'Endpoint: http://127.0.0.1:8765/mcp'
