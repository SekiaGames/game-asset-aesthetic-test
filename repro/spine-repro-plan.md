# Spine 三条路线复现计划

> 基于仓库 `zeroa234/game-asset-aesthetic-test`（main @ 9c78c1e）的三个技能包：
> `game-asset-spine-cutout`、`game-asset-spine-portrait`、`game-asset-spine-multiview`。
> 本文只给"怎么把网友的操作重走一遍"，不含角色素材。

---

## 0. 先看结论

三条路线**不是并列难度**，而是有明显依赖和成本差：

| 路线 | 本质 | 需要 GPU | 需要的额外软件 | 复现难度 | 建议次序 |
|---|---|---|---|---|---|
| cutout（侧视切件） | 自己画/生成 6 件部件 → 脚本绑骨 → GIF/atlas | 不需要（只有"从视频拟合动作"才要 DWPose） | Python 环境、Node、可选 Godot | ★★ | **第 1** |
| portrait（正面立绘） | 一张立绘 → AI 语义拆层 → 网格转头/表情/物理 | 需要（See-through 推理） | ComfyUI + 节点 + 权重 + 超分 | ★★★★ | 第 2 |
| multiview（正/侧/背） | = portrait 拆层 ×3 + 三视图生成 + three.js 演示 | 需要（三次拆层） | 同 portrait，另加 Blender（动捕可选） | ★★★★★ | 第 3 |

**核心判断：先做 cutout。** 它把这类工作最贵的三个坑（部件是否完整、枢轴/遮挡层级、atlas 与运行时）全部暴露出来，而且脚本自带离线预览（`setup_pose.png`、每个动作的 `.gif`、`_sheet.png` 接触表），**不需要引擎、不需要 GPU 就能验收**。

同时必须接受一个前提：**这个仓库不是"clone 就能跑"的产品**，它整理的是方法 + 代码。角色图、模型权重、动捕、旧阶段中间产物都没有附带（见每包 `references/implementation.md` 第一段）。所以"复现"= 自己补齐输入 + 沿用代码和参数，不是执行示例。

---

## 1. 仓库怎么读（读对文件能省掉一半试错）

| 文件 | 作用 | 复现时的用法 |
|---|---|---|
| `SKILL.md` | 作者写的**结论式方法**：流程、检查项、失败经验 | 先读，它已经把"哪条路被否定"写死了 |
| `references/implementation.md` | **运行边界**：依赖、坐标系、哪些脚本只是"方法整理" | 动手前必读，避免把历史常数当通用值 |
| `references/sources.md` | 模型/节点/上游项目/许可入口 | 装环境时照这个清单找 |
| `references/manifest.json` | 每个代码文件的来源 + SHA-256 + 原文档路径 | 想追原作者原始报告时看这里 |
| `assets/workspace/` | 可运行代码 + 提示词 + ComfyUI 工作流 + 演示页 | 实际执行目录 |
| `docs/document-coverage.md` | 原项目文档清单与处置（哪些路线没发布） | 判断"哪些能力本来就没有" |

三个技能包里有一批**共享脚本**（`spine-pack.py`、`spine-verify.mjs`、`pose-extract.py`、`seethrough-to-layers.py`、`upscale-anime.py`、`front-rig.py`），内容一致。不要把它们当三份不同实现去对比。

---

## 2. 三条路线的真实数据流

### 2.1 cutout：绿幕部件 → 侧视骨骼

```
6 件绿幕部件图 (part_00..05)
  → spine-cutout-parts.py      色键(spill 差值) + 连通域 + 软边扩展 → parts/part_XX.png + parts.json
  → spine-cutout-rig.py        硬编码枢轴表 → <rig>.json + images/ + setup_pose.png + 每动作 .gif/_sheet.png
  → spine-pack.py              货架装箱 + bleed + Spine 4.x atlas + preview.html
  → spine-verify.mjs           官方 spine-core 4.2 加载，报 bones/slots/regions/缺失附件
  → (可选) spine-to-godot.py   Skeleton2D + AnimationPlayer + --check 定帧对照
```

可选增强（都不是必须）：

- `pose-extract.py`（DWPose）→ `pose-to-rig.py`：从循环视频拟合出 `run_video` 这类"真人动作"动画。
- `spine-cutout-rig.py --weapon`：加载 `katana-action.py`，程序化生成拔刀→回身→跳斩。
- `--skirt` + `skirt-measure.py`：把身体在腰带处切上下两段，裙摆做成权重网格 + 阻尼弹簧。

**关键实现细节（读代码才能发现）：**

- 只用到 `part_00`（头）、`part_01`（身）、`part_02`（手臂）、`part_04`（腿）；`03/05` 不读，远侧手脚是同一张图**压暗**（`c8c0c8ff`）后复用。
- 几何是**写死的像素常数**：`ELBOW_Y=150`、`KNEE_Y=50`、`THIGH_LEN=180`、`BELT=124`、`GROUND=621`（脚底在 body 图坐标系里的 y，不是身高）、枢轴表 `P` 全是测试角色 kurumi 的尺寸。
- `spine-cutout-parts.py` 按 `bbox ± 4px` 裁剪，所以模板枢轴常量实际对应**加了 4px 补边**的部件图；只要每个部件补边量一致，就是整体平移、相对关系不变。
- 切件排序键是 `(x // 50, y)` 而不是纯 y，部件并排摆放时顺序会被打乱，跑完必须核对 `parts.json`。
- 手/腿的"上段"是从单张图里裁出来再拉伸/插值补出来的（`leg-upper` 用 resize + 逐行重采样做锥度），所以原图比例不对时会露馅。

### 2.2 portrait：一张立绘 → 可演的正面骨骼

```
front.png (透明底)
  → 同画布图像编辑（config/front-edit-prompts-rgba.json：E1 空脸 / E2 闭眼 / E3 张嘴 / E4 笑脸 / G_* 手势）
  → See-through（config/workflows/see-through.json：layers→depth→postprocess→保存）
      · 可选头部高清补丁 config/patches/see-through-head-hires.patch
  → comfy-run-api.py --seethrough   把图层 + layers.json 从 ComfyUI output 拷回来
  → pose-extract.py                 DWPose → kp(18) + face(68) + hand(21)
  → seethrough-to-layers.py         还原同画布（预乘 alpha）、逐像素深度合并、去污染、表情层
                                     → layers/ + layers.json（含重合成误差指标）
  → front-rig.py                    DWPose + 包围盒定骨；贪心三角网格 + 多骨权重；
                                     aim_head/aim_eye/aim_body 视差；Spine 4.2 物理；表情插槽
  → spine-pack.py → spine-verify.mjs → preview.html
  → spine-video.py                  headless 渲染 + ffmpeg 拼演示片
```

**这条路线的"技术含量"集中在三处，其他都是胶水：**

1. **拆层还原**：See-through 输出的是"推理分辨率 + 补边"空间里的层，必须按 `9_00.png` 推回推理边长，再用**预乘 alpha** 放回原画布；深度图是**逐像素**合并依据（按整层中位深度排会把脖子盖成灰色）。
2. **头部形变**：`front-rig.py` 用 NX×NY 根格子骨骼铺在头部椭球面上，位移 ∝ 深度，做一阶球面转动近似；五官/刘海按不同比例吃 `aim_*` 的位移。**没有这层网格，"转头"就只是整块平移，眼睛会滑出脸。**
3. **重合成自检**：`seethrough-to-layers.py` 结束会打印 `mean_abs_err_fg / p99_fg / alpha_miss`，并写 `_recomp.png`。这是唯一能在进引擎前发现"缺层"的手段。

### 2.3 multiview：三方向 + 三维场景切换

```
front.png + 三栏留空画布 (sheet-split.py --make-input)
  → 图像编辑（config/dir-view-prompts.json 的 sheet_a）
  → sheet-split.py                等分栏 + 同一缩放 + 水平居中 + 脚底对齐 → front/side/back.png
  → See-through ×3 → seethrough-to-layers.py (poses = -)
  → dir-rig.py --view front|side|back --ref ...   → 三套同名同周期骨骼 + .rigmeta.json
  → spine-pack.py + spine-verify.mjs ×3
  → dst-manifest.py               三套路径 + 身高 + 速度（像素速度 ÷ 身高）
  → dst-demo-build.py             打成一个可发布目录 → three.js 演示
```

可选：`mocap-to-vrm.py`（Blender + VRM，CMU/Mixamo 重定向）→ `mocap-views.py`（同一动捕投到三台正交相机）→ `dir-rig.py --motion`；跑步关键姿势走 `run-pose-prompts.json` + `--run-pose/--run-pass/--run-fist`。

**演示页的切换逻辑在 `src/dst-demo/main.js`**，复现时最容易漏的三条：

- 按"角色朝向与镜头夹角"分扇区选 front/side/back，边界带**回差**（HYST），避免抖动；
- 侧面只画一套，另一边靠 `skeleton.scaleX = -1` 镜像；
- 切视角时**继承动画时间**；物理冲量取角色**真实位移**，并在切视角/镜像/转镜头时重置（否则原地转镜头会让头发猛甩）。

---

## 3. 复现顺序与验收门槛

```
P0 环境 + 最小闭环 ──► G0 运行时能加载
        │
        ▼
P1 cutout  ──────────► G1 setup pose 无裂缝 + 动作 GIF 合理 + verify 无 MISSING
        │
        ▼
P2 portrait ─────────► G2 重合成误差达标 + 转头/眨眼/口型成立
        │
        ▼
P3 multiview ────────► G3 三套同身高同脚底 + 绕场切换不跳
```

### G0 — 环境最小闭环（半天，零 GPU）　✅ 已完成 2026-10-21

目标不是出美术，而是确认 **Python → Spine JSON → atlas → 官方运行时** 这条链路在你机器上成立。做法：用一个最小的占位角色跑通 `spine-cutout-parts.py → spine-cutout-rig.py → spine-pack.py → spine-verify.mjs`。

通过标准：`spine-verify.mjs` 打印 `bones/slots/regions` 且**没有 `MISSING:`**。

实测结果见 [p0/P0-report.md](p0/P0-report.md)：12 bones / 10 slots / 6 regions，5 个动作全部 0 缺失，退出码 0；并用本机 Chrome 无头打开 `preview.html`，官方 spine-player 4.2 渲染正常。

### G1 — cutout（1–2 天）

- `setup_pose.png`：关节处无裂缝、无露底、描边连续、手脚层级正确（远侧压暗）。
- `idle/walk/run/wave/jump` 的 `.gif`：极限转角不裂、脚底不穿地、循环首末衔接。
- `spine-verify.mjs`：所有动作 0 MISSING，bounds 合理（不是 0×0）。
- `preview.html`：动作按钮都能播。

### G2 — portrait（3–7 天，取决于 GPU）

- `seethrough-to-layers.py` 打印：`mean_abs_err_fg` 约 ≤12/255、`alpha_miss` <1%，`_recomp.png` 目视无缺层。
- 原尺寸看头部/手腕/肩颈/发际线，1:1 像素检查边缘。
- 转头、眨眼、张嘴、手势之间过渡不穿帮。
- **进实际 app 才算完成**——作者明确说这条没做。

### G3 — multiview（2–4 天）

- 三张图同身高（作者实测 ±0.5%）、同地平线、脚底对齐。
- 侧面是真侧面、背面无五官；绕角色一圈不出现"同一视角两套骨骼打架"。
- 走/跑切视角时步幅、相位连续；镜像侧手不反关节。
- 站立原地转镜头时头发不猛甩（物理冲量是否接了真实位移）。

---

## 4. 逐路线操作清单

### 4.1 环境（一次做完）

```sh
# 三包都可独立携带；建议在仓库外建工作区，别把产物写进 skill 目录
export REPRO=~/spine-repro
mkdir -p $REPRO && cd $REPRO

# 以 cutout 为例（portrait/multiview 各自 workspace 各装一次）
cp -r <repo>/extensions/skills/game-asset-spine-cutout/assets/workspace ./cutout-ws
cd cutout-ws
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # numpy Pillow scipy opencv-python
npm install                                                          # @esotericsoftware/spine-core ~4.2
export SPINE_RENDER_BROWSER="/Volumes/Data/Users/sekia/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

注意：

- 脚本里写的是 `python -I`（隔离模式），换成 `.venv/bin/python -I` 即可，venv 的 site-packages 仍然生效。
- `pose-extract.py` **不能**加 `-I`，它要从 ComfyUI 安装目录 import `controlnet_aux`；用 `COMFYUI_DIR` 指路径。
- `spine-render.mjs` 默认浏览器路径是 Windows 的 Edge，**macOS 必须设 `SPINE_RENDER_BROWSER`**。
  本机 Chrome 不在 `/Applications`，实际路径是 `/Volumes/Data/Users/sekia/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`（版本 155）。
- `spine-video.py` 需要 `ffmpeg` 在 PATH（本机目前没有）。

### 4.2 cutout 步骤

1. **出部件图**（最关键，决定后面 80% 的效果）
   - 侧视、朝向一致（模板假定角色朝右，正向旋转 = 肢体向前摆）。
   - 6 件：头、身、整条手臂、整条腿（脚本自己切肘/膝）；远侧不用单独画。
   - 每件**包含被遮挡区域和自己的完整描边**，关节处留重叠区；不要用"原画颜色差分"切件，运动中必裂。
   - 纯绿背景、平光、无投影、无描边溢色；分辨率与原画一致。
2. **切件**
   ```sh
   .venv/bin/python -I scripts/spine-cutout-parts.py sheet.png parts --min-area 2000
   ```
   检查 `parts.json` 的排序（按 `x//50` 再按 y），**人工确认 00 是头**。顺序错了骨骼就全错。
3. **标定 —— 第一个真正的决策点**
   - 方案 A（快）：把部件缩放/排版到模板尺寸（脚底在 body 图坐标系 y≈621、人物总高约 730px、身体图腰带 y≈124、手臂图肘 y≈150、腿图膝 y≈50、大腿长 180）。
   - 方案 B（通用）：改 `spine-cutout-rig.py` 里的 `ELBOW_Y / KNEE_Y / THIGH_LEN / BELT`、`NECK/SH_*/HIP_JOINT_*/WAIST` 和 `P` 枢轴表。
   - 无论哪种，**每改一次就看 `setup_pose.png`**，那是唯一的廉价反馈。
4. **绑骨**
   ```sh
   .venv/bin/python -I scripts/spine-cutout-rig.py parts rig            # 基础动作
   .venv/bin/python -I scripts/spine-cutout-rig.py parts rig --skirt    # 加裙摆网格
   .venv/bin/python -I scripts/spine-cutout-rig.py parts rig --weapon parts_katana   # 加拔刀动作
   ```
   产物：`rig/images/`、`rig/setup_pose.png`、`rig/<anim>.gif`、`rig/<anim>_sheet.png`。
5. **打包 + 运行时校验**
   ```sh
   .venv/bin/python -I scripts/spine-pack.py rig --name mychar
   node scripts/spine-verify.mjs rig mychar
   open rig/preview.html
   ```
   `spine-pack.py` 默认 `filter:MipMapLinearLinear,Linear`（缩小时描线不断成虚线，代价是约 1/3 显存）；切成 `Linear,Linear` 可省显存。
6. **（可选）Godot**：`python -I scripts/spine-to-godot.py rig godot --check`，需要 Godot 4 打开 `check.tscn`。作者建议优先用官方 `spine-godot`（保留原生约束），自写 Skeleton2D 只是后备。
7. **（可选）视频拟合动作**
   ```sh
   .venv/bin/python scripts/pose-extract.py "frames/*.png" poses        # 不加 -I
   .venv/bin/python -I scripts/pose-to-rig.py loop.json rest.json run.json --name run_video --fps 24
   .venv/bin/python -I scripts/spine-cutout-rig.py parts rig run.json
   ```
   先看 `poses/overlay/*.png`：**侧视 DWPose 会互换左右**，先目视确认再谈拟合。不要把这套假设用在不对称攻击动作上。

### 4.3 portrait 步骤

前置：ComfyUI + `ComfyUI-See-through` 节点 + `models/SeeThrough/` 两个权重 + `comfyui_controlnet_aux` + `RealESRGAN_x4plus_anime_6B.pth`。

1. **准备 `front.png`**：透明底、正面、全身（或半身）、实际显示尺寸的量级（作者用 2K）。绿幕图先用 `key-unmix.py` 转 RGBA（它比 parts 里的简单色键好在会**去混色**，边缘不会变暗橄榄色）。
2. **表情/手势图**：按 `config/front-edit-prompts-rgba.json` 逐张同画布编辑，输出保持透明。核对三件事：画布尺寸一致、头部偏移 <0.5px、前景 IoU >0.99（作者历史值，按你的显示尺寸重定）。
3. **跑 See-through**：用 `config/workflows/see-through.json`，**先用现场 `/object_info` 校对节点输入**（注释里节点 ID 是本机注册名，旧模板不是跨版本契约）。起步：`resolution 1280 / seed 42 / steps 30`；`use_lama` 关（LaMa 权重会下到 C 盘缓存，改用 OpenCV 补洞）。
4. **头部高清（可选但强烈建议）**：先 `git apply --check` 确认补丁与当前节点版本兼容，再打补丁；第二遍只跑头部。**串行运行并核对 `latest.txt`**——背面/无脸可能不更新记录，别复制上一张脸。
5. **取回层**
   ```sh
   .venv/bin/python -I scripts/comfy-run-api.py wf.json out --image 1=front.png --seethrough
   ```
6. **DWPose**
   ```sh
   .venv/bin/python scripts/pose-extract.py "front.png" poses --on-white
   ```
   绿幕直接检测会 0 人（作者实测 1/1 图 0 人），必须做软合成到白底。
7. **重建层**
   ```sh
   .venv/bin/python -I scripts/seethrough-to-layers.py front.png out poses.json layers \
       --closed <E2 的 see-through 目录> --ah <E3> --happy <E4> --sr RealESRGAN_x4plus_anime_6B.pth
   ```
   看打印的 `recomposite` 指标 + `layers/_recomp.png`。缺裙子/头饰时：换种子或降分辨率重跑，然后**整层替换**——不要矢量化、不要用原图像素补。
8. **绑骨 + 打包 + 校验**
   ```sh
   .venv/bin/python -I scripts/front-rig.py layers rig --name mychar_front
   .venv/bin/python -I scripts/spine-pack.py rig --name mychar_front
   node scripts/spine-verify.mjs rig mychar_front
   ```
9. **（可选）演示视频**：`python -I scripts/spine-video.py layers rig out --name mychar_front`（需 ffmpeg）。
10. **（可选）参考模型拆解**：`node scripts/spine-inspect.mjs <skel> <atlas> out.json`，用来分析别人的立绘骨骼结构（作者就是靠它拆的 ryza 参考模型）。

### 4.4 multiview 步骤

1. **三视图必须一次生成**：
   ```sh
   .venv/bin/python -I scripts/sheet-split.py --make-input front.png sheet_a_in.png --panels 3
   ```
   然后用 `config/dir-view-prompts.json` 的 `sheet_a` 提示词把中/右两栏画出来。**不要用 3D 渲染打底**（`sheet_b` 实测被带偏：泡泡袖、头小、矮一截）；也**不要把正面图放进输入去单独转侧/背**（七轮失败，Qwen 编辑基本保留图 1 构图）。
2. **切栏**
   ```sh
   .venv/bin/python -I scripts/sheet-split.py sheet.png views --size 1696x2464 --height 2184 --ground 2316
   ```
   三张共用同一缩放倍数、同画布、水平居中、脚底对齐；清掉近透明 alpha 底噪。
3. **三次拆层**：同 portrait 的第 3–7 步，`poses` 传 `-`（没有正脸关键点）。每次核对本次 `head_hires`。
4. **三套骨骼**
   ```sh
   .venv/bin/python -I scripts/dir-rig.py views/front rig/front --view front --ref views/front/layers.json
   .venv/bin/python -I scripts/dir-rig.py views/side  rig/side  --view side  --ref views/front/layers.json
   .venv/bin/python -I scripts/dir-rig.py views/back  rig/back  --view back  --ref views/front/layers.json
   ```
   侧面默认 `--leg-mode dup`（两腿在轮廓里重叠，同一张腿图用两次、远侧压暗）；正/背面自动按两腿间透明缝分左右。
5. **打包 + 清单 + 演示**
   ```sh
   for v in front side back; do .venv/bin/python -I scripts/spine-pack.py rig/$v --name mychar_$v; node scripts/spine-verify.mjs rig/$v mychar_$v; done
   .venv/bin/python -I scripts/dst-manifest.py rig --name mychar
   .venv/bin/python -I scripts/dst-demo-build.py rig/manifest.json web
   python3 -m http.server -d web 8080
   ```
6. **（可选）动捕量级**：Blender + VRM Add-on 把 CMU/Mixamo 重定向到素体 → `mocap-views.py` 出三视角关节轨迹 → `dir-rig.py --motion walk=...`。这是唯一能让三套动作"几何上真的对应"的做法，但也是最重的一步，建议 G3 通过后再碰。

---

## 5. 本机现状（已实测）

| 项 | 状态 |
|---|---|
| 仓库 | 已 clone，`origin/main @ 9c78c1e`，本地只多一个 `.gitignore` 提交 |
| Node | v22.22.2 ✅（`spine-verify` 已验证可用） |
| Python | 3.13.12 ✅ venv 已建在 `~/.workbuddy/binaries/python/envs/spine-p0` |
| Python 依赖 | ✅ numpy 2.5.4 / Pillow 13.0.0 / scipy 1.18.1 / opencv-headless 4.10.0 |
| Node 依赖 | ✅ `repro/p0/ws` 已 `npm install --omit=dev`（spine-core 4.2） |
| 浏览器 | ✅ Chrome 155，在 `/Volumes/Data/Users/sekia/Applications/Google Chrome.app`（非标准路径，`/Applications` 下没有） |
| ffmpeg | ❌ 未安装（`spine-video.py`、GIF→mp4 会失败） |
| Blender | ❌ 未安装（动捕路线、`mocap-*.py` 全部不可用） |
| Spine 编辑器 | ❌ 未安装（不影响脚本路线；但要在编辑器里调动画必须有） |
| ComfyUI | ❌ 未找到（portrait/multiview 的拆层还没法跑） |

结论：**G0 已通过**（见 `p0/P0-report.md`）。下一步 P1 只差一张真实的侧视角色部件图；portrait 的拆层要先搭 ComfyUI。

---

## 6. 已知的坑（按踩中概率排序）

| 坑 | 现象 | 规避 |
|---|---|---|
| 把模板常数当通用值 | 新角色骨骼错位、肢体被拉长 | 先标定（方案 A/B），每步看 `setup_pose.png` |
| 部件顺序/命名错 | 头被当身体、动作全乱 | 人工核对 `parts.json`，别信自动排序 |
| 部件不含被遮挡区 | 大角度关节处裂缝 | 每件补全被遮挡区域 + 完整描边 + 关节重叠 |
| 边缘暗边 | 透明处混黑/混绿，轮廓出现深色小点 | `spine-pack.py` 的 bleed 已处理；别关掉 |
| See-through 缺层 | 少裙子/头饰，重合成 `alpha_miss` 升高 | 换 seed / 降分辨率重跑，整层替换 |
| 跨次推理比深度 | 两次结果的深度标尺不可比 | 深度只用于单次内部排序 |
| 头部高清串行假设 | 复制到上一张脸 | 核对 `latest.txt` 与本次记录 |
| DWPose 侧视左右互换 | 拟合出反关节 | 先看 overlay，或改用"近侧+半周期远侧"联合拟合 |
| 三视图生成回正面 | 侧/背和正面几乎一样 | 三栏留空一次性生成；不要塞正面图进单视角编辑 |
| 3D 底图带偏画风 | 头小、袖型变、矮一截 | 不要用形体不匹配的 3D 覆盖空栏 |
| 物理被镜头运动触发 | 原地转镜头时头发猛甩 | 冲量取真实位移，切视角/镜像/转镜头时重置 |
| Godot 整数轨道 | 整条旋转轨道被当整数 | 数字轨道写浮点（`0.0` 不是 `0`） |
| 许可 | 商用集成被卡 | Spine 运行时授权、See-through 权重条款分别看；Genielabs 的 skill 是 PolyForm Noncommercial，代码不能抄 |

---

## 7. 建议的 MVP 定义

不要一上来追求"进游戏"。按下面三个 MVP 递进，每个都有明确停止条件：

- **MVP-A（cutout，本周可完成）**：自己的角色 → 6 件切件 → `idle/walk/run` 三个 GIF + `preview.html` + `spine-verify` 零 MISSING。**做到这里你已经掌握了这套工作流 80% 的实操。**
- **MVP-B（portrait）**：正面立绘 → 完整分层（`alpha_miss` <1%）→ 转视线 + 眨眼 + 张嘴 + 一个手势 → 30fps 演示片。**进 app 不算在内。**
- **MVP-C（multiview）**：三方向 + 同一套走路相位 → three.js 绕场切换不跳 → 一个可分享的静态目录。

如果最终目的只是"给游戏做 2D 角色"，**MVP-A 就是终点**；portrait 适合对话立绘/看板娘，multiview 只适合饥荒式"2D 角色 + 3D 场景"。

---

## 8. 下一步（今天）

1. 建 venv、装 cutout 的 Python 依赖，`npm install`，设 `SPINE_RENDER_BROWSER`。
2. 拿任意一张角色侧视图切 6 件（或先用一张简单占位图），跑通 G0 最小闭环，确认 `spine-verify` 无 MISSING。
3. 再决定标定走方案 A 还是 B——这一步决定后面是"改图"还是"改代码"。
