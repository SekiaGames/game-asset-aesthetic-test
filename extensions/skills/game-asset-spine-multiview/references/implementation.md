# 代码与运行边界

需准备输入：先取得模型/层图/节点/服务，按脚本帮助提供输入。

所有命令从本技能 `assets/workspace/` 执行。Python 基础依赖见 requirements.txt；Blender 脚本在 Blender 自带 Python 中运行，不能 pip 安装 bpy 来替代。Node 脚本先按 package-lock.json 安装依赖。实际浏览器路径由 SPINE_RENDER_BROWSER 设置。

ComfyUI 使用 COMFYUI_DIR 指定含 models/custom_nodes/output 的目录；API 地址以脚本 --base/COMFYUI_URL 为准。推理类还需上游 torch/spandrel/节点环境；不自动安装权重或修改全局设置。示例工作目录由使用者在目标项目内选择，不把技能目录当唯一产物位置。

角色图、模型、动捕和旧阶段中间文件未附带。参数化头/身体脚本仍要求对应 output/part3d-test/... 数据树、对象命名与模板 pack，必须先调整输入/常数；只有方法和代码被整理，不承诺旧角色可在新环境完整重建。

| 附带代码 | 导出时适配 |
|---|---|
| [assets/workspace/scripts/dir-rig.py](../assets/workspace/scripts/dir-rig.py) | 示例命令/ComfyUI 默认目录改为可移植写法；算法不变。 |
| [assets/workspace/scripts/dst-demo-build.py](../assets/workspace/scripts/dst-demo-build.py) | 示例命令/ComfyUI 默认目录改为可移植写法；算法不变。 |
| [assets/workspace/scripts/dst-manifest.py](../assets/workspace/scripts/dst-manifest.py) | 示例命令/ComfyUI 默认目录改为可移植写法；算法不变。 |
| [assets/workspace/scripts/front-rig.py](../assets/workspace/scripts/front-rig.py) | 示例命令/ComfyUI 默认目录改为可移植写法；算法不变。 |
| [assets/workspace/scripts/mocap-to-vrm.py](../assets/workspace/scripts/mocap-to-vrm.py) | 示例命令/ComfyUI 默认目录改为可移植写法；算法不变。 |
| [assets/workspace/scripts/mocap-views.py](../assets/workspace/scripts/mocap-views.py) | 示例命令/ComfyUI 默认目录改为可移植写法；算法不变。 |
| [assets/workspace/scripts/seethrough-to-layers.py](../assets/workspace/scripts/seethrough-to-layers.py) | 示例命令/ComfyUI 默认目录改为可移植写法；算法不变。 |
| [assets/workspace/scripts/sheet-split.py](../assets/workspace/scripts/sheet-split.py) | 示例命令/ComfyUI 默认目录改为可移植写法；算法不变。 |
| [assets/workspace/scripts/spine-pack.py](../assets/workspace/scripts/spine-pack.py) | 示例命令/ComfyUI 默认目录改为可移植写法；算法不变。 |
| [assets/workspace/scripts/spine-verify.mjs](../assets/workspace/scripts/spine-verify.mjs) | 原项目代码；输入与角色假设见模块说明。 |
| [assets/workspace/scripts/upscale-anime.py](../assets/workspace/scripts/upscale-anime.py) | 示例命令/ComfyUI 默认目录改为可移植写法；算法不变。 |
| [assets/workspace/src/dst-demo/index.html](../assets/workspace/src/dst-demo/index.html) | 原项目代码；输入与角色假设见模块说明。 |
| [assets/workspace/src/dst-demo/main.js](../assets/workspace/src/dst-demo/main.js) | 原项目代码；输入与角色假设见模块说明。 |
| [assets/workspace/config/dir-view-prompts.json](../assets/workspace/config/dir-view-prompts.json) | 原项目代码；输入与角色假设见模块说明。 |
| [assets/workspace/config/run-pose-prompts.json](../assets/workspace/config/run-pose-prompts.json) | 原项目代码；输入与角色假设见模块说明。 |

来源文档只有路径和 SHA-256 留在 manifest，正文已人工提炼到 SKILL；不把旧绝对路径、用户资产或历史成功数字变成新环境验收。
