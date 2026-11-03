# Copies this laptop's SSH public key to the Raspberry Pi,
# so later SSH logins don't ask for a password.
$pub = Join-Path $env:USERPROFILE ".ssh\id_ed25519.pub"
Write-Host "Enter the Pi password (it stays hidden while you type):" -ForegroundColor Cyan
Get-Content $pub | ssh admin@raspberrypi5.local "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo KEY-ADDED-OK"
