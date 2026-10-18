# 代码与运行边界

需准备输入：先取得模型/层图/节点/服务，按脚本帮助提供输入。

所有命令从本技能 `assets/workspace/` 执行。Python 基础依赖见 requirements.txt；Blender 脚本在 Blender 自带 Python 中运行，不能 pip 安装 bpy 来替代。Node 脚本先按 package-lock.json 安装依赖。实际浏览器路径由 SPINE_RENDER_BROWSER 设置。

ComfyUI 使用 COMFYUI_DIR 指定含 models/custom_nodes/output 的目录；API 地址以脚本 --base/COMFYUI_URL 为准。推理类还需上游 torch/spandrel/节点环境；不自动安装权重或修改全局设置。示例工作目录由使用者在目标项目内选择，不把技能目录当唯一产物位置。

角色图、模型、动捕和旧阶段中间文件未附带。参数化头/身体脚本仍要求对应 output/part3d-test/... 数据树、对象命名与模板 pack，必须先调整输入/常数；只有方法和代码被整理，不承诺旧角色可在新环境完整重建。

| 附带代码 | 导出时适配 |
|---|---|
| [assets/workspace/src/tts_batch.py](../assets/workspace/src/tts_batch.py) | 默认台本改普通讲解样例；保留 API 协议，批量请求失败后返回非零退出码，避免假成功。 |
| [assets/workspace/src/script_parse.py](../assets/workspace/src/script_parse.py) | 原项目代码；输入与角色假设见模块说明。 |
| [assets/workspace/src/voice_design.py](../assets/workspace/src/voice_design.py) | 音色描述/参考文本换成普通教程，路径可由环境变量设置。 |
| [assets/workspace/src/qc.py](../assets/workspace/src/qc.py) | 重写通用质检说明，删除原场景举例；ASR 路径可配置。 |
| [assets/workspace/src/prosody.py](../assets/workspace/src/prosody.py) | 原项目代码；输入与角色假设见模块说明。 |
| [assets/workspace/src/spk_sim.py](../assets/workspace/src/spk_sim.py) | 重写通用质检说明，删除原场景举例；ASR 路径可配置。 |

TTS_MODELS_DIR 设置 VoiceDesign 模型根目录；TTS_VOICE_OUTPUT 设置音色候选输出；TTS_ASR_MODEL 设置 SenseVoice 本地模型。Fish API 服务默认本地 8080，通过 --url 指向实际地址。ASR/VoiceDesign/服务端通常使用各自上游环境，不能假定一个 requirements 文件解决所有 GPU 版本。

原项目通用声纹比较脚本附带供扩展，其模型须按 FunASR 官方模型入口配置。没有附带原始参考声线或脚本，也不包含后台服务安装/系统配置修改。

来源文档只有路径和 SHA-256 留在 manifest，正文已人工提炼到 SKILL；不把旧绝对路径、用户资产或历史成功数字变成新环境验收。
