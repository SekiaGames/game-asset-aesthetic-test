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
import re
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



MODEL_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._+\-]*\.(?:safetensors|ckpt|pt|pth|bin|onnx|gguf|sft))", re.I)
_list_cache = {"t": 0, "map": {}}


def comfy_dir():
    for d in COMFY_DIR_GUESSES:
        if d and os.path.isdir(os.path.join(d, "models")):
            return d
    return None


def workflows():
    d = comfy_dir()
    if not d:
        return []
    wd = os.path.join(d, "user", "default", "workflows")
    out = []
    for p in glob.glob(os.path.join(wd, "**", "*.json"), recursive=True):
        out.append({"path": p, "name": os.path.basename(p), "mtime": int(os.path.getmtime(p))})
    out.sort(key=lambda x: -x["mtime"])
    return out


def have_models():
    d = comfy_dir()
    idx = set()
    if not d:
        return idx
    for _, _, fs in os.walk(os.path.join(d, "models")):
        for f in fs:
            idx.add(f.lower())
    return idx


def model_list_map(ttl=120):
    """filename(小写) -> Manager 清单条目（缓存已改写成 hf-mirror）"""
    if time.time() - _list_cache["t"] < ttl and _list_cache["map"]:
        return _list_cache["map"]
    d = comfy_dir()
    m = {}
    if d:
        for p in sorted(glob.glob(os.path.join(d, "user", "__manager", "cache", "*_model-list.json"))):
            try:
                data = json.load(open(p, encoding="utf-8"))
            except Exception:                                   # noqa: BLE001
                continue
            for e in data.get("models") or []:
                fn = (e.get("filename") or "").lower()
                if fn and fn not in m:
                    m[fn] = e
    _list_cache.update(t=time.time(), map=m)
    return m


URL_RE = re.compile(r"https?://[^\s\"'()\\]+\.(?:safetensors|ckpt|pt|pth|bin|onnx|gguf|sft)", re.I)


def scan_workflow(path):
    """从工作流里抽模型文件名，并尽量找到下载源。

    优先级：Manager 清单 → 工作流注释里自带的 URL（新版模板会把 Comfy-Org 的
    resolve/main/... 链接写进 note，实测 Qwen-Image 2.1 模板就是如此）。
    """
    raw = open(path, encoding="utf-8").read()
    names = sorted({mm.group(1) for mm in MODEL_RE.finditer(raw)})
    have = have_models()
    lst = model_list_map()

    wf_urls = {}
    for m in URL_RE.finditer(raw):
        u = m.group(0)
        fn = u.rsplit("/", 1)[-1].lower()
        wf_urls.setdefault(fn, u)

    out = []
    for n in names:
        low = n.lower()
        e = lst.get(low)
        if e:
            out.append({"filename": n, "present": low in have, "url": e.get("url"),
                        "type": e.get("type"), "save_path": e.get("save_path"),
                        "size": e.get("size"), "name": e.get("name"), "src": "manager"})
            continue
        u = wf_urls.get(low)
        save_path = "default"
        if u:
            parts = u.split("/resolve/")[-1].split("/")     # main/diffusion_models/xxx.safetensors
            if len(parts) > 2:
                save_path = parts[1]
        out.append({"filename": n, "present": low in have, "url": u,
                    "type": save_path, "save_path": save_path,
                    "size": None, "name": None, "src": "workflow" if u else None})
    return out


def split_url(u):
    """https://hf-mirror.com/Org/Repo/resolve/main/vae/x.safetensors -> (Org/Repo, vae/x.safetensors)"""
    if "/resolve/" not in u:
        return None, None
    base, rest = u.split("/resolve/", 1)
    parts = base.split("/")
    if len(parts) < 5:
        return None, None
    repo = "/".join(parts[-2:])
    tail = rest.split("/", 1)
    return (repo, tail[1]) if len(tail) == 2 else (None, None)


JOBS = []
_job_lock = __import__("threading").Lock()


def comfy_python(comfy):
    """下载子进程用的是 ComfyUI 自己的 python（里面有 huggingface_hub）。"""
    for c in (os.path.join(comfy, ".venv", "bin", "python"),
              os.path.join(os.path.dirname(comfy), "standalone-env", "bin", "python")):
        if os.access(c, os.X_OK):
            return c
    return sys.executable


def _run_job(job, comfy):
    """下载交给独立工具 DownloadModelTool，工作台不再自己实现下载。"""
    job["state"] = "running"
    dl = os.path.join(ROOT, "DownloadModelTool", "dl.py")
    argv = [comfy_python(comfy), "-u", dl, "get", job["url"]]
    try:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=0)
        buf = ""
        while True:
            ch = p.stdout.read(1)
            if not ch:
                break
            if ch in "\r\n":
                line = buf.strip()
                buf = ""
                if line:
                    job["last"] = line[-120:]
            else:
                buf += ch
        if p.wait() == 0:
            job["state"] = "done"
        else:
            job["state"] = "error"
            job["last"] = (job.get("last") or "") + f" (exit {p.returncode})"
    except Exception as e:                                  # noqa: BLE001
        job["state"] = "error"
        job["last"] = str(e)[:120]


def start_jobs(items):
    comfy = comfy_dir()
    if not comfy:
        return 0, ["找不到 ComfyUI 目录"]
    added, errs = 0, []
    for it in items:
        u = (it.get("url") or "").replace("https://huggingface.co", "https://hf-mirror.com")
        repo, path = split_url(u)
        if not repo:
            errs.append(f"{it.get('filename')}: URL 无法解析")
            continue
        with _job_lock:
            if any(j["path"] == path and j["state"] in ("queued", "running") for j in JOBS):
                continue
            JOBS.append({"filename": it.get("filename") or path.rsplit("/", 1)[-1],
                         "repo": repo, "path": path, "url": u,
                         "state": "queued", "last": ""})
            added += 1
    if added:
        t = __import__("threading").Thread(target=_worker, args=(comfy,), daemon=True)
        t.start()
    return added, errs


def _worker(comfy):
    while True:
        with _job_lock:
            nxt = next((j for j in JOBS if j["state"] == "queued"), None)
        if not nxt:
            return
        _run_job(nxt, comfy)


def manager_post(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else b""
    req = urllib.request.Request(COMFY + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


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
        if u.path == "/api/workflows":
            return self._send(200, json.dumps({"items": workflows()}, ensure_ascii=False))
        if u.path == "/api/jobs":
            return self._send(200, json.dumps({"items": JOBS[-40:]}, ensure_ascii=False))
        if u.path == "/api/queue":
            try:
                with urllib.request.urlopen(COMFY + "/v2/manager/queue/status", timeout=5) as r:
                    return self._send(200, r.read(), "application/json; charset=utf-8")
            except Exception as e:                          # noqa: BLE001
                return self._send(502, {"error": str(e)[:120]})
        if u.path == "/api/run":
            return self.stream(q.get("step", [""])[0])
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = {}
        if n:
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:                               # noqa: BLE001
                return self._send(400, {"error": "bad json"})

        if u.path == "/api/scan":
            wf = body.get("workflow") or ""
            if not os.path.isfile(wf):
                return self._send(400, {"error": "工作流文件不存在"})
            return self._send(200, json.dumps({"items": scan_workflow(wf)}, ensure_ascii=False))

        if u.path == "/api/fix":
            items = [i for i in (body.get("items") or []) if i.get("url")]
            if not items:
                return self._send(400, {"error": "没有可下载的条目（没匹配到下载源）"})
            added, errs = start_jobs(items)
            return self._send(200, json.dumps({"queued": added, "errors": errs}, ensure_ascii=False))

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
