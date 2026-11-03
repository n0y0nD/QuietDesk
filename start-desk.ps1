# QuietDesk on the laptop, hands-free: runs at Windows sign-in (install-desk-startup.ps1 sets that up).
#  1. Keeps an SSH tunnel to the Pi open, and reconnects if the Pi or Wi-Fi restarts.
#  2. Opens the QuietDesk app window (its own Edge app window: no address bar, own icon) and minimises it.
#     That window is QuietDesk's mic and speaker: press the button on the desk and talk, nothing to open.
#     Click it in the taskbar (or the QuietDesk shortcut) to see the full console.
# -Show: leave the window open instead of minimising it. The first time it always stays open,
# so you can click "Allow" for the microphone once.
param([switch]$Show)

$ErrorActionPreference = "SilentlyContinue"
$PiHosts = @("raspberrypi5.local", "192.168.29.117")   # the Pi's name, then its IP as a backup
$Url = "http://localhost:8000/?desk=1"
$Edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$ProfileDir = "$env:LOCALAPPDATA\QuietDesk\edge-profile"   # its own profile, so Edge's settings stay separate
$FirstRun = -not (Test-Path $ProfileDir)

. (Join-Path $PSScriptRoot "quietdesk-window.ps1")   # Get-QuietDeskWindow, Show-QuietDeskWindow

function Start-Tunnel($PiHost) {
    Start-Process ssh -WindowStyle Hidden -PassThru -ArgumentList @(
        "-o", "BatchMode=yes", "-o", "HostKeyAlias=raspberrypi5.local", "-o", "ConnectTimeout=6",
        "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3",
        "-N", "-L", "8000:localhost:8000", "admin@$PiHost")
}

function Test-QuietDesk {
    try { (Invoke-WebRequest "http://localhost:8000/api/hw" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 }
    catch { $false }
}

# 1. Tunnel: try each address until QuietDesk answers (the Pi may still be booting).
$i = 0
$tunnel = $null
while (-not (Test-QuietDesk)) {
    if ($tunnel) { Stop-Process -Id $tunnel.Id -Force }
    $tunnel = Start-Tunnel $PiHosts[$i % $PiHosts.Count]
    $i++
    Start-Sleep 6
}

# 2. The app window, unless it is already open. Flags: play sound without a click first, and keep
#    running at full speed while minimised (so the desk button answers at once).
if (-not (Get-QuietDeskWindow)) {
    Start-Process $Edge -ArgumentList @(
        "--user-data-dir=`"$ProfileDir`"", "--app=$Url", "--window-size=1100,820", "--no-first-run",
        "--autoplay-policy=no-user-gesture-required", "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows")
    for ($k = 0; $k -lt 30 -and -not (Get-QuietDeskWindow); $k++) { Start-Sleep 1 }
}
$w = Get-QuietDeskWindow
if ($w) {
    if ($Show -or $FirstRun) { Show-QuietDeskWindow } else { [QuietDesk.Win]::ShowWindowAsync($w, 6) | Out-Null }
}

# 3. Keep the tunnel up for as long as the laptop is on.
while ($true) {
    Start-Sleep 5
    if (-not (Test-QuietDesk)) {
        if ($tunnel) { Stop-Process -Id $tunnel.Id -Force }
        $tunnel = Start-Tunnel $PiHosts[$i % $PiHosts.Count]
        $i++
        Start-Sleep 6
    }
}
