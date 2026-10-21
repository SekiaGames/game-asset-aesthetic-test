"""路径与环境解析：所有「ComfyUI 在哪 / 镜像用哪个」的判断都收在这里。"""
import glob
import os

DEFAULT_ENDPOINT = "https://hf-mirror.com"

GUESSES = [
    os.environ.get("COMFYUI_DIR"),
    os.path.expanduser("~/ComfyUI"),
    "/Volumes/Data/Users/sekia/ComfyUI-Installs/ComfyUI/ComfyUI",
    os.path.expanduser("~/ComfyUI-Installs/ComfyUI/ComfyUI"),
    os.path.expanduser("~/Documents/ComfyUI"),
]


def comfy_dir(explicit=None):
    """返回含 models/ 的 ComfyUI 目录；找不到返回 None。"""
    for d in [explicit] + GUESSES:
        if d and os.path.isdir(os.path.join(d, "models")):
            return os.path.abspath(d)
    return None


def models_dir(comfy):
    return os.path.join(comfy, "models")


def endpoint(explicit=None):
    return (explicit or os.environ.get("HF_ENDPOINT") or DEFAULT_ENDPOINT).rstrip("/")


def workflows(comfy):
    wd = os.path.join(comfy, "user", "default", "workflows")
    out = []
    for p in glob.glob(os.path.join(wd, "**", "*.json"), recursive=True):
        out.append((os.path.getmtime(p), p))
    return [p for _, p in sorted(out, reverse=True)]


def manager_lists(comfy):
    return sorted(glob.glob(os.path.join(comfy, "user", "__manager", "cache", "*_model-list.json")))


def free_gb(path):
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / 1024 ** 3
