"""透明图层动漫超分（spandrel 直接加载 ComfyUI models/upscale_models 里的模型，不经 ComfyUI 服务）。

    python -I scripts/upscale-anime.py <in.png> <out.png> \
        --model RealESRGAN_x4plus_anime_6B.pth [--out-scale 2.1] [--alpha bicubic|model]

用途：See-through 的层是「结构对、线条软」的重画结果（报告 §16.6：细节只有原图一半左右），
放到原图画布前先用动漫超分把线条恢复锐利，再缩放到目标尺寸。
模型（2026-10-09 从官方来源下载）：Real-ESRGAN x4plus_anime_6B（xinntao 官方 release）、APISR 4x GRL / 2x RRDB（作者 release）、
Real-CUGAN up2x conservative / no-denoise（bilibili/ailab 官方 release 的 updated_weights.zip）。
透明处理同 upscale-layers.py：RGB 先把 α<0.5 的像素填成最近不透明像素的颜色（bleed），α 默认 bicubic 放大（平滑），
也可当灰度图交给模型。缩放都在预乘 alpha 下做。分块推理（重叠 32px）避免显存不够。
推理部分用 spandrel（ComfyUI 自带依赖）；bleed / 分块 / 透明处理是自写的胶水。
"""
import argparse
import os

import numpy as np
import torch
import spandrel
from PIL import Image
from scipy import ndimage

COMFY = os.environ.get("COMFYUI_DIR", "ComfyUI")  # ComfyUI 目录（含 custom_nodes / models / output）
MODEL_DIR = os.path.join(COMFY, "models/upscale_models")
_cache = {}


def load(name):
    if name not in _cache:
        p = name if os.path.isfile(name) else os.path.join(MODEL_DIR, name)
        m = spandrel.ModelLoader().load_from_file(p)
        m.cuda().eval()
        if m.supports_half:
            m.half()
        _cache[name] = m
    return _cache[name]


def bleed_rgb(rgb, alpha):
    solid = alpha >= 128
    if solid.all() or not solid.any():
        return rgb
    _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
    return np.where(solid[..., None], rgb, rgb[iy, ix])


@torch.inference_mode()
def run_model(m, img3, tile=384, pad=32):
    """img3: HxWx3 uint8 → (H·s)x(W·s)x3 float32 0..1，分块推理、重叠区丢弃。"""
    s = m.scale
    H, W = img3.shape[:2]
    x = torch.from_numpy(img3).permute(2, 0, 1)[None].float().div(255).cuda()
    if m.supports_half:
        x = x.half()
    out = torch.zeros((1, 3, H * s, W * s), dtype=torch.float32, device="cuda")
    for y0 in range(0, H, tile):
        for x0 in range(0, W, tile):
            y1, x1 = min(y0 + tile, H), min(x0 + tile, W)
            ya, xa = max(y0 - pad, 0), max(x0 - pad, 0)
            yb, xb = min(y1 + pad, H), min(x1 + pad, W)
            patch = x[:, :, ya:yb, xa:xb]
            # 部分架构要求宽高是某数的倍数：反射补边后裁回
            ph, pw = (-patch.shape[2]) % 8, (-patch.shape[3]) % 8
            if ph or pw:
                patch = torch.nn.functional.pad(patch, (0, pw, 0, ph), mode="replicate")
            r = m(patch).float()[:, :, : (yb - ya) * s, : (xb - xa) * s]
            out[:, :, y0 * s:y1 * s, x0 * s:x1 * s] = r[:, :, (y0 - ya) * s:(y0 - ya + y1 - y0) * s, (x0 - xa) * s:(x0 - xa + x1 - x0) * s]
    return out[0].clamp(0, 1).permute(1, 2, 0).cpu().numpy()


def resize_premul(rgba_f, w, h):
    """rgba_f: float 0..1；预乘 alpha 下 Lanczos 缩放。"""
    a = rgba_f[..., 3:4]
    pm = np.concatenate([rgba_f[..., :3] * a, a], -1)
    ch = [np.array(Image.fromarray(pm[..., i].astype(np.float32), "F").resize((w, h), Image.LANCZOS)) for i in range(4)]
    pm = np.clip(np.stack(ch, -1), 0, 1)
    al = pm[..., 3:4]
    rgb = np.where(al > 1e-4, pm[..., :3] / np.maximum(al, 1e-4), 0)
    return np.concatenate([np.clip(rgb, 0, 1), al], -1)


def sr_rgba(rgba, model, out_w=None, out_h=None, alpha_mode="bicubic"):
    """rgba: HxWx4 uint8 → 超分后缩放到 (out_w, out_h) 的 HxWx4 uint8（不给尺寸就保持模型倍数）。"""
    m = load(model)
    s = m.scale
    H, W = rgba.shape[:2]
    rgb = bleed_rgb(rgba[..., :3], rgba[..., 3])
    up = run_model(m, rgb)
    if alpha_mode == "model":
        a = run_model(m, np.repeat(rgba[..., 3:4], 3, -1)).mean(-1, keepdims=True)
    else:
        a = np.array(Image.fromarray(rgba[..., 3]).resize((W * s, H * s), Image.BICUBIC)).astype(np.float32)[..., None] / 255
    big = np.concatenate([up, a], -1)
    if out_w and out_h and (out_w, out_h) != (W * s, H * s):
        big = resize_premul(big, out_w, out_h)
    return (np.clip(big, 0, 1) * 255 + 0.5).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--model", required=True)
    ap.add_argument("--out-scale", type=float, default=None, help="相对输入的最终倍数（默认 = 模型倍数）")
    ap.add_argument("--alpha", default="bicubic", choices=["bicubic", "model"])
    a = ap.parse_args()
    im = np.array(Image.open(a.src).convert("RGBA"))
    H, W = im.shape[:2]
    ow, oh = (round(W * a.out_scale), round(H * a.out_scale)) if a.out_scale else (None, None)
    Image.fromarray(sr_rgba(im, a.model, ow, oh, a.alpha)).save(a.dst)
    print(a.dst)


if __name__ == "__main__":
    main()
