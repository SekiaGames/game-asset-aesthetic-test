"""按镜像下载单个模型文件到指定目录（不依赖 hugface_hub 的 CLI，也不依赖桌面 App 的设置）。

    <comfy-venv>/bin/python tools/fetch-model.py <repo_id> <filename> <target_dir>

关键点：
- HF_ENDPOINT 必须在 import huggingface_hub **之前**写进 os.environ，因为 constants.ENDPOINT
  是 import 时读一次。
- HF_HUB_DISABLE_XET=1：hf-mirror 会把大文件 302 到 cas-bridge.xethub.hf.co（Xet），
  那条链路在国内经常断；关掉后走普通 HTTP 路径。
- 中断后重跑同一条命令会续传（huggingface_hub 保留 .incomplete 分片）。
"""
import os
import sys

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)

from huggingface_hub import constants, hf_hub_download   # noqa: E402


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    repo, name, target = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(target, exist_ok=True)
    print(f"endpoint   {constants.ENDPOINT}")
    print(f"xet off    {os.environ.get('HF_HUB_DISABLE_XET') == '1'}")
    print(f"target     {target}")
    p = hf_hub_download(repo, name, local_dir=target)
    size = os.path.getsize(p) / (1024 ** 3)
    print(f"done       {p}  ({size:.2f} GB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
