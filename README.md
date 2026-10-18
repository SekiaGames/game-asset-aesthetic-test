<p align="center">
  <img src="docs/assets/banner.svg" alt="Game Art Skill Library：像素精灵、骨骼动画、方块角色与讲解配音" width="1280" />
</p>

<h1 align="center">游戏美术 · 通用 Agent Skills</h1>

<p align="center">
  从一张角色图，到像素精灵、Spine 骨骼动画和方块角色。<br />
  把实际项目里走通的方法、代码和踩坑经验，整理成可以独立携带的技能。
</p>

<p align="center">
  <a href="#-技能导航"><img alt="8 skills" src="https://img.shields.io/badge/Skills-8-75e8c5?style=flat-square&amp;labelColor=17212d" /></a>
  <a href="reports/validation-2026-10-18.json"><img alt="6 offline checks" src="https://img.shields.io/badge/Offline_checks-6-93b7ff?style=flat-square&amp;labelColor=17212d" /></a>
  <img alt="SFW content" src="https://img.shields.io/badge/Content-SFW-bca2f8?style=flat-square&amp;labelColor=17212d" />
  <img alt="Chinese documentation" src="https://img.shields.io/badge/Docs-中文-f0b480?style=flat-square&amp;labelColor=17212d" />
  <a href="https://github.com/zeroa234/game-asset-aesthetic-test/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/zeroa234/game-asset-aesthetic-test?style=flat-square&amp;labelColor=17212d&amp;color=9aacc3" /></a>
</p>

<p align="center">
  <a href="#-效果预览">效果预览</a> ·
  <a href="#-视频讲解">视频讲解</a> ·
  <a href="#-技能导航">浏览技能</a> ·
  <a href="#-开始使用">开始使用</a> ·
  <a href="reports/validation-2026-10-18.json">验证记录</a> ·
  <a href="https://github.com/zeroa234/game-asset-aesthetic-test/archive/refs/heads/main.zip">下载完整仓库</a>
</p>

---

## ✨ 这里有什么

**8 个独立技能，覆盖三类工作：** 2D 像素精灵与 Spine 骨骼、方块角色、讲解配音。可以只挑一条路线，也可以把生成、绑定、检查串起来用。

| 🧭 方法 | 🧰 代码 | 🔎 证据 |
|---|---|---|
| 输入、步骤、关键决策与失败经验 | 按路线附带脚本、配置和依赖说明 | 原始文档来源、代码哈希与实际验证范围 |

技能里保留了**已验证、失败和待验证**的区别，运行时物理和游戏集成分别写明做到了哪一步。

## 🎬 效果预览

下面都是项目实测时的输出（缩小、压缩后的截图和动图），点图片进入对应技能。

<table>
  <tr>
    <td align="center" valign="top" width="33%">
      <a href="extensions/skills/game-asset-video-sprites/SKILL.md"><img src="docs/assets/gallery/sprite-run.gif" width="260" alt="像素精灵跑步循环" /></a><br />
      <sub><b>视频 → 像素精灵</b><br />35×65 像素 · 16 色 · 16 帧循环（4 倍放大）</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <a href="extensions/skills/game-asset-spine-cutout/SKILL.md"><img src="docs/assets/gallery/spine-katana.gif" width="260" alt="切件骨骼拔刀跳斩动作" /></a><br />
      <sub><b>切件骨骼 · 复杂动作</b><br />拔刀 → 回身 → 跳斩，Spine 4.2</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <a href="extensions/skills/game-asset-spine-portrait/SKILL.md"><img src="docs/assets/gallery/spine-portrait.gif" width="260" alt="立绘拆层后的眨眼与说话" /></a><br />
      <sub><b>一张立绘 → 骨骼动画</b><br />拆层 + 头部网格形变：眨眼、说话</sub>
    </td>
  </tr>
  <tr>
    <td align="center" valign="top" colspan="2">
      <a href="extensions/skills/game-asset-spine-multiview/SKILL.md"><img src="docs/assets/gallery/spine-multiview.gif" width="360" alt="三套 Spine 在 3D 场景中按方向切换" /></a><br />
      <sub><b>正 / 侧 / 背三套 Spine</b><br />在 three.js 场景里按角色朝向与镜头夹角切换</sub>
    </td>
    <td align="center" valign="top">
      <a href="extensions/skills/game-asset-blocky-hair/SKILL.md"><img src="docs/assets/gallery/blocky-hair.gif" width="150" alt="方块角色发型环绕展示" /></a><br />
      <sub><b>方块角色 · 发型</b><br />主发束与配饰，环绕一周</sub>
    </td>
  </tr>
  <tr>
    <td align="center" valign="top" colspan="2">
      <a href="extensions/skills/game-asset-blocky-character/SKILL.md"><img src="docs/assets/gallery/blocky-lineup.jpg" width="420" alt="比例模板做出的三个方块角色" /></a><br />
      <sub><b>比例模板 → 方块角色</b><br />旋转方块、普通服装与逐面像素 UV</sub>
    </td>
    <td align="center" valign="top">
      <a href="extensions/skills/game-asset-blocky-qa/SKILL.md"><img src="docs/assets/gallery/blocky-qa.jpg" width="200" alt="共面闪烁修复前后对照" /></a><br />
      <sub><b>共面闪烁：先定位再修</b><br />上：两块侧盖同平面，红色为闪烁像素<br />下：合并成一层后消失</sub>
    </td>
  </tr>
</table>

## 📺 视频讲解

这些路线的实测过程做成了 B 站视频，点封面观看。

<table>
  <tr>
    <td align="center" valign="top" width="33%">
      <a href="https://www.bilibili.com/video/BV1mXHy6cEWy/"><img src="docs/assets/gallery/cover-ep1.jpg" width="300" alt="第 1 期封面：AI 做像素动画" /></a><br />
      <sub><b>01 · AI 做像素动画</b><br />视频帧路线与切件骨骼路线</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <a href="https://www.bilibili.com/video/BV1sopt67EJQ/"><img src="docs/assets/gallery/cover-ep2.jpg" width="300" alt="第 2 期封面：让 OC 动起来" /></a><br />
      <sub><b>02 · 让 OC 动起来</b><br />一张图 → 拆部件 → 骨骼与表情 → 进游戏</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <a href="https://www.bilibili.com/video/BV1TsJB6uEut/"><img src="docs/assets/gallery/cover-ep3.jpg" width="300" alt="第 3 期封面：AI 像素建模" /></a><br />
      <sub><b>03 · AI 像素建模</b><br />方块模板、自动检查与穿衣物理</sub>
    </td>
  </tr>
</table>

## 🗺️ 路线总览

![8 个技能的路线关系：2D 与 Spine、方块角色，以及两条路线都能用的 TTS 讲解配音](docs/assets/routes.svg)

<sub>图中为路线示意。各路线所需模型、插件与其他技能，从对应包的资源来源页获取。</sub>

## 🧩 技能导航

### 🎞️ 2D · 像素精灵与 Spine

| 你想完成的工作 | Skill |
|---|---|
| 视频动作 → 循环像素精灵；高清色键、共享裁切、锁色与拼表 | [game-asset-video-sprites](extensions/skills/game-asset-video-sprites/SKILL.md) |
| 侧视部件 → 骨骼动画；姿态拟合、武器握点与 Godot 检查 | [game-asset-spine-cutout](extensions/skills/game-asset-spine-cutout/SKILL.md) |
| 正面立绘 → 完整拆层、网格转头、表情与二次运动 | [game-asset-spine-portrait](extensions/skills/game-asset-spine-portrait/SKILL.md) |
| 正 / 侧 / 背多套 Spine → 三维场景中的方向切换 | [game-asset-spine-multiview](extensions/skills/game-asset-spine-multiview/SKILL.md) |

### ⛏️ Blockbench · 方块角色

| 你想完成的工作 | Skill |
|---|---|
| 社区比例 → 旋转方块、普通服装与逐面像素 UV | [game-asset-blocky-character](extensions/skills/game-asset-blocky-character/SKILL.md) |
| 原画发型 → 主发束、配饰、内层露出与动态避让 | [game-asset-blocky-hair](extensions/skills/game-asset-blocky-hair/SKILL.md) |
| 模型检查 → 共面闪烁、镜像、接缝与动态边界 | [game-asset-blocky-qa](extensions/skills/game-asset-blocky-qa/SKILL.md) |

### 🎙️ TTS · 普通讲解配音

| 你想完成的工作 | Skill |
|---|---|
| 虚构音色 → 批量候选、中文识别质检、韵律与段落衔接 | [game-asset-tts-narration](extensions/skills/game-asset-tts-narration/SKILL.md) |

## 🚀 开始使用

**1 · 获取仓库**

```sh
git clone https://github.com/zeroa234/game-asset-aesthetic-test.git
```

**2 · 挑选一个完整技能目录**

从 `extensions/skills/` 中复制所需目录到你的 Agent 支持的 skills 位置。保留整个目录，入口、参考和代码一起携带。

**3 · 给 Agent 一项具体任务**

例如，安装像素精灵技能后：

```text
使用 $game-asset-video-sprites，
把我的角色跑步视频做成 64px 高、12fps 的循环精灵表。
先检查循环区间、轮廓漂移和调色板，再输出 RGBA 帧与精灵表。
```

尚未安装时，也可以让 Agent 直接读取所选目录的 `SKILL.md`。运行配套代码前，先读该包的 `references/implementation.md`，再按实际路线准备环境和输入。

<details>
<summary><strong>📦 一个技能包里有什么？</strong></summary>

```text
game-asset-<route>/
├── SKILL.md                       何时使用、流程、检查与已知限制
├── references/
│   ├── sources.md                 模型、插件、其他技能的获取来源
│   ├── implementation.md          依赖、输入约定和代码适配说明
│   └── manifest.json              来源与代码 SHA-256
└── assets/workspace/              配套脚本、配置与必要依赖清单
```

各技能可独立携带，配套代码不依赖兄弟技能。图像层、角色模型、权重和第三方插件由使用者根据来源页另行准备；部分路线提供可运行 CLI，部分需要角色适配或原阶段中间输入。

</details>

## ✅ 验证与使用边界

截至 **2026-10-18**，8 个技能入口通过结构校验，完成 6 组离线检查。徽章对应这份实测记录，不代表持续运行的 CI。

| 检查 | 实际验证的内容 |
|---|---|
| 🎨 精灵后处理 | 锁色、二值透明度、循环首末与拼表 |
| 🧱 方块模板 | 普通着装示例的原版 / 导出版 spec 回归与图集 |
| 📐 共面修复 | 缺陷正例能检出，修复后再次检查 |
| 🦴 Spine | 图集与合成骨骼由官方 4.2 运行时加载 |
| 🎙️ TTS 客户端 | 本地模拟 API、候选记录、失败退出与中文 CER |
| 🧾 JavaScript | 附带脚本的语法检查 |

完整记录见 [验证报告](reports/validation-2026-10-18.json)，输入文档处置见 [覆盖清单](docs/document-coverage.md)。每包的 `manifest.json` 记录附带代码的来源、哈希及适配项。

> **适用边界**：本次未重新运行 GPU 模型或试听音色。部分路线的代码需要角色适配或原阶段的中间输入；导出几何或物理描述，也不等于完成目标游戏内验收。

## 🔗 工具与资源

路线中会用到 **FFmpeg · ComfyUI · Spine · Godot · three.js · Blender · Blockbench · Qwen3-TTS · Fish Speech** 等工具。具体选型、模型文件和他人的技能入口，均写在各包的 `references/sources.md`，并区分本次核对与历史来源。

本仓库聚焦普通游戏美术与讲解内容，不附带 NSFW 资源、模型权重或角色源文件。效果预览和视频封面只用于展示效果，图中角色是测试用的二次创作形象，版权归各自权利人，不随本仓库授权，也不作为可复用素材。项目代码与上游资源未被统一重新授权；插件、权重、角色和运行时分别按各自条款使用。

---

<p align="center">
  <strong>从试验出发，带着方法继续做。</strong><br />
  <sub>Game Art Skill Library · 8 routes · code, sources &amp; evidence</sub>
</p>
