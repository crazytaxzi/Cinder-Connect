Get-Process | ForEach-Object {
    $proc = $_
    try { $path = [string]$proc.Path } catch { $path = '' }
    if ([string]::IsNullOrWhiteSpace($path)) {
        try {
            $start = $proc.StartTime.ToFileTimeUtc()
            [PSCustomObject]@{
                Id = $proc.Id
                Name = $proc.ProcessName
                StartFileTimeUtc = $start
            }
        } catch {}
    }
} | Select-Object -First 12 | Format-Table -AutoSize
