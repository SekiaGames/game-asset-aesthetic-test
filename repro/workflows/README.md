# 工作流文件：为什么打不开，以及怎么打开

## 报错

把作者仓库里的 `extensions/skills/game-asset-spine-portrait/assets/workspace/config/workflows/see-through.json`
拖进 ComfyUI，报：

```
由于重新加载工作流数据出错，加载被中止
TypeError: e is not iterable
```

## 原因：那份是 API 格式，不是画布格式

ComfyUI 有两种 JSON，长得完全不一样：

| 格式 | 结构 | 谁用 |
|---|---|---|
| **API**（`/prompt` 用） | `{"1": {"class_type": "LoadImage", "inputs": {...}}, "2": ...}` | `comfy-run-api.py`、服务端接口 |
| **UI**（画布用） | `{"nodes": [ {id, type, pos, widgets_values, ...} ], "links": [[id, src, slot, dst, slot, type]], "version": 0.4}` | 浏览器前端拖拽 / 保存 |

前端拿到 API 格式后去迭代 `data.nodes`（undefined）→ `TypeError: e is not iterable`。
作者那份的注释也写得很清楚，它是配 `seethrough_psd_info.log` 的**服务端**流程，
本来就是给 `comfy-run-api.py --seethrough` 用的，不是给人拖进画布的。

## 解法：用官方 UI 版套作者的参数

ComfyUI-See-through 仓库自己带了两份 UI 格式工作流：

```
workflows/seethrough-basic.json          ← 本目录引用的骨架
workflows/seethrough-layer-editor.json
```

`tools/make-seethrough-ui.py` 以 `seethrough-basic.json` 为骨架（widget 顺序天然正确），
套上作者 API 文件里的数值，并补上作者多出来的 `JoinImageWithAlpha` 与层预览：

```sh
cd repro
python3 tools/make-seethrough-ui.py --install
```

产出 `workflows/see-through.ui.json`，并拷到
`<ComfyUI>/user/default/workflows/see-through.ui.json`（前端侧栏可直接打开）。

参数映射：

| 作者 API 文件 | 本文件 |
|---|---|
| `GenerateLayers(seed=42, resolution=1280, num_inference_steps=30)` | 同值，control_after_generate 设 `fixed` |
| `GenerateDepth(seed=42, resolution_depth=-1)` | 同值，`fixed` |
| `PostProcess(tblr_split=true, use_lama=false)` | 同值（官方默认 `use_lama=true`，必须改） |
| `SavePSD(filename_prefix="seethrough_kurumi")` | 同值 |
| `JoinImageWithAlpha`（作者有，官方没有） | 保留：LoadImage 的 IMAGE+MASK 合回 RGBA 再进 GenerateLayers |
| `SaveImage(images=[5,1])` | 换成 `PreviewImage` 挂在 GenerateLayers 的 preview 上，少写文件 |
| `LoadLayerDiffModel(model="seethroughv0.0.2_layerdiff3d")` | 改成 `layerdifforg/seethroughv0.0.2_layerdiff3d`（HF repo id） |

最后一条是**必须改**的：0.5.0 的 `model` 接受 HF repo id 或 `models/SeeThrough/` 下的目录名。
作者用的是短名 + `auto_download=false`，只有本机目录正好叫那个名字时才成立；换成 repo id 才不会误判。

## 已做的安装（2026-10-22）

| 项 | 状态 |
|---|---|
| 节点包 | `custom_nodes/ComfyUI-See-through`（0.5.0，commit `98d754b`） |
| Python 依赖 | diffusers 0.40 / accelerate / peft / scikit-learn / matplotlib / opencv-python-headless（hub 锁在 1.30，不动 ComfyUI 原有环境） |
| 重启后注册 | 7 个节点：LoadLayerDiffModel / LoadDepthModel / GenerateLayers / GenerateDepth / PostProcess / SavePSD / PartsToLayers |
| 安装前环境快照 | `repro/comfy/venv-freeze-before-seethrough.txt`（要回滚就按它卸） |
| 模型 | 已下：`models/SeeThrough/seethroughv0.0.2_layerdiff3d`（9.5 GB）、`.../seethroughv0.0.1_marigold`（3.1 GB） |

模型是 diffusers 目录结构，**不能按单文件下**（`DownloadModelTool get` 只处理单文件，
拿不到 `model_index.json` 等流水线定义）：

| repo | 体积 | 落地 |
|---|---|---|
| `layerdifforg/seethroughv0.0.2_layerdiff3d` | 9.46 GB（24 文件） | `models/SeeThrough/seethroughv0.0.2_layerdiff3d/` |
| `layerdifforg/seethroughv0.0.1_marigold` | 3.05 GB（16 文件） | `models/SeeThrough/seethroughv0.0.1_marigold/` |

```sh
cd repro/DownloadModelTool
./run.command snapshot layerdifforg/seethroughv0.0.2_layerdiff3d --list   # 只打印镜像直链
./run.command snapshot layerdifforg/seethroughv0.0.2_layerdiff3d          # 实际下载
```

完整直链清单在 [`seethrough-model-urls.txt`](seethrough-model-urls.txt)（39 个文件）。
每个 URL 形如 `https://hf-mirror.com/<repo>/resolve/main/<path>`，支持 Range（实测 206，约 2.1 MB/s）。

## 第二个坑：模型加载时去拉 juggernaut（已修）

格式修好、模型下完之后，`SeeThrough_LoadLayerDiffModel` 又报：

```
OSError: frankjoshua/juggernautXL_version6Rundiffusion does not appear to have a file named scheduler_config.json
```

不是模型没下全，是**节点代码写死了远程 repo**：

```python
# see-through/common/modules/layerdiffuse/diffusers_kdiffusion_sdxl.py:120
if scheduler is None:                      # nodes.py 传的就是 None
    model_id = "frankjoshua/juggernautXL_version6Rundiffusion"
    scheduler = DPMSolverMultistepScheduler.from_pretrained(model_id, subfolder="scheduler", ...)
```

作者机器上那个 repo 在 HF 缓存里，所以没暴露；新机器必然走网络，镜像抖一下就炸。

而本地模型目录自带一份**完全等价**的配置（`scheduler/scheduler_config.json`：
`DPMSolverMultistepScheduler`、`algorithm_type=sde-dpmsolver++`、`final_sigmas_type=zero`、
SDXL betas 0.00085/0.012）。所以补丁改成从本地读，`scheduler` 不是 `None` 了，
那个分支就绕过：

```sh
cd <ComfyUI>/custom_nodes/ComfyUI-See-through
git apply /path/to/repro/patches/seethrough-local-scheduler.patch
```

补丁：[`../patches/seethrough-local-scheduler.patch`](../patches/seethrough-local-scheduler.patch)。
改完重启后端，日志应出现 `[SeeThrough] Scheduler from local model dir (no juggernaut fetch)`。

## 验证到哪一步（诚实版）

| 检查 | 结果 |
|---|---|
| 节点真的注册了 | ✅ 重启后 `/object_info` 有 7 个 `SeeThrough_*`，总节点数 995 → 1002 |
| 节点模块能 import | ✅ 独立进程加载，打印 `Loaded 7 nodes` |
| widget 顺序与实测定义一致 | ✅ 对照 `/object_info` 逐个核过（含 `control_after_generate` 位置、SavePSD 的两个按钮值） |
| JSON 结构自检 | ✅ `make-seethrough-ui.py` 内置断言：id 唯一、link 两端登记一致 |
| **在画布里真打开一次** | ❌ 没做。`tools/check-workflow-load.mjs` 想用 headless Chrome 的 CDP 调 `app.loadGraphData` 实测，但本机环境的透明代理拦掉了到 `127.0.0.1:9xxx` 的 WebSocket 握手（`non-101`），跑不通 |

所以「能加载」这件事是**按官方骨架 + 实测节点定义推出来的**，不是亲眼看见的。
打开时若还报错，把控制台报错发我，那说明是节点定义与骨架版本不符。
