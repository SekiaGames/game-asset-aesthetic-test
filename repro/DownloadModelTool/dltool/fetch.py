"""真正下载的一层：hf_hub_download + 镜像 + 关掉 Xet + 重试。

为什么必须关 Xet：hf-mirror 只代理元数据，大文件会 302 到 cas-bridge.xethub.hf.co，
那条链路在国内经常直接断。关掉后走普通 HTTP 路径。
"""
import json
import os
import time
import urllib.request


def _prepare(endpoint):
    os.environ["HF_ENDPOINT"] = endpoint
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)
    try:                      # constants 在 import 时就固化了 ENDPOINT，光设环境变量不够
        from huggingface_hub import constants
        constants.ENDPOINT = endpoint
    except Exception:                                          # noqa: BLE001
        pass


def repo_files(endpoint, repo, revision="main", timeout=30):
    """列出 repo 里的文件：[(path, size_bytes)]。走镜像的 /api/models 接口。"""
    url = f"{endpoint}/api/models/{repo}?blobs=true&revision={revision}"
    req = urllib.request.Request(url, headers={"User-Agent": "dltool/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    out = []
    for s in d.get("siblings") or []:
        name = s.get("rfilename")
        if not name or name == ".gitattributes":
            continue
        out.append((name, int(s.get("size") or 0)))
    return out


def resolve_url(endpoint, repo, path, revision="main"):
    """单文件的镜像直链。"""
    return f"{endpoint}/{repo}/resolve/{revision}/{path}"


def snapshot(endpoint, repo, dest, revision="main", ignore=(".gitattributes",), retries=2):
    """整仓下载（diffusers 目录结构必须这样下，单文件方式拿不到 model_index.json 之类）。"""
    _prepare(endpoint)
    from huggingface_hub import snapshot_download

    os.makedirs(dest, exist_ok=True)
    last = None
    for attempt in range(1, retries + 1):
        try:
            kw = dict(repo_id=repo, local_dir=dest, revision=revision,
                      ignore_patterns=list(ignore), max_workers=2)
            try:
                return snapshot_download(endpoint=endpoint, **kw)
            except TypeError:                                  # 老版本没有 endpoint 参数
                return snapshot_download(**kw)
        except Exception as e:                                  # noqa: BLE001
            last = e
            if attempt < retries:
                print(f"  第 {attempt} 次失败：{e}；{5 * attempt}s 后重试")
                time.sleep(5 * attempt)
    raise last


def download(endpoint, repo, path, models_root, to=None, retries=3, quiet=False):
    """下到 <models_root>/<path>（保持 repo 内的子目录结构）。返回最终路径。"""
    _prepare(endpoint)
    from huggingface_hub import hf_hub_download

    dest_dir = os.path.join(models_root, to) if to else models_root
    os.makedirs(dest_dir, exist_ok=True)
    last = None
    for attempt in range(1, retries + 1):
        try:
            if to:
                tmp = os.path.join(models_root, ".dl-tmp")
                p = hf_hub_download(repo, path, local_dir=tmp, endpoint=endpoint)
                dest = os.path.join(dest_dir, os.path.basename(path))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                os.replace(p, dest)
                return dest
            return hf_hub_download(repo, path, local_dir=models_root, endpoint=endpoint)
        except Exception as e:                                  # noqa: BLE001
            last = e
            if attempt < retries:
                if not quiet:
                    print(f"  第 {attempt} 次失败：{e}；{2 * attempt}s 后重试")
                time.sleep(2 * attempt)
    raise last
