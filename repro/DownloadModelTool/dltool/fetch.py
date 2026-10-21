"""真正下载的一层：hf_hub_download + 镜像 + 关掉 Xet + 重试。

为什么必须关 Xet：hf-mirror 只代理元数据，大文件会 302 到 cas-bridge.xethub.hf.co，
那条链路在国内经常直接断。关掉后走普通 HTTP 路径。
"""
import os
import time


def _prepare(endpoint):
    os.environ["HF_ENDPOINT"] = endpoint
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)


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
