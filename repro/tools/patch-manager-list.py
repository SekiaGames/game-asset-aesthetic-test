"""把 ComfyUI-Manager 缓存里的模型清单从 huggingface.co 改写到 hf-mirror.com。

为什么需要：Manager 的「下载缺失模型」读的是 model-list.json 里的**硬编码 URL**
（本机 516 条指向 huggingface.co）。HF_ENDPOINT 只影响 huggingface_hub 库，
不会改写这些 URL，所以设了环境变量也没用。

    python tools/patch-manager-list.py [ComfyUI 目录]

- 只改缓存文件，不动 Manager 代码；原文件留 .bak
- Manager 拉不到新清单（raw.githubusercontent.com 被重置）时会一直用这份缓存，
  所以改完重启 App 即生效；哪天它成功刷新了，重跑本脚本即可
- 顺带报告 channel_url 和 github.com 的条数（后者仍可能不通）
"""
import glob
import json
import os
import sys

SRC = "https://huggingface.co"
DST = "https://hf-mirror.com"


def find_comfy(arg):
    cands = [arg] if arg else []
    cands += [
        os.environ.get("COMFYUI_DIR"),
        "/Volumes/Data/Users/sekia/ComfyUI-Installs/ComfyUI/ComfyUI",
        os.path.expanduser("~/ComfyUI-Installs/ComfyUI/ComfyUI"),
        os.path.expanduser("~/ComfyUI"),
    ]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, "user", "__manager")):
            return c
    raise SystemExit("找不到 ComfyUI 目录（需含 user/__manager）")


def main():
    root = find_comfy(sys.argv[1] if len(sys.argv) > 1 else None)
    print("ComfyUI  ", root)
    files = sorted(glob.glob(os.path.join(root, "user", "__manager", "cache", "*_model-list.json")))
    if not files:
        print("没有缓存清单；先在 App 里打开一次 Manager 让它拉取（失败也会留缓存）")
        return 1
    for p in files:
        raw = open(p, encoding="utf-8").read()
        n = raw.count(SRC)
        bak = p + ".bak"
        if not os.path.exists(bak):
            open(bak, "w", encoding="utf-8").write(raw)
        if n:
            open(p, "w", encoding="utf-8").write(raw.replace(SRC, DST))
        d = json.loads(open(p, encoding="utf-8").read())
        models = d.get("models") or []
        hosts = {}
        for m in models:
            u = m.get("url") or ""
            if isinstance(u, str) and u.startswith("http"):
                h = u.split("/")[2]
                hosts[h] = hosts.get(h, 0) + 1
        print(f"{os.path.basename(p)}: 改写 {n} 条 → 现在 {hosts}")
    cfg = os.path.join(root, "user", "__manager", "config.ini")
    if os.path.isfile(cfg):
        for line in open(cfg, encoding="utf-8"):
            if "channel_url" in line:
                print("channel_url:", line.strip(), "  ← raw.githubusercontent.com 被墙时它永远刷新失败，"
                      "但缓存仍可用")
    print("\n下一步：完全退出 ComfyUI 再启动，然后重试「下载缺失模型」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
