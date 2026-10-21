"""本地工作台：把流水线每一步和产物预览放在一个页面里（只用标准库）。

启动：
    <venv>/bin/python studio/server.py
    PORT=9000 COMFYUI_URL=http://127.0.0.1:8188 COMFYUI_DIR=/path/to/ComfyUI <venv>/bin/python studio/server.py

设计取舍：
- 不重做 ComfyUI 的图编辑界面。文生图 / 分件仍在 ComfyUI 里跑，这里负责
  「按顺序调脚本 + 看产物 + 看清环境缺什么」。
- 每一步都是「一条命令 + 一组产物」，脚本本身仍可直接在终端跑；页面只做编排与展示。
- 只允许跑预置步骤、只允许读 repro/ 下的文件。
"""
import glob
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                 # repro/
P1 = os.path.join(ROOT, "p1")
PORT = int(os.environ.get("PORT", 8765))
COMFY = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
PY = sys.executable

# 常见安装位置兜底（本机是 standalone 布局：<install>/ComfyUI）
COMFY_DIR_GUESSES = [
    os.environ.get("COMFYUI_DIR"),
    os.path.expanduser("~/ComfyUI"),
    "/Volumes/Data/Users/sekia/ComfyUI-Installs/ComfyUI/ComfyUI",
    os.path.expanduser("~/ComfyUI-Installs/ComfyUI/ComfyUI"),
]


def find_node():
    p = shutil.which("node")
    if p:
        return p
    for c in glob.glob(os.path.expanduser("~/.workbuddy/binaries/node/versions/*/bin/node")):
        if os.access(c, os.X_OK):
            return c
    return "node"


NODE = find_node()
_env_cache = {"t": 0, "v": None}


def comfy_env(ttl=20):
    """一次拿全：服务、版本、底模列表、关键节点、磁盘上的安装目录。"""
    if time.time() - _env_cache["t"] < ttl and _env_cache["v"]:
        return _env_cache["v"]
    env = {"up": False, "url": COMFY, "version": None, "checkpoints": [],
           "seethrough": False, "dwpose": False, "dir": None, "error": None}
    for d in COMFY_DIR_GUESSES:
        if d and os.path.isdir(os.path.join(d, "models")) and os.path.isdir(os.path.join(d, "custom_nodes")):
            env["dir"] = d
            break
    try:
        with urllib.request.urlopen(COMFY + "/system_stats", timeout=2) as r:
            j = json.loads(r.read().decode())
        env["up"] = True
        env["version"] = (j.get("system") or {}).get("comfyui_version")
    except Exception as e:                                    # noqa: BLE001
        env["error"] = str(e)[:90]
        _env_cache.update(t=time.time(), v=env)
        return env
    try:
        with urllib.request.urlopen(COMFY + "/object_info", timeout=8) as r:
            oi = json.loads(r.read().decode())
        ck = ((oi.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {})
               .get("ckpt_name") or [[]])[0])
        env["checkpoints"] = list(ck)
        env["seethrough"] = any(k.startswith("SeeThrough_") for k in oi)
        env["dwpose"] = any("DWPose" in k or "DWPreprocessor" == k for k in oi)
    except Exception as e:                                    # noqa: BLE001
        env["error"] = str(e)[:90]
    _env_cache.update(t=time.time(), v=env)
    return env


def steps():
    """步骤表：id / 名称 / 命令（可多条）/ 产物 / 依赖。"""
    return [
        {"id": "t2i", "name": "① 文生图", "desc": "ComfyUI 出侧视基准图",
         "needs": ("comfy", "checkpoint"), "cmd": [], "out": ["p1/art/t2i/*.png"]},
        {"id": "parts", "name": "② 分件生成", "desc": "头 / 裙 / 手臂 / 腿，各自透明底",
         "needs": ("comfy", "checkpoint"), "cmd": [], "out": ["p1/art/parts-gen/*.png"]},
        {"id": "measure", "name": "③ 清理 + 测量", "desc": "褪棋盘格、去水印、统计主色 bbox",
         "needs": (), "cwd": P1, "cmd": [[PY, "measure.py"]],
         "out": ["p1/art/clean/ref.png", "p1/measurements.json"]},
        {"id": "compose", "name": "④ 标定 + 拼件", "desc": "按目标跨度缩放、关节对枢轴、补内部空洞",
         "needs": (), "cwd": P1, "cmd": [[PY, "compose.py"]],
         "out": ["p1/out/exploded.png", "p1/out/parts/part_00.png", "p1/rig-constants.json"]},
        {"id": "rig", "name": "⑤ 绑骨", "desc": "Spine 4.2 JSON + 每个动作的 GIF",
         "needs": (), "cwd": P1,
         "cmd": [[PY, "-I", "ws-rig/spine-cutout-rig.py", "out/parts", "out/rig"],
                 ["/bin/sh", "-c",
                  "[ -f out/rig/kurumi.json ] && mv -f out/rig/kurumi.json out/rig/mint.json || true"]],
         "out": ["p1/out/rig/setup_pose.png", "p1/out/rig/idle.gif", "p1/out/rig/walk_sheet.png"]},
        {"id": "pack", "name": "⑥ 打包 atlas", "desc": "装箱 + bleed + 生成 preview.html",
         "needs": (), "cwd": P1,
         "cmd": [[PY, "-I", "ws-rig/spine-pack.py", "out/rig", "--name", "mint"]],
         "out": ["p1/out/rig/mint.png", "p1/out/rig/preview.html"]},
        {"id": "verify", "name": "⑦ 运行时校验", "desc": "官方 spine-core 4.2 加载，报缺失附件",
         "needs": (), "cwd": os.path.join(ROOT, "p0", "ws"),
         "cmd": [[NODE, "scripts/spine-verify.mjs", os.path.join(P1, "out", "rig"), "mint"]],
         "out": []},
    ]


MISSING = {"comfy": "ComfyUI 未启动", "checkpoint": "缺底模",
           "seethrough": "缺 See-through 节点", "dwpose": "缺 DWPose 节点",
           "ffmpeg": "缺 ffmpeg"}


def step_view(s, env):
    miss = []
    if "comfy" in s["needs"] and not env["up"]:
        miss.append("comfy")
    if "checkpoint" in s["needs"] and not env["checkpoints"]:
        miss.append("checkpoint")
    if "seethrough" in s["needs"] and not env["seethrough"]:
        miss.append("seethrough")
    if "dwpose" in s["needs"] and not env["dwpose"]:
        miss.append("dwpose")
    items = []
    for pat in s["out"]:
        for p in sorted(glob.glob(os.path.join(ROOT, pat))):
            items.append({"rel": os.path.relpath(p, ROOT), "name": os.path.basename(p),
                          "size": os.path.getsize(p), "mtime": int(os.path.getmtime(p))})
    return {"id": s["id"], "name": s["name"], "desc": s["desc"],
            "needs": [MISSING[m] for m in s["needs"]],
            "blocked": [MISSING[m] for m in miss], "has_cmd": bool(s["cmd"]),
            "artifacts": items}


def safe_path(rel):
    p = os.path.realpath(os.path.join(ROOT, rel))
    if os.path.commonpath([p, os.path.realpath(ROOT)]) != os.path.realpath(ROOT):
        return None
    return p if os.path.isfile(p) else None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % a))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/api/state":
            env = comfy_env()
            ff = bool(shutil.which("ffmpeg"))
            return self._send(200, json.dumps({
                "env": {"up": env["up"], "url": env["url"], "version": env["version"],
                        "dir": env["dir"], "error": env["error"],
                        "checkpoints": env["checkpoints"], "seethrough": env["seethrough"],
                        "dwpose": env["dwpose"], "ffmpeg": ff,
                        "spine_core": os.path.isdir(os.path.join(ROOT, "p0", "ws", "node_modules"))},
                "steps": [step_view(s, env) for s in steps()]}, ensure_ascii=False))
        if u.path == "/api/file":
            p = safe_path(unquote(q.get("p", [""])[0]))
            if not p:
                return self._send(404, "not found", "text/plain; charset=utf-8")
            ctype = mimetypes.guess_type(p)[0] or "application/octet-stream"
            if p.endswith(".json"):
                ctype = "application/json; charset=utf-8"
            if p.endswith(".html"):
                ctype = "text/html; charset=utf-8"
            with open(p, "rb") as f:
                return self._send(200, f.read(), ctype)
        if u.path == "/api/run":
            return self.stream(q.get("step", [""])[0])
        self._send(404, "not found", "text/plain")

    def stream(self, sid):
        s = next((x for x in steps() if x["id"] == sid), None)
        if not s:
            return self._send(400, "unknown step", "text/plain")
        if not s["cmd"]:
            return self._send(409, "该步骤还没接命令行实现（需要 ComfyUI 工作流）", "text/plain")

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def emit(obj):
            self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode())
            self.wfile.flush()

        env2 = dict(os.environ, PYTHONUNBUFFERED="1")
        ok = True
        try:
            for argv in s["cmd"]:
                emit({"type": "line", "text": "$ " + " ".join(
                    os.path.basename(a) if i == 0 else a for i, a in enumerate(argv))})
                p = subprocess.Popen(argv, cwd=s.get("cwd", P1), env=env2, text=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
                for line in p.stdout:
                    emit({"type": "line", "text": line.rstrip("\n")})
                if p.wait() != 0:
                    ok = False
                    emit({"type": "line", "text": f"退出码 {p.returncode}"})
                    break
            emit({"type": "done", "ok": ok})
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.close_connection = True


if __name__ == "__main__":
    e = comfy_env(0)
    print(f"workbench  http://127.0.0.1:{PORT}")
    print(f"comfyui    {COMFY}  ({'up ' + str(e['version']) if e['up'] else 'down'})")
    print(f"comfyui    dir={e['dir']}  底模={len(e['checkpoints'])}  "
          f"seethrough={e['seethrough']} dwpose={e['dwpose']}")
    print(f"python     {PY}\nnode       {NODE}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
