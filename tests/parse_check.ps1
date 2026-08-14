$files = @(
    'C:\Projects\Cinder-Connect\native-host\native_host.ps1',
    'C:\Projects\Cinder-Connect\scripts\launch_and_bind.ps1',
    'C:\Projects\Cinder-Connect\scripts\install_native_host.ps1',
    'C:\Projects\Cinder-Connect\mcp-server\setup_mcp.ps1',
    'C:\Projects\Cinder-Connect\mcp-server\run_mcp.ps1'
)

foreach ($file in $files) {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $file, [ref]$tokens, [ref]$errors
    ) | Out-Null
    Write-Output "$file errors=$($errors.Count)"
    foreach ($error in $errors) {
        Write-Output "  $($error.Message)"
    }
}
