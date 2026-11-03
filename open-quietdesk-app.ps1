# The QuietDesk shortcut runs this: bring the QuietDesk window to the front, or start QuietDesk if it isn't running.
. (Join-Path $PSScriptRoot "quietdesk-window.ps1")
if (-not (Show-QuietDeskWindow)) {
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$(Join-Path $PSScriptRoot 'start-desk.ps1')`"", "-Show")
}
