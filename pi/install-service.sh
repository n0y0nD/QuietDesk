#!/bin/bash
# Make QuietDesk start by itself when the Pi boots (systemd user service, no sudo).
set -e
cd "$(dirname "$0")"
if [ -f web.pid ] && kill -0 "$(cat web.pid)" 2>/dev/null; then
  kill "$(cat web.pid)"   # stop a copy started by hand with start-web.sh
  rm -f web.pid
  sleep 1
fi
mkdir -p ~/.config/systemd/user
cp quietdesk.service ~/.config/systemd/user/
loginctl enable-linger "$USER" 2>/dev/null || true   # start at boot, even before anyone logs in
systemctl --user daemon-reload
systemctl --user enable --now quietdesk
systemctl --user --no-pager status quietdesk | head -5
