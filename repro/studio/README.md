# 本地工作台

把流水线每一步、环境自检和产物预览放在一个本地页面里。**零第三方依赖**，只用 Python 标准库。

## 启动

```sh
cd repro
./studio/run.command                 # 或者：
PORT=8765 <venv>/bin/python studio/server.py
```

打开 http://127.0.0.1:8765

环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `PORT` | 8765 | 页面端口 |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | ComfyUI 地址；远端也能指 |
| `COMFYUI_DIR` | 自动猜 | 含 `models/ custom_nodes/ output/` 的那一层 |

## 它做什么 / 不做什么

做：

- **环境自检**：ComfyUI 服务、底模数量、See-through 节点、DWPose 节点、spine-core、ffmpeg。
  缺哪项就直接写在对应步骤上（例如「缺底模」），不用去猜为什么跑不动。
- **按步执行**：每步一条命令，日志实时流回页面（SSE），失败带退出码。
- **产物预览**：`art/clean`、`exploded.png`、`setup_pose.png`、`idle.gif`、`*_sheet.png`、
  atlas 与 `preview.html`，点开即看。

不做：

- **不重做 ComfyUI 的图编辑界面**。文生图 / 分件仍然在 ComfyUI 里搭工作流，这里只负责编排和看结果。
- **不接管脚本逻辑**。所有步骤在终端里都能原样跑；页面只是把命令和产物对上。

## 当前接线状态

| 步骤 | 状态 |
|---|---|
| ① 文生图 | 待接（需要 ComfyUI 有底模） |
| ② 分件生成 | 待接（需要底模 + See-through 节点） |
| ③ 清理 + 测量 | 已接 `p1/measure.py` |
| ④ 标定 + 拼件 | 已接 `p1/compose.py` |
| ⑤ 绑骨 | 已接 `p1/ws-rig/spine-cutout-rig.py`（含 kurumi.json → mint.json） |
| ⑥ 打包 atlas | 已接 `ws-rig/spine-pack.py` |
| ⑦ 运行时校验 | 已接 `p0/ws/scripts/spine-verify.mjs` |

## 接 ① 的思路（等底模到位）

1. 在 ComfyUI 里搭一条最小文生图（`CheckpointLoaderSimple → CLIPTextEncode ×2 → EmptyLatentImage → KSampler → VAEDecode → SaveImage`），导出 **API 格式**。
2. 存成 `studio/flows/t2i.json`，把节点里的正/负提示词、分辨率、seed 抽成 `--set` 参数。
3. 在 `server.py` 的 `steps()` 里给 `t2i` 填 `cmd`：调 `comfy-run-api.py`，产物落到 `p1/art/t2i/`。
4. 页面就会自动从「缺底模」变成可点。

**不要**把节点 ID 写死——工作流里的 `class_type` 名字以现场 `/object_info` 为准。
