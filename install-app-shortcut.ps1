# Run once: adds a "QuietDesk" shortcut (with Lumi's icon) to the Desktop and the Start menu.
# Double-click it to open the QuietDesk window. To remove, delete the two "QuietDesk" shortcuts.
$target = Join-Path $PSScriptRoot "open-quietdesk-app.ps1"
$icon = Join-Path $PSScriptRoot "quietdesk.ico"
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
    $s = $shell.CreateShortcut((Join-Path $dir "QuietDesk.lnk"))
    $s.TargetPath = "powershell.exe"
    $s.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$target`""
    $s.WorkingDirectory = $PSScriptRoot
    $s.IconLocation = $icon
    $s.WindowStyle = 7
    $s.Description = "QuietDesk: Lumi, your desk companion"
    $s.Save()
    Write-Output "Added: $(Join-Path $dir 'QuietDesk.lnk')"
}
