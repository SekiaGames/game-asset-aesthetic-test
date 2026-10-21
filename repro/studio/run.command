#!/bin/sh
# 双击启动工作台（Terminal 窗口留着，关掉即停止服务）
set -e
cd "$(dirname "$0")/.."

for p in "$HOME/.workbuddy/binaries/python/envs/spine-p0/bin/python" python3; do
  if command -v "$p" >/dev/null 2>&1; then PY=$p; break; fi
done
[ -n "${PY:-}" ] || { echo "找不到 python"; exit 1; }

PORT=${PORT:-8765}
URL="http://127.0.0.1:$PORT/"

"$PY" studio/server.py &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' INT TERM EXIT
sleep 1
open "$URL" 2>/dev/null || true
printf '\n工作台 %s\n按 Ctrl-C 停止\n' "$URL"
wait $SRV
