#!/usr/bin/env bash
# Screenshot the virtual display.
OUT="${1:-$HOME/rimworld-logs/shot-$(date +%H%M%S).png}"
DISPLAY=:99 import -window root "$OUT" && echo "$OUT"
