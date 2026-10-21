# P0 最小闭环报告（G0 已通过）

日期：2026-10-21　目标：确认「Python → Spine JSON → atlas → 官方运行时」这条链路在本机成立。
用**合成占位角色**跑，不涉及美术资源。

## 结论

**G0 通过。** 官方 `spine-core` 4.2 能加载生成的骨骼与图集，5 个动作全部无缺失附件，`spine-verify` 退出码 0：

```
bones 12, slots 10, regions 6
setup           bounds x=-105 y=-4 w=210 h=751
idle     2.00s  bounds x=-104 y=-4 w=210 h=753
walk     1.00s  bounds x=-177 y=7 w=296 h=744
run      0.60s  bounds x=-307 y=62 w=615 h=680
jump     1.20s  bounds x=-134 y=-16 w=256 h=750
wave     1.60s  bounds x=-116 y=-4 w=373 h=756
```

产物：`setup_pose.png`、`idle/walk/run/jump/wave.gif`、`*_sheet.png`（6 帧接触表）、`p0dummy.json`
（86KB）、`p0dummy.atlas`、`p0dummy.png`（512×512，6 regions）、`preview.html`、
`preview-shot.png`（官方 spine-player 在 Chrome 里的实际渲染截图）。

## 一次性命令

**双击 `run.command`**（macOS 会用 Terminal 打开，跑完等回车关窗），或在命令行：

```sh
cd repro/p0
./run.command       # 生成占位图 → 切件 → 绑骨 → 打包 → 校验，约 30 秒
```

可选环境变量：`PY=` 指定解释器、`NODE=` 指定 node、`NO_PAUSE=1` 结束后不等待、
`NO_OPEN=1` 成功后不自动打开 setup pose、`OPEN_PREVIEW=1` 改为在浏览器里打开 `preview.html`。

```
repro/p0/
├── run.command         一键复现（双击即可）
├── art/make-sheet.py   合成部件图（按模板常量画，含 bbox==画布的自检）
├── art/sheet.png       196×1722 绿幕部件图
├── ws/                 从 skill 复制的 workspace（未改一行代码，不入库）
└── out/
    ├── parts/          part_00..05 + parts.json
    └── rig/            骨骼 JSON / atlas / 图集 / GIF / preview.html
```

## 环境实况

| 项 | 结果 |
|---|---|
| Python | 3.13.12（managed），venv 在 `~/.workbuddy/binaries/python/envs/spine-p0` |
| numpy / Pillow / scipy | 2.5.4 / 13.0.0 / 1.18.1 |
| opencv | **4.10.0 headless**（见下方偏差 1） |
| Node | 22.22.2，`npm install --omit=dev` 只装 `@esotericsoftware/spine-core@4.2.x`（4 秒） |
| 浏览器 | Chrome 155，在 **`/Volumes/Data/Users/sekia/Applications/Google Chrome.app`**（非标准路径），已用它渲染 `preview.html` |
| ffmpeg / Blender / ComfyUI | 仍然没有（不影响 P0） |

**两处偏差（必须记下来）：**

1. **opencv 换成了 headless 版。** `requirements.txt` 写的是 `opencv-python`，但它的 wheel 有 48MB，
   本机到 `files.pythonhosted.org` 只有约 40KB/s，pip 反复被拖死。改用阿里云镜像直连下载
   wheel（2.5MB/s）+ 本地安装 `opencv-python-headless==4.10.0.84`。脚本只用到 `morphologyEx /
   connectedComponentsWithStats / dilate`，headless 版完全够用。
2. **骨骼 JSON 被改名。** `spine-cutout-rig.py` 把输出名写死成 `kurumi.json`（没有 `--name`），
   而 `spine-pack.py` 要求 `<rig>/<name>.json`。所以 `run.sh` 里多了一步 `mv kurumi.json p0dummy.json`，
   或者干脆 `--name kurumi`。

## 真跑一遍才发现的四个坑

这些是读代码不一定能看出来、动手就会撞上的：

### 1. `spine-cutout-parts.py` 的 `--pad 4` 会让所有枢轴整体偏移 4px

它按 `bbox ± 4px` 裁剪，每张部件图的四周都多出 4px 透明边。模板里的枢轴常量（head 83,128 /
arm 35,25 / leg 30,8 …）是按裁剪后的图标的，所以内容实际落点比设计值偏 (+4,+4)。
**只要每个部件的补边量相同，这 4px 是整体平移，相对关系不变**——本次实测正是如此，无需改常量。
但如果某个部件贴着母版边缘，`max(x-4, 0)` 会把一侧的补边裁掉 → 只有它偏 4px → 关节错位。
**真实素材排版时，每个部件四周都要留足 4px 以上空白。**

### 2. 切件顺序的排序键是 `(x // 50, y)`，不是纯 y

`comps.sort(key=lambda i: (stats[i, 0] // 50, stats[i, 1]))`。部件并排放在一起时，
x 落入不同 50px 桶，顺序会先按列再按行，`00` 未必是头。
本次把 6 个部件**竖排、左边缘对齐在同一个 x**，才保证顺序 = 自上而下。
真实素材（并排的手臂/腿）很容易踩这个坑，跑完必须核对 `parts.json`。

### 3. 只用 4 张部件图，`03/05` 是废文件

`spine-cutout-rig.py` 只读 `part_00/01/02/04`，远侧手脚是同一张图压暗（`c8c0c8ff`）复用。
所以母版里给远侧单独画的图不会被用到——画了也白画（但顺序位仍要占住）。

### 4. 合成角色的"错位"多数是模板假设，不是管线错误

模板的 body 图宽 176、腰枢轴在 x=78，也就是**身体相对腰线是偏前的**（前方 98px、后方 78px）。
我按对称画的占位身体，渲染出来就显得比头偏后 10px，手臂压在裙子中间。这是占位图的造型问题，
骨架放置逻辑本身是对的（`setup_pose.png` 里 12 骨骼 / 10 插槽全部按预期挂上）。

## 浏览器渲染（已补上）

用本机 Chrome 155 无头跑官方 `spine-player` 4.2 打开 `preview.html`，图集、骨骼、动作按钮全部正常，
截图见 `out/rig/preview-shot.png`。命令（Chrome 在非标准路径，且我的沙箱里要加 `--no-sandbox`）：

```sh
CHROME="/Volumes/Data/Users/sekia/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless=new --no-sandbox --disable-gpu-sandbox \
  --user-data-dir=/tmp/chrome-p0 --window-size=620,940 \
  --use-angle=swiftshader --enable-unsafe-swiftshader --virtual-time-budget=15000 \
  --screenshot=out/rig/preview-shot.png \
  "file://$PWD/out/rig/preview.html"
```

这也顺带确认了 `spine-pack.py` 的 **bleed + atlas 格式**在官方播放器里没问题（轮廓没有黑边/绿边）。
`SPINE_RENDER_BROWSER` 后续就填上面这个 Chrome 路径。

## G0 没有证明的事

- **引擎集成**：Godot 的 `spine-to-godot.py --check` 没跑（没装 Godot）。
- **`spine-render.mjs`**：那是 portrait 包里逐帧渲染的工具，需要 `playwright-core` + `spine-webgl`，本次没装。
- **美术质量与标定**：占位图不涉及"部件是否含被遮挡区、描边是否连续、枢轴是否对准关节"这些真正的难点。
- **视频动作拟合**：`pose-extract.py` 需要 ComfyUI 的 controlnet_aux，未跑。

## 下一步（P1 的第一天）

1. 拿一张真实的侧视角色图，按 6 件切开（含被遮挡区、完整描边、关节留重叠），排版时**竖排同 x、四周留 8px 空白**。
2. 跑 `run.command` 的同一条链路，先看 `setup_pose.png`：关节是否对得上、描边是否连续。
3. 对不上时再决定标定方案 A（把部件缩放到模板尺寸）还是 B（改 `ELBOW_Y / KNEE_Y / THIGH_LEN / BELT` 与枢轴表）。
