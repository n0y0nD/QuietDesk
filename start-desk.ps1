# QuietDesk on the laptop, hands-free: runs at Windows sign-in (install-desk-startup.ps1 sets that up).
#  1. Keeps an SSH tunnel to the Pi open, and reconnects if the Pi or Wi-Fi restarts.
#  2. Opens QuietDesk in a small Edge app window (desk mode) and minimises it. That window is
#     QuietDesk's mic and speaker: press the button on the desk and talk, nothing to open.
# The first time, the window stays open so you can click "Allow" for the microphone once.

$ErrorActionPreference = "SilentlyContinue"
$PiHosts = @("raspberrypi5.local", "192.168.29.117")   # the Pi's name, then its IP as a backup
$Url = "http://localhost:8000/?desk=1"
$Edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$ProfileDir = "$env:LOCALAPPDATA\QuietDesk\edge-profile"   # its own profile, so Edge's settings stay separate
$FirstRun = -not (Test-Path $ProfileDir)

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

Add-Type -Namespace QuietDesk -Name Win -MemberDefinition '[DllImport("user32.dll")] public static extern bool ShowWindowAsync(System.IntPtr h, int n);'

# 1. Tunnel: try each address until QuietDesk answers (the Pi may still be booting).
$i = 0
$tunnel = $null
while (-not (Test-QuietDesk)) {
    if ($tunnel) { Stop-Process -Id $tunnel.Id -Force }
    $tunnel = Start-Tunnel $PiHosts[$i % $PiHosts.Count]
    $i++
    Start-Sleep 6
}

# 2. The desk window. Flags: play sound without a click first, and keep running at full speed
#    while minimised (so the desk button answers at once).
Start-Process $Edge -ArgumentList @(
    "--user-data-dir=`"$ProfileDir`"", "--app=$Url", "--window-size=480,780", "--no-first-run",
    "--autoplay-policy=no-user-gesture-required", "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows")

if (-not $FirstRun) {
    for ($k = 0; $k -lt 30; $k++) {   # wait for the window, then minimise it
        Start-Sleep 1
        $w = Get-Process msedge | Where-Object { $_.MainWindowTitle -like "QuietDesk desk*" } | Select-Object -First 1
        if ($w) { [QuietDesk.Win]::ShowWindowAsync($w.MainWindowHandle, 6) | Out-Null; break }
    }
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
