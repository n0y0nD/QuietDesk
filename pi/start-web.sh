#!/bin/bash
# Start (or restart) the QuietDesk web console in the background on the Pi.
cd "$(dirname "$0")"
if [ -f web.pid ] && kill -0 "$(cat web.pid)" 2>/dev/null; then
  kill "$(cat web.pid)"
  sleep 1
fi
setsid nohup .venv/bin/python web.py > web.log 2>&1 < /dev/null &
echo $! > web.pid
echo "QuietDesk web console started (log: web.log)"
