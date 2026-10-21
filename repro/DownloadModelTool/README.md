# DownloadModelTool

独立的模型下载工具。**不依赖工作流、不依赖工作台、不依赖 ComfyUI 服务**——只要能读写 ComfyUI 的 `models/` 目录。

工作流只是可选的一种「输入清单」；平时它就是 `get` 一个 URL。

## 用法

```sh
./run.command                       # 双击 = doctor（环境检查）
./run.command doctor                # python / hub / ComfyUI / 镜像 / 磁盘
./run.command get <HF URL>          # 下单个文件
./run.command get <repo> <repo内路径>
./run.command missing <workflow.json>   # 只看缺什么、从哪下
./run.command fill <workflow.json>      # 下载全部缺失项
./run.command list --filter qwen        # 搜 Manager 清单
```

例：

```sh
# 直接一个文件（repo 内带子目录的保持结构 → models/vae/xxx）
./run.command get https://hf-mirror.com/Comfy-Org/Qwen-Image-2.1/resolve/main/vae/qwen_image_2.1_vae_bf16.safetensors

# repo 根目录的权重默认落 models/checkpoints/
./run.command get cagliostrolab/animagine-xl-3.1 animagine-xl-3.1.safetensors
```

## 放哪里（重要）

| URL 形态 | 落地位置 |
|---|---|
| `.../resolve/main/vae/x.safetensors` | `models/vae/x.safetensors` |
| `.../resolve/main/text_encoders/x` | `models/text_encoders/x` |
| `.../resolve/main/x.safetensors`（repo 根） | `models/checkpoints/x` |
| 显式 `--to loras` | `models/loras/x` |

## 为什么不用 `hf` 命令 / Manager 的下载器

- 本机 ComfyUI 的 `hf` 可执行文件 shebang 指向打包机的路径，直接跑会 `bad interpreter`；
  所以这里统一用 **`huggingface_hub` 的 Python API**。
- Manager 的队列能入队、也会改写 URL，但它落在 `torchvision.datasets.utils.download_url`，
  实测在 `Comfy-Org/Qwen-Image-2.1` 上会挂住（队列 in_progress，几分钟零字节）。
- **必须 `HF_HUB_DISABLE_XET=1`**：hf-mirror 只代理元数据，大文件会 302 到
  `cas-bridge.xethub.hf.co`，国内常断。

## 三个下载源（自动选）

1. **直接 URL** —— 最明确，`get` 走这条；
2. **Manager 清单** —— `models` 字段里的 `filename/url/save_path`，500+ 条常见模型；
3. **工作流 note** —— 新版模板把 `huggingface.co/Comfy-Org/...` 的链接写在注释里，`missing`/`fill` 会读。

三条互不依赖；缺源时 `missing` 会标 `缺·无源`，用 `get` 手工补。

## 结构

```
dl.py            入口（python dl.py <子命令>）
run.command      双击 / 找带 huggingface_hub 的 python
dltool/
  config.py      找 ComfyUI 目录、镜像、磁盘
  sources.py     URL 解析 + Manager 清单 + 工作流扫描 + 本机已有文件
  fetch.py       hf_hub_download 封装（镜像 / 关 Xet / 重试）
  cli.py         子命令
```

## 与工作台的关系

`repro/studio` 的「补齐缺失模型」不再自己实现下载，只做两件事：扫工作流、把缺失项交给本工具
（`dl.py get <url>`），然后读进程输出显示进度。想单独用本工具、完全不碰工作台也可以。
