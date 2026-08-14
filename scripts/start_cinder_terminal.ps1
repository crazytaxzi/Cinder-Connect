$ErrorActionPreference = 'Stop'

# ================= USER CONFIG =================
$RunAsAdministrator = $true
# ===============================================

$RepoRoot = Split-Path -Parent $PSScriptRoot
$TerminalScript = Join-Path $RepoRoot 'terminal\cinder_terminal.py'

if (-not (Test-Path -LiteralPath $TerminalScript)) {
    throw "Terminal script not found: $TerminalScript"
}

$Python = $null
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    $Python = (& py.exe -3.12 -c 'import sys; print(sys.executable)').Trim()
}
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = (Get-Command python.exe -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python executable not found: $Python"
}
$start = @{
    FilePath = $Python
    ArgumentList = @('-u', ('"{0}"' -f $TerminalScript))
    WorkingDirectory = $RepoRoot
    PassThru = $true
}
if ($RunAsAdministrator) {
    $start.Verb = 'RunAs'
}

Write-Host 'Starting Cinder terminal...'
if ($RunAsAdministrator) {
    Write-Host 'Approve the UAC prompt for an elevated terminal.'
}
$process = Start-Process @start
Start-Sleep -Milliseconds 250
$process.Refresh()
if ($process.HasExited) {
    throw 'Cinder terminal exited before it could be bound.'
}

try { $actualPath = $process.Path } catch { $actualPath = $Python }
if ([string]::IsNullOrWhiteSpace($actualPath)) { $actualPath = $Python }
$binding = [ordered]@{
    version = 2
    pid = [int]$process.Id
    exe_path = [System.IO.Path]::GetFullPath($actualPath)
    start_filetime_utc = [int64]$process.StartTime.ToFileTimeUtc()
    binding_id = [guid]::NewGuid().ToString()
    bound_utc = [DateTime]::UtcNow.ToString('o')
    elevated_requested = [bool]$RunAsAdministrator
    role = 'cinder-terminal'
}

$bindingDir = Join-Path $env:LOCALAPPDATA 'CinderConnect'
$bindingPath = Join-Path $bindingDir 'binding.json'
$tempPath = Join-Path $bindingDir 'binding.json.tmp'
New-Item -ItemType Directory -Force -Path $bindingDir | Out-Null
$json = $binding | ConvertTo-Json -Depth 4
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($tempPath, $json, $utf8NoBom)
Move-Item -LiteralPath $tempPath -Destination $bindingPath -Force

Write-Host "Bound terminal PID: $($binding.pid)"
Write-Host "Executable:         $($binding.exe_path)"
Write-Host "Binding:            $($binding.binding_id)"
