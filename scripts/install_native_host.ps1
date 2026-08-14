$ErrorActionPreference = 'Stop'

$HostName = 'cinder_connect'
$ExtensionId = 'cinder-connect@crazytaxzi.local'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$SourceHost = Join-Path $RepoRoot 'native-host\native_host.ps1'
$InstallRoot = Join-Path $env:LOCALAPPDATA 'CinderConnect\native-host'
$InstalledHost = Join-Path $InstallRoot 'native_host.ps1'
$LauncherPath = Join-Path $InstallRoot 'cinder_connect_host.bat'
$ManifestPath = Join-Path $InstallRoot 'cinder_connect.json'

if (-not (Test-Path -LiteralPath $SourceHost)) {
    throw "Native host source not found: $SourceHost"
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Copy-Item -LiteralPath $SourceHost -Destination $InstalledHost -Force
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$launcher = @"
@echo off
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$InstalledHost" %*
"@
[System.IO.File]::WriteAllText($LauncherPath, $launcher, $utf8NoBom)

$manifest = [ordered]@{
    name = $HostName
    description = 'Cinder Connect exact-process binding verifier'
    path = $LauncherPath
    type = 'stdio'
    allowed_extensions = @($ExtensionId)
}
$manifestJson = $manifest | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($ManifestPath, $manifestJson, $utf8NoBom)

$regPath = "HKCU:\Software\Mozilla\NativeMessagingHosts\$HostName"
New-Item -Path $regPath -Force | Out-Null
Set-Item -Path $regPath -Value $ManifestPath

Write-Host ''
Write-Host 'Cinder Connect native host installed.'
Write-Host "Host manifest: $ManifestPath"
Write-Host "Registry key:  $regPath"
Write-Host "Extension ID:  $ExtensionId"
Write-Host ''
Write-Host 'Next: load extension\manifest.json from Firefox about:debugging.'
