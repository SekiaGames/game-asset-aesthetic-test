"""绿幕图 → 透明 RGBA（图像模型绿底出图后用）。

    python -I scripts/key-unmix.py <绿底.png> <输出.png>

算法（自写）：已知纯色背景的抠图——Vlahos 差值键求 α + 去混色还原前景色。
溢绿量 s = G − max(R, B)。背景色取本图背景像素（s > 150）的中位数，「完全透明」的界取背景 s 的 1% 分位 × 0.97
（每张图的绿都不同：实测中位 238 / 218 / 187）。α = 1 − s / 界；前景色 F = (C − (1 − α)·背景色) / α。
简单的「s > 20 就透明、把 G 压到 max(R, B)」会把一半皮肤一半绿幕的边缘像素当成背景（边变细 → 锯齿），
留下的边缘被压成暗橄榄色（2026-10-09 实测腿边缘 RGB (59,66,54)，内部亮度 217）。
front-layers.py 也从这里导入 key_unmix。
"""
import sys

import numpy as np
from PIL import Image


def key_green(rgb):
    """简单绿幕键（背景像素太少、取不到背景色时的退路）。"""
    r, g, b = [rgb[..., i].astype(np.int16) for i in range(3)]
    spill = g - np.maximum(r, b)
    alpha = np.clip((80 - spill) / 60.0, 0, 1)
    out = rgb.copy()
    g2 = np.minimum(g, np.maximum(r, b) + 4)
    out[..., 1] = np.where(spill > 4, g2, g).astype(np.uint8)
    return out, (alpha * 255).astype(np.uint8)


def key_unmix(rgb):
    c = rgb.astype(np.float32)
    s = c[..., 1] - np.maximum(c[..., 0], c[..., 2])
    bgm = s > 150
    if bgm.sum() < 100:
        return key_green(rgb)
    bg = np.median(c[bgm], 0)
    floor = np.percentile(s[bgm], 1) * 0.97
    alpha = np.clip(1.0 - s / floor, 0.0, 1.0)
    a3 = np.maximum(alpha, 0.05)[..., None]
    fg = (c - (1.0 - alpha[..., None]) * bg) / a3
    fg = np.where(alpha[..., None] > 0.02, fg, c)
    return np.clip(fg, 0, 255).astype(np.uint8), (alpha * 255).round().astype(np.uint8)


if __name__ == "__main__":
    src, dst = sys.argv[1:3]
    rgb, alpha = key_unmix(np.array(Image.open(src).convert("RGB")))
    Image.fromarray(np.dstack([rgb, alpha])).save(dst)
    print(dst, rgb.shape[1], "x", rgb.shape[0], "前景占比", round(float((alpha > 127).mean()), 3))
