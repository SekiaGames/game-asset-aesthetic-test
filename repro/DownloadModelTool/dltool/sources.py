"""从三种来源解析「某个模型文件该从哪下、放到哪个子目录」：

1. 直接给 HF URL（最明确）
2. Manager 的 model-list 缓存（有 500+ 条常见模型）
3. 工作流 JSON（新版模板会把 Comfy-Org 的 resolve/main 链接写进 note）

三条路都不依赖对方；工作流只是「顺带能读」的一种输入，不是必需。
"""
import json
import os
import re

MODEL_EXT = ("safetensors", "ckpt", "pt", "pth", "bin", "onnx", "gguf", "sft")
NAME_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._+\-]*\.(?:%s))" % "|".join(MODEL_EXT), re.I)
URL_RE = re.compile(r"https?://[^\s\"'()\\]+\.(?:%s)" % "|".join(MODEL_EXT), re.I)


def parse_url(url):
    """https://<host>/<org>/<repo>/resolve/<rev>/<sub>/<file> -> (repo, path)"""
    if "/resolve/" not in url:
        return None, None
    base, rest = url.split("/resolve/", 1)
    parts = [p for p in base.split("/") if p]
    if len(parts) < 4:
        return None, None
    repo = "/".join(parts[-2:])
    bits = rest.split("/", 1)
    if len(bits) != 2 or not bits[1]:
        return None, None
    return repo, bits[1]


def subdir_of(path, fallback="checkpoints"):
    """repo 内路径的第一个目录就是 ComfyUI 的 models 子目录。"""
    parts = path.split("/")
    return parts[0] if len(parts) > 1 else fallback


def manager_index(comfy):
    """filename(小写) -> Manager 条目"""
    idx = {}
    for p in os.listdir(os.path.join(comfy, "user", "__manager", "cache")) if os.path.isdir(
            os.path.join(comfy, "user", "__manager", "cache")) else []:
        if not p.endswith("_model-list.json"):
            continue
        try:
            data = json.load(open(os.path.join(comfy, "user", "__manager", "cache", p), encoding="utf-8"))
        except Exception:                                       # noqa: BLE001
            continue
        for e in data.get("models") or []:
            fn = (e.get("filename") or "").lower()
            if fn and fn not in idx:
                idx[fn] = e
    return idx


def local_files(models):
    """models/ 下已有文件的 basename（小写）→ 绝对路径"""
    out = {}
    for dp, dirs, fs in os.walk(models):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in fs:
            out.setdefault(f.lower(), os.path.join(dp, f))
    return out


def from_workflow(path):
    """工作流里出现的模型文件名，以及它自带的下载 URL。"""
    raw = open(path, encoding="utf-8").read()
    names = sorted({m.group(1) for m in NAME_RE.finditer(raw)})
    urls = {}
    for m in URL_RE.finditer(raw):
        u = m.group(0)
        urls.setdefault(u.rsplit("/", 1)[-1].lower(), u)
    return names, urls


def resolve(comfy, filename, urls=None, endpoint="https://huggingface.co"):
    """返回 {filename, url, repo, path, subdir, source, size}"""
    low = filename.lower()
    urls = urls or {}

    e = manager_index(comfy).get(low)
    if e and e.get("url"):
        u = e["url"].replace("https://huggingface.co", endpoint)
        repo, path = parse_url(u)
        if repo:
            sp = e.get("save_path") or ""
            sub = sp.split("/")[0] if sp and sp != "default" and not sp.startswith("custom_nodes") else subdir_of(path)
            return {"filename": filename, "url": u, "repo": repo, "path": path,
                    "subdir": sub, "source": "manager", "size": e.get("size")}

    u = urls.get(low)
    if u:
        u = u.replace("https://huggingface.co", endpoint)
        repo, path = parse_url(u)
        if repo:
            return {"filename": filename, "url": u, "repo": repo, "path": path,
                    "subdir": subdir_of(path), "source": "workflow", "size": None}

    return {"filename": filename, "url": None, "repo": None, "path": None,
            "subdir": None, "source": None, "size": None}
