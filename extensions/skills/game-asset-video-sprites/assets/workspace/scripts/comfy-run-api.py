"""跑一个 API 格式的 ComfyUI 工作流，取回所有输出图片（拆层方案对比用：Qwen-Image-Layered、See-through）。

    python -I scripts/comfy-run-api.py <workflow.json> <out_dir> \
        --image 1=<图片路径> [--set 15.seed=3 --set 14.layers=8 ...] [--seethrough]

--image 节点号=路径：上传图片并填进该 LoadImage；--set 节点号.字段=值（值按 JSON 解析，失败就当字符串）。
输出：SaveImage 类节点的图片按「节点号_序号.png」存到 out_dir；--seethrough 时再按 ComfyUI output 里
seethrough_psd_info.log 指向的 layers.json，把 See-through 存的各层 PNG 和 layers.json 拷过来。
只用标准库 + ComfyUI HTTP API（写法同 comfy-batch-rmbg.py）；ComfyUI 需已启动。
"""
import argparse
import json
import os
import shutil
import time
import urllib.parse
import urllib.request
import uuid

COMFY = os.environ.get("COMFYUI_DIR", "ComfyUI")  # ComfyUI 目录（含 custom_nodes / models / output）
COMFY_OUT = os.path.join(COMFY, "output")


def upload(base, path):
    boundary = uuid.uuid4().hex
    name = f"runapi_{uuid.uuid4().hex[:8]}_{os.path.basename(path)}"
    with open(path, "rb") as f:
        data = f.read()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            f"Content-Type: image/png\r\n\r\n").encode() + data + (
            f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n").encode()
    req = urllib.request.Request(f"{base}/upload/image", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return json.load(urllib.request.urlopen(req))["name"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow")
    ap.add_argument("out")
    ap.add_argument("--image", action="append", default=[])
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--seethrough", action="store_true")
    ap.add_argument("--base", default="http://127.0.0.1:8188")
    ap.add_argument("--timeout", type=float, default=3600)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    with open(a.workflow, encoding="utf-8") as f:
        g = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    for spec in a.image:
        node, path = spec.split("=", 1)
        g[node]["inputs"]["image"] = upload(a.base, path)
    for spec in a.set:
        key, val = spec.split("=", 1)
        node, field = key.split(".", 1)
        try:
            val = json.loads(val)
        except json.JSONDecodeError:
            pass
        g[node]["inputs"][field] = val
    req = urllib.request.Request(f"{a.base}/prompt", json.dumps({"prompt": g, "client_id": uuid.uuid4().hex}).encode(),
                                 {"Content-Type": "application/json"})
    resp = json.load(urllib.request.urlopen(req))
    if resp.get("node_errors"):
        raise SystemExit(f"工作流校验失败: {json.dumps(resp['node_errors'], ensure_ascii=False)[:2000]}")
    pid = resp["prompt_id"]
    t0 = time.time()
    while True:
        h = json.load(urllib.request.urlopen(f"{a.base}/history/{pid}")).get(pid)
        if h and h.get("status", {}).get("completed"):
            break
        if h and h.get("status", {}).get("status_str") == "error":
            msgs = [m for m in h["status"].get("messages", []) if m[0] == "execution_error"]
            raise SystemExit(f"执行失败: {json.dumps(msgs, ensure_ascii=False)[:3000]}")
        if time.time() - t0 > a.timeout:
            raise SystemExit("超时")
        time.sleep(2)
    n = 0
    for node, out in h["outputs"].items():
        for i, img in enumerate(out.get("images", [])):
            q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img["subfolder"], "type": img["type"]})
            with open(os.path.join(a.out, f"{node}_{i:02d}.png"), "wb") as f:
                f.write(urllib.request.urlopen(f"{a.base}/view?{q}").read())
            n += 1
    if a.seethrough:
        with open(os.path.join(COMFY_OUT, "seethrough_psd_info.log")) as f:
            info_name = f.read().strip()
        info = json.load(open(os.path.join(COMFY_OUT, info_name), encoding="utf-8"))
        for L in info["layers"]:
            for k in ("filename", "depth_filename"):
                if k in L:
                    shutil.copy(os.path.join(COMFY_OUT, L[k]), os.path.join(a.out, L[k]))
        shutil.copy(os.path.join(COMFY_OUT, info_name), os.path.join(a.out, "layers.json"))
        n += len(info["layers"])
    print(f"完成 {time.time() - t0:.0f}s，{n} 张 → {a.out}")


if __name__ == "__main__":
    main()
