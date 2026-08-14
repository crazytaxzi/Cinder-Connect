$ErrorActionPreference = 'Stop'

$BindingPath = Join-Path $env:LOCALAPPDATA 'CinderConnect\binding.json'
$ExtensionSeenPath = Join-Path $env:LOCALAPPDATA 'CinderConnect\extension_seen.json'
$InputStream = [Console]::OpenStandardInput()
$OutputStream = [Console]::OpenStandardOutput()
$Reader = New-Object System.IO.BinaryReader($InputStream)
$Writer = New-Object System.IO.BinaryWriter($OutputStream)
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Write-NativeMessage {
    param([Parameter(Mandatory=$true)]$Object)
    $json = $Object | ConvertTo-Json -Compress -Depth 6
    $bytes = $Utf8.GetBytes($json)
    $Writer.Write([uint32]$bytes.Length)
    $Writer.Write($bytes)
    $Writer.Flush()
}
function Read-NativeMessage {
    try {
        $length = $Reader.ReadUInt32()
    } catch {
        return $null
    }
    if ($length -gt 4194304) {
        throw 'Native message is larger than 4 MiB.'
    }
    $bytes = $Reader.ReadBytes([int]$length)
    if ($bytes.Length -ne $length) {
        return $null
    }
    $json = $Utf8.GetString($bytes)
    return $json | ConvertFrom-Json
}
function Normalize-Path {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ''
    }
    return [System.IO.Path]::GetFullPath($Path)
}

function New-Status {
    param(
        [bool]$Ok,
        [string]$State,
        [string]$Detail = ''
    )
    return [ordered]@{
        ok = $Ok
        state = $State
        detail = $Detail
    }
}
function Get-BindingStatus {
    if (-not (Test-Path -LiteralPath $BindingPath)) {
        return New-Status $false 'not_bound' 'No binding file exists.'
    }
    try {
        $binding = Get-Content -LiteralPath $BindingPath -Raw | ConvertFrom-Json
    } catch {
        return New-Status $false 'bad_binding' $_.Exception.Message
    }

    try {
        $targetProcessId = [int]$binding.pid
        $expectedPath = Normalize-Path ([string]$binding.exe_path)
        $expectedStart = [int64]$binding.start_filetime_utc
    } catch {
        return New-Status $false 'bad_binding' 'Binding fields are invalid.'
    }
    try {
        $process = Get-Process -Id $targetProcessId -ErrorAction Stop
        $process.Refresh()
        $actualStart = [int64]$process.StartTime.ToFileTimeUtc()
        $actualName = [string]$process.ProcessName
    } catch {
        $status = New-Status $false 'stale_pid' 'The bound process is not running.'
        $status.pid = $targetProcessId
        return $status
    }

    if ($expectedStart -ne $actualStart) {
        $status = New-Status $false 'start_time_mismatch' 'PID was reused by a newer process.'
        $status.pid = $targetProcessId
        return $status
    }

    $expectedName = [System.IO.Path]::GetFileNameWithoutExtension($expectedPath)
    if (-not [StringComparer]::OrdinalIgnoreCase.Equals($expectedName, $actualName)) {
        $status = New-Status $false 'process_name_mismatch' 'PID belongs to a differently named executable.'
        $status.pid = $targetProcessId
        $status.process_name = $actualName
        return $status
    }

    $actualPath = ''
    try {
        $actualPath = Normalize-Path ([string]$process.Path)
    } catch {}

    $pathVerified = -not [string]::IsNullOrWhiteSpace($actualPath)
    if ($pathVerified -and -not [StringComparer]::OrdinalIgnoreCase.Equals($expectedPath, $actualPath)) {
        $status = New-Status $false 'path_mismatch' 'PID belongs to a different executable path.'
        $status.pid = $targetProcessId
        $status.exe_path = $actualPath
        return $status
    }

    $status = New-Status $true 'attached'
    $status.pid = $targetProcessId
    $status.exe_path = $(if ($pathVerified) { $actualPath } else { $expectedPath })
    $status.path_verified = $pathVerified
    if (-not $pathVerified) {
        $status.detail = 'Live executable path is hidden by Windows elevation; PID, creation time, and process name matched.'
    }
    $status.binding_id = [string]$binding.binding_id
    $status.bound_utc = [string]$binding.bound_utc
    return $status
}

function Write-ExtensionSeen {
    param($Status)
    $record = [ordered]@{
        last_seen_utc = [DateTime]::UtcNow.ToString('o')
        state = [string]$Status.state
        pid = $Status.pid
        binding_id = $Status.binding_id
    }
    $dir = Split-Path -Parent $ExtensionSeenPath
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $json = $record | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText($ExtensionSeenPath, $json, $Utf8)
}

function Add-ExtensionPresence {
    param($Status)
    if (-not (Test-Path -LiteralPath $ExtensionSeenPath)) {
        $Status.extension_seen = $false
        return $Status
    }
    try {
        $seen = Get-Content -LiteralPath $ExtensionSeenPath -Raw | ConvertFrom-Json
        $Status.extension_seen = $true
        $Status.extension_last_seen_utc = [string]$seen.last_seen_utc
        $Status.extension_last_state = [string]$seen.state
        $Status.extension_last_binding_id = [string]$seen.binding_id
    } catch {
        $Status.extension_seen = $false
    }
    return $Status
}

while ($true) {
    $message = Read-NativeMessage
    if ($null -eq $message) {
        break
    }

    if ([string]$message.command -eq 'extension_status') {
        $status = Get-BindingStatus
        Write-ExtensionSeen $status
        Write-NativeMessage (Add-ExtensionPresence $status)
        continue
    }

    if ([string]$message.command -eq 'status') {
        $status = Get-BindingStatus
        Write-NativeMessage (Add-ExtensionPresence $status)
        continue
    }

    Write-NativeMessage ([ordered]@{
        ok = $false
        state = 'unsupported_command'
        detail = 'Only the status command is supported.'
    })
}
