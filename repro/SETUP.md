# 环境安装清单（macOS）

本机实测：**Apple M4 Pro / 48 GB 统一内存 / macOS 26.6.2 / Homebrew 已装 / `/Volumes/Data` 余 159 GB**。
以下按「哪条路线需要」分组，标了必须与可选。

---

## 0. 先说结论：P1 要不要等 ComfyUI

**不用等。** cutout 路线（P1）**完全不碰 ComfyUI**——只有「视频 → DWPose → 动作拟合」这一支才用，
而肩颈那条缝、裙摆物理、Godot 导出，都不需要任何新软件。

所以顺序是：

```
现在（零安装）  → 修肩颈 / 加 --skirt / 可选 Godot
之后（装 ComfyUI）→ P2 正面立绘拆层
再后（装 Blender）→ P3 多方向 + 动捕
```

---

## 1. 立刻装（几分钟，后面都用得上）

| 软件 | 用途 | 命令 | 必需 |
|---|---|---|---|
| ffmpeg | `spine-video.py` 拼视频、GIF↔mp4、抽帧 | `brew install ffmpeg` | 是（P2 起） |
| Godot 4 | `spine-to-godot.py --check` 引擎侧验收 | `brew install --cask godot` | 可选 |
| Chrome | 已装（`/Volumes/Data/Users/sekia/Applications/Google Chrome.app`） | — | 已有 |

---

## 2. P2：ComfyUI + See-through（必须）

### 2.1 软件

| 项 | 说明 | 必须 |
|---|---|---|
| Python 3.12 | ComfyUI 生态兼容性最好（3.13 也能跑，但部分节点轮子还没跟上） | 是 |
| ComfyUI | 主程序 | 是 |
| ComfyUI-Manager | 装/更新节点方便（强烈建议） | 建议 |
| ComfyUI-See-through | 语义拆层节点，工作流见 `config/workflows/see-through.json`（参考版本 0.5.0） | 是 |
| comfyui_controlnet_aux | DWPose 节点（`pose-extract.py` 直接从它 import） | 是 |
| huggingface_hub | 拉权重 | 是 |

```sh
brew install python@3.12
mkdir -p ~/ai && cd ~/ai
git clone https://github.com/Comfy-Org/ComfyUI.git
cd ComfyUI
python3.12 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt

cd custom_nodes
git clone https://github.com/Comfy-Org/ComfyUI-Manager.git
git clone https://github.com/jtydhr88/ComfyUI-See-through.git
git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git
cd .. && for d in ComfyUI-See-through comfyui_controlnet_aux; do
  [ -f custom_nodes/$d/requirements.txt ] && .venv/bin/pip install -r custom_nodes/$d/requirements.txt
done
.venv/bin/pip install -U "huggingface_hub[cli]"
```

### 2.2 权重（数 GB，预留 20–30 GB）

| 权重 | 放哪里 | 来源 |
|---|---|---|
| `seethroughv0.0.2_layerdiff3d` | `models/SeeThrough/` | `hf download layerdifforg/seethroughv0.0.2_layerdiff3d --local-dir models/SeeThrough/seethroughv0.0.2_layerdiff3d` |
| `seethroughv0.0.1_marigold`（深度） | `models/SeeThrough/` | `hf download layerdifforg/seethroughv0.0.1_marigold --local-dir models/SeeThrough/seethroughv0.0.1_marigold` |
| `RealESRGAN_x4plus_anime_6B.pth` | `models/upscale_models/` | xinntao/Real-ESRGAN 的 Releases |
| See-through 节点自己声明的底模 | 按其 README | **不要凭猜测放**，先看节点 README |

工作流里 `use_lama: false`，所以**不用装 LaMa**。

### 2.3 验证（三步，别跳）

```sh
# ① 服务起来了
cd ~/ai/ComfyUI && .venv/bin/python main.py --port 8188
curl -s http://127.0.0.1:8188/system_stats | head -c 200

# ② 节点真的注册了（工作流里的节点 ID 是本机注册名，必须先核对）
curl -s http://127.0.0.1:8188/object_info \
  | .venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print([k for k in d if 'SeeThrough' in k])"

# ③ 脚本认得这个目录
export COMFYUI_DIR=$HOME/ai/ComfyUI
python scripts/pose-extract.py "某张正面图.png" /tmp/poses --on-white   # 要能出 poses.json
```

`COMFYUI_DIR` 必须指向**含 `models/ custom_nodes/ output/` 的那一层**——`pose-extract.py`、`upscale-anime.py`、
`comfy-run-api.py` 都从它推路径。

---

## 3. P3：Blender + 动捕（P2 通过后再装）

| 项 | 用途 | 命令 / 来源 | 必须 |
|---|---|---|---|
| Blender 4.x | 动捕重定向、三视角投影 | `brew install --cask blender` | 仅动捕路线 |
| VRM Add-on | 导入导出 VRM | https://github.com/saturday06/VRM-Addon-for-Blender | 仅动捕路线 |
| CMU Motion Capture | 免费动捕数据 | http://mocap.cs.cmu.edu/ | 仅动捕路线 |
| three.js / spine-threejs | 演示页，`npm install` 已声明固定版本 | 仓库 `package.json`（three 0.184 / spine-threejs 4.2.120） | P3 演示需要 |

仓库脚本注释写的是 **Blender 5.2**，VRM 插件对新版 Blender 的兼容性要现查——装完先确认插件能启用再往下走。

---

## 4. 可选但有价值

| 软件 | 用途 | 备注 |
|---|---|---|
| Spine 编辑器 | 手调关键帧、看枢轴、导出二进制 | 付费；脚本路线不需要，但**要在编辑器里精修就必须有** |
| Godot 4 | 引擎侧验收 | 官方 `spine-godot` 保真度高于自写 Skeleton2D |

---

## 5. 版本与许可

- **Spine 运行时固定 4.2 系列**：包里的 JSON 是 `spine: 4.2.43`，编辑器/运行时版本要匹配。
- 生成 JSON 不代表拿到运行时授权，商用要看 [Spine Runtimes License](https://esotericsoftware.com/spine-runtimes-license)。
- See-through 的**代码许可 ≠ 权重许可**，两个分别看。
- `GenielabsOpenSource/spine-animation-ai` 是 PolyForm Noncommercial 1.0.0，只能读思路，不能抄代码进商用项目。

---

## 6. M4 Pro 能不能跑 See-through

作者的数字来自 NVIDIA 机器，仓库自己也写了「8GB 显卡可行性只是从更大显卡峰值推测，不是实测」。到 M 系列上有两个未知：

1. **算子支持**：LayerDiff3D / marigold 这类扩散模型在 MPS 上可能遇到不支持的算子，会退回 CPU（极慢）或直接报错。
2. **速度**：1280 分辨率、30 步，就算能跑，单张也可能要几分钟到十几分钟。

建议顺序：**先用最高 1024 分辨率、低步数跑通一遍**，确认能出层再看质量。
如果 MPS 不行，两条退路：

- `comfy-run-api.py --base http://<远程GPU>:8188` 把推理放远端；
- 但 `--seethrough` 会从**本地** `COMFYUI_DIR/output` 拷图层，远端跑时这一步要手动把层和 `layers.json` 拿回来。

48 GB 统一内存对显存不构成瓶颈，瓶颈在算子和速度，不在容量。

---

## 7. 建议的安装顺序

- [ ] `brew install ffmpeg`
- [ ] （可选）`brew install --cask godot`
- [ ] `brew install python@3.12`
- [ ] ComfyUI + Manager + 两个节点
- [ ] 三个权重放进 `models/`（名字和下拉框对得上）
- [ ] `/object_info` 里能看到 `SeeThrough_*`
- [ ] `COMFYUI_DIR` 设好，`pose-extract.py` 能出 `poses.json`
- [ ] （P3 再装）Blender + VRM 插件

---

## 8. 模型下载（国内网络，实测）

桌面版 ComfyUI 的「中国镜像」开关**只影响它自己的元数据请求**，实测那个 venv 里
`huggingface_hub.constants.ENDPOINT` 仍是 `https://huggingface.co`。所以下载失败有两层原因：

1. **`HF_ENDPOINT` 没进到那个进程**：GUI 启动的 App 不读 `.zshrc`。
2. **Xet**：hf-mirror 只代理元数据，大文件被 302 到 `cas-bridge.xethub.hf.co`，那条链路在国内经常断。

另外这台机器的 `hf` 命令是坏的——shebang 指向构建机的
`/Users/runner/work/ComfyUI-Standalone-Environments/.../python3`，直接执行会报 `bad interpreter`。
所以别用 `hf download`，改用 venv 的 python 调 API：

```sh
C=/Volumes/Data/Users/sekia/ComfyUI-Installs/ComfyUI
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1

$C/standalone-env/bin/python - <<'PY'
from huggingface_hub import hf_hub_download
p = hf_hub_download(
    "cagliostrolab/animagine-xl-3.1",
    "animagine-xl-3.1.safetensors",
    local_dir="/Volumes/Data/Users/sekia/ComfyUI-Installs/ComfyUI/ComfyUI/models/checkpoints",
)
print(p)
PY
```

验证：

```sh
curl -s http://127.0.0.1:8188/object_info \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['CheckpointLoaderSimple']['input']['required']['ckpt_name'][0])"
```

要全局生效（给桌面 App 用）：`launchctl setenv HF_ENDPOINT https://hf-mirror.com` +
`launchctl setenv HF_HUB_DISABLE_XET 1`，然后**完全退出并重启 App**。
注意 `launchctl setenv` 重启电脑后失效，要长期生效得写 LaunchAgent plist。

已知细节：

- `HF_HUB_ENABLE_HF_TRANSFER=1` 先别开，hf_transfer 在镜像上更容易失败。
- 中断后重跑同一条命令会续传；若卡在 `.incomplete`，删掉 `local_dir/.cache` 里对应文件再下。
- 单文件 checkpoint（6.9 GB）比 diffusers 目录结构省事，ComfyUI 直接认。

---

## 9. 日志在哪（下载失败时按这个顺序查）

| 位置 | 内容 |
|---|---|
| `~/Library/Logs/Comfy Desktop/app.log` | 桌面 App 主进程 + 后端 stdout 的合流，出错先看这里 |
| `<install>/logs/comfyui.log` | 后端当前日志（轮转，带 `[INFO]/[ERROR]` 前缀） |
| `<install>/ComfyUI/user/comfyui.log` | 后端日志的另一份（`comfyui.prev*.log` 是历史） |
| DevTools Console | **前端**报错只在这里：菜单 View → Toggle Developer Tools |

判断故障层：

- 日志里出现 `model_url replaced by HF_ENDPOINT` → 说明 Manager 走了镜像，失败是**某个具体模型**
  的 URL 有问题（403 gated、非 HF 源、404）。
- 出现 `[ComfyUI-Manager] Failed to download: <url> / <错误>` → 那条 url 就是元凶，单独换源。
- **日志里什么都没有，只有界面弹「下载失败」** → 那次点击根本没进后端，是桌面前端自己的下载器；
  只能去 DevTools Console 看。绕开方式见下。

Manager 的队列是显式启动的，手动验证一条链路：

```sh
curl -X POST http://127.0.0.1:8188/v2/manager/queue/install_model \
  -H 'Content-Type: application/json' \
  -d '{"client_id":"diag","ui_id":"diag-1","name":"probe","type":"upscale",
       "url":"https://huggingface.co/<repo>/resolve/main/<file>",
       "filename":"probe.bin","save_path":"upscale_models"}'
curl -X POST http://127.0.0.1:8188/v2/manager/queue/start
curl http://127.0.0.1:8188/v2/manager/queue/status
```
