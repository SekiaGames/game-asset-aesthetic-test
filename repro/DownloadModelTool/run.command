#!/bin/sh
# 双击运行（无参数时只做环境检查）。带参数时等价于 python dl.py ...
set -e
cd "$(dirname "$0")"

pick_python() {
  for c in "${COMFYUI_DIR:-}/.venv/bin/python" \
           "$HOME/ComfyUI-Installs/ComfyUI/standalone-env/bin/python" \
           "$HOME/ComfyUI-Installs/ComfyUI/ComfyUI/.venv/bin/python" \
           python3; do
    [ -x "$c" ] || command -v "$c" >/dev/null 2>&1 || continue
    "$c" -c "import huggingface_hub" 2>/dev/null && { echo "$c"; return 0; }
  done
  return 1
}

PY=$(pick_python) || {
  echo "找不到装了 huggingface_hub 的 python。"
  echo "  用 ComfyUI 自带的：<ComfyUI>/standalone-env/bin/python dl.py doctor"
  echo "  或先安装：python3 -m pip install -U huggingface_hub"
  printf '\n按回车关闭…'; read -r _
  exit 1
}

if [ $# -eq 0 ]; then
  "$PY" dl.py doctor
  printf '\n用法：./run.command missing "<工作流.json>"   或   ./run.command get <HF URL>\n'
  printf '按回车关闭…'; read -r _
else
  exec "$PY" dl.py "$@"
fi
