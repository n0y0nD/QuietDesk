# Helpers to find and show the QuietDesk app window (the Edge app window using QuietDesk's own profile).
Add-Type -Namespace QuietDesk -Name Win -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool ShowWindowAsync(System.IntPtr h, int n);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr h);
'@ -ErrorAction SilentlyContinue

function Get-QuietDeskWindow {
    # The Edge process that owns QuietDesk's window is the one started with QuietDesk's profile folder.
    $ids = Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
        Where-Object { $_.CommandLine -like "*QuietDesk\edge-profile*" -and $_.CommandLine -notlike "*--type=*" } |
        Select-Object -ExpandProperty ProcessId
    foreach ($id in $ids) {
        $p = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($p -and $p.MainWindowHandle -ne 0) { return $p.MainWindowHandle }
    }
    return $null
}

function Show-QuietDeskWindow {
    $h = Get-QuietDeskWindow
    if ($h) {
        [QuietDesk.Win]::ShowWindowAsync($h, 9) | Out-Null   # restore if minimised
        [QuietDesk.Win]::SetForegroundWindow($h) | Out-Null
        return $true
    }
    return $false
}
