$ErrorActionPreference = 'Stop'

$BindingPath = Join-Path $env:LOCALAPPDATA 'CinderConnect\binding.json'
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
        $actualPath = Normalize-Path $process.Path
        $actualStart = [int64]$process.StartTime.ToFileTimeUtc()
    } catch {
        $status = New-Status $false 'stale_pid' 'The bound process is not running.'
        $status.pid = $targetProcessId
        return $status
    }
    if (-not [StringComparer]::OrdinalIgnoreCase.Equals($expectedPath, $actualPath)) {
        $status = New-Status $false 'path_mismatch' 'PID belongs to a different executable.'
        $status.pid = $targetProcessId
        $status.exe_path = $actualPath
        return $status
    }
    if ($expectedStart -ne $actualStart) {
        $status = New-Status $false 'start_time_mismatch' 'PID was reused by a newer process.'
        $status.pid = $targetProcessId
        $status.exe_path = $actualPath
        return $status
    }

    $status = New-Status $true 'attached'
    $status.pid = $targetProcessId
    $status.exe_path = $actualPath
    $status.binding_id = [string]$binding.binding_id
    $status.bound_utc = [string]$binding.bound_utc
    return $status
}
while ($true) {
    $message = Read-NativeMessage
    if ($null -eq $message) {
        break
    }

    if ([string]$message.command -eq 'status') {
        Write-NativeMessage (Get-BindingStatus)
        continue
    }

    Write-NativeMessage ([ordered]@{
        ok = $false
        state = 'unsupported_command'
        detail = 'Only the status command is supported.'
    })
}
