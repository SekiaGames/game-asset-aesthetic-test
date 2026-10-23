# 项目长期记忆

## 运行环境（ComfyUI 出图）

- 硬件：Apple M4 Pro，**48 GB 统一内存**，macOS 26.6.2
- ComfyUI 由 **Comfy Desktop 1.1.7** 托管，安装实例 `inst-1792595779824`
  - 安装路径：`/Volumes/Data/Users/sekia/ComfyUI-Installs/ComfyUI`
  - 启动配置（含 launchArgs）：`~/Library/Application Support/Comfy Desktop/installations.json`
  - 改 launchArgs 前**必须先完全退出 Comfy Desktop**，否则会被覆盖
- 模型目录：`/Volumes/Data/Users/sekia/ComfyUI-Installs/ComfyUI/ComfyUI/models/`
  - diffusion_models：`qwen_image_2.1_int8_convrot.safetensors`(6.9G)、`minimax_h3_fl2va_pruned_int8_convrot.safetensors`(20G)
  - text_encoders：`qwen3vl_8b_int8_convrot`(8.9G)、`qwen3.5_9b_qwen_image_2.1_pe_t2i.int8_convrot`、`qwen3vl_32b_minimax_h3_nvfp4_awq`(15G)

## MPS 显存 OOM 的排查结论

Qwen Image 2.1 采样时报 `MPS backend out of memory`，崩溃在
`comfy/ldm/modules/sub_quadratic_attention.py` 的 `attn_scores.softmax(dim=-1)`。

根因链：
1. MPS 是统一内存且支持 over-commit，`get_free_memory()` 返回的空闲值虚高（远超 48 GB 物理内存）。
2. `attention_sub_quad` 的自适应逻辑（`for x in [4096,2048,1024,512,256]`）据此选中最大 chunk，
   并把 `kv_chunk_size` 设成 `k_tokens`，即 **KV 完全不分块**，走 `_get_attention_scores_no_kv_chunking` 快路径。
3. 于是 N×N 注意力分数矩阵被一次性实体化，单次 softmax 就要 2.91 GiB。

**重要陷阱**：不要照报错提示设 `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0`。
MPS 上限（63.65 GiB）本就大于物理内存 48 GB，解除上限只会加剧 swap，治不了本因。

解法优先级：
1. 换 attention 后端 —— launchArgs 加 `--use-pytorch-cross-attention`（SDPA，不实体化 N×N）。
   备选 `--use-split-cross-attention`。
2. 降低 token 数：降分辨率 / 减少参考图数量（Qwen Image 2.1 多图编辑的
   `ref_latents`/`image_slots` 每多一张，token 线性增长、attention 平方增长）。
3. VAE decode 用 tiled 节点。

验证是否生效：重启后日志应出现 `Using pytorch attention`
（原来是 `Using sub quadratic optimization for attention`）。

参考占用：text encoder 8.9 GB + diffusion 6.9 GB + VAE 0.64 GB ≈ 16.5 GB 常驻。
