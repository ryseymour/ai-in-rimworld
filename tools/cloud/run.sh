#!/usr/bin/env bash
# Start orchestrator (publishing telemetry) and RimWorld under Xvfb with a dev quicktest colony.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
GAME_DIR="${GAME_DIR:-$HOME/rimworld}"
LOG_DIR="${LOG_DIR:-$HOME/rimworld-logs}"
mkdir -p "$LOG_DIR"
export DISPLAY=:99

if ! pgrep -f "Xvfb :99" >/dev/null; then
  Xvfb :99 -screen 0 1600x900x24 -nolisten tcp >"$LOG_DIR/xvfb.log" 2>&1 &
  sleep 1
fi
if ! pgrep -f "airim serve" >/dev/null; then
  (cd "$REPO_DIR/orchestrator" && nohup uv run airim serve ${PUBLISH:+--publish} >"$LOG_DIR/orchestrator.log" 2>&1 &)
fi
export LIBGL_ALWAYS_SOFTWARE=1 MESA_GL_VERSION_OVERRIDE=3.3 GALLIUM_DRIVER=llvmpipe
cd "$GAME_DIR"
nohup ./RimWorldLinux -screen-width 1600 -screen-height 900 -screen-fullscreen 0 -logfile "$LOG_DIR/player.log" ${QUICKTEST:+-quicktest} >"$LOG_DIR/stdout.log" 2>&1 &
echo "rimworld pid $! ; logs in $LOG_DIR ; screenshot: tools/cloud/shot.sh"
