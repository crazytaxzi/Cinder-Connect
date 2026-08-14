$ErrorActionPreference = 'Stop'

# ================= USER CONFIG =================
$TargetExe = 'C:\Windows\System32\notepad.exe'
$TargetArgs = @()
$WorkingDirectory = ''
# ===============================================

if (-not (Test-Path -LiteralPath $TargetExe)) {
    throw "Target executable not found: $TargetExe"
}

$start = @{
    FilePath = $TargetExe
    PassThru = $true
}
if ($TargetArgs.Count -gt 0) {
    $start.ArgumentList = $TargetArgs
}
if (-not [string]::IsNullOrWhiteSpace($WorkingDirectory)) {
    $start.WorkingDirectory = $WorkingDirectory
}
$process = Start-Process @start
Start-Sleep -Milliseconds 150
$process.Refresh()

if ($process.HasExited) {
    throw 'Target exited before its process identity could be bound.'
}

$actualPath = $process.Path
if ([string]::IsNullOrWhiteSpace($actualPath)) {
    $actualPath = (Resolve-Path -LiteralPath $TargetExe).Path
}

$binding = [ordered]@{
    version = 1
    pid = [int]$process.Id
    exe_path = [System.IO.Path]::GetFullPath($actualPath)
    start_filetime_utc = [int64]$process.StartTime.ToFileTimeUtc()
    binding_id = [guid]::NewGuid().ToString()
    bound_utc = [DateTime]::UtcNow.ToString('o')
}
$bindingDir = Join-Path $env:LOCALAPPDATA 'CinderConnect'
$bindingPath = Join-Path $bindingDir 'binding.json'
$tempPath = Join-Path $bindingDir 'binding.json.tmp'
New-Item -ItemType Directory -Force -Path $bindingDir | Out-Null

$json = $binding | ConvertTo-Json -Depth 4
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($tempPath, $json, $utf8NoBom)
Move-Item -LiteralPath $tempPath -Destination $bindingPath -Force

Write-Host ''
Write-Host 'Cinder Connect binding created.'
Write-Host "PID:        $($binding.pid)"
Write-Host "Executable: $($binding.exe_path)"
Write-Host "Binding:    $($binding.binding_id)"
Write-Host "File:       $bindingPath"
