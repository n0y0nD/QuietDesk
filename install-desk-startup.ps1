# Run once: QuietDesk's desk window will then start by itself whenever you sign in to Windows.
# To undo, delete "QuietDesk desk.lnk" from the Startup folder (Win+R, shell:startup).
$script = Join-Path $PSScriptRoot "start-desk.ps1"
$link = Join-Path ([Environment]::GetFolderPath("Startup")) "QuietDesk desk.lnk"
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($link)
$s.TargetPath = "powershell.exe"
$s.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$s.WorkingDirectory = $PSScriptRoot
$s.WindowStyle = 7   # minimised
$s.Description = "QuietDesk desk window (mic and speaker for the desk device)"
$s.Save()
Write-Output "Added to Startup: $link"
