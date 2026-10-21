#!/bin/sh
# P0 最小闭环：合成部件图 → 切件 → 绑骨 → 打包 → 官方 4.2 运行时校验
#
# 双击本文件即可运行（macOS 会用 Terminal 打开），也可以在命令行执行 ./run.command
#   PY=/path/to/python   指定解释器（默认找本机 venv，再退回 python3）
#   NODE=/path/to/node   指定 node（默认找 PATH，再退回 workbuddy 自带的版本）
#   NO_PAUSE=1           结束后不等回车（给脚本 / CI 用）
#   NO_OPEN=1            成功后不自动打开 setup pose
#   OPEN_PREVIEW=1       成功后改为在浏览器里打开 preview.html（需要联网取 spine-player）
set -e
cd "$(dirname "$0")"

finish() {
  rc=$?
  if [ "$rc" -ne 0 ]; then
    printf '\n出错了（退出码 %s），上面是最后几行输出。\n' "$rc"
  fi
  if [ -t 0 ] && [ -t 1 ] && [ -z "${NO_PAUSE:-}" ]; then
    printf '\n按回车关闭窗口…'
    read -r _ || true
  fi
  exit "$rc"
}
trap finish EXIT

# ---- 找解释器（双击运行时 /bin/sh 读不到 .zshrc，PATH 可能很干净）----
if [ -z "${PY:-}" ]; then
  for p in "$HOME/.workbuddy/binaries/python/envs/spine-p0/bin/python" python3 python; do
    if command -v "$p" >/dev/null 2>&1; then PY=$p; break; fi
  done
fi
[ -n "${PY:-}" ] || { echo "找不到 python，用 PY=... 指定"; exit 1; }

if [ -z "${NODE:-}" ]; then
  if command -v node >/dev/null 2>&1; then
    NODE=$(command -v node)
  else
    for c in "$HOME"/.workbuddy/binaries/node/versions/*/bin/node; do
      if [ -x "$c" ]; then NODE=$c; break; fi
    done
  fi
fi
[ -n "${NODE:-}" ] || { echo "找不到 node，用 NODE=... 指定"; exit 1; }
NPM=$(dirname "$NODE")/npm
[ -x "$NPM" ] || NPM=$(command -v npm || echo npm)

printf 'python  %s\nnode    %s\n\n' "$("$PY" -V 2>&1)" "$("$NODE" -v 2>&1)"

# ws 是 skill 包的拷贝，不入库；第一次运行时自动铺开并装 Node 依赖
if [ ! -d ws/scripts ]; then
  echo "[0/5] 铺开 skills/workspace → ws/"
  cp -R ../../extensions/skills/game-asset-spine-cutout/assets/workspace ws
fi
if [ ! -d ws/node_modules ]; then
  echo "[0/5] 安装 Node 依赖（spine-core）"
  (cd ws && "$NPM" install --omit=dev --no-audit --no-fund)
fi

echo "[1/5] 生成合成部件图"
"$PY" art/make-sheet.py

echo "[2/5] 切件（色键 + 连通域）"
"$PY" -I ws/scripts/spine-cutout-parts.py art/sheet.png out/parts

echo "[3/5] 绑骨 + 离线预览"
"$PY" -I ws/scripts/spine-cutout-rig.py out/parts out/rig
# spine-cutout-rig.py 把输出名写死成 kurumi.json，这里改成我们要的名字
mv -f out/rig/kurumi.json out/rig/p0dummy.json

echo "[4/5] 打包 atlas + preview.html"
"$PY" -I ws/scripts/spine-pack.py out/rig --name p0dummy

echo "[5/5] 官方 spine-core 4.2 加载校验"
"$NODE" ws/scripts/spine-verify.mjs out/rig p0dummy

echo ""
echo "完成 → $(pwd)/out/rig"
echo "  setup_pose.png / 每个动作的 gif / *_sheet.png / p0dummy.atlas / preview.html"
if [ -t 0 ] && [ -t 1 ]; then
  if [ -n "${OPEN_PREVIEW:-}" ]; then
    open "file://$(pwd)/out/rig/preview.html" 2>/dev/null || true
  elif [ -z "${NO_OPEN:-}" ]; then
    open out/rig/setup_pose.png 2>/dev/null || true
  fi
fi
