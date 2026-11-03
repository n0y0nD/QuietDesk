#!/bin/bash
# Start (or restart) the QuietDesk web console in the background on the Pi.
cd "$(dirname "$0")"
if systemctl --user is-enabled quietdesk >/dev/null 2>&1; then
  systemctl --user restart quietdesk   # installed as a service (install-service.sh)
  echo "QuietDesk restarted (service, log: web.log)"
  exit 0
fi
if [ -f web.pid ] && kill -0 "$(cat web.pid)" 2>/dev/null; then
  kill "$(cat web.pid)"
  sleep 1
fi
setsid nohup .venv/bin/python -u web.py > web.log 2>&1 < /dev/null &
echo $! > web.pid
echo "QuietDesk web console started (log: web.log)"
