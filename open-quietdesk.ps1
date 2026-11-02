# Open the QuietDesk web console from the laptop.
# 1) Starts web.py on the Pi, 2) opens an SSH tunnel to it, 3) opens http://localhost:8000.
# Keep this window open while you use QuietDesk; close it (or press Ctrl+C) to stop the tunnel.
$pi = "admin@raspberrypi5.local"

Write-Host "Starting QuietDesk on the Pi..."
ssh $pi "~/quietdesk/start-web.sh"

# Open the browser a few seconds from now, once the tunnel below is up.
Start-Job { Start-Sleep -Seconds 5; Start-Process "http://localhost:8000" } | Out-Null

Write-Host "Tunnel open: http://localhost:8000  (keep this window open)"
ssh -N -L 8000:localhost:8000 $pi
