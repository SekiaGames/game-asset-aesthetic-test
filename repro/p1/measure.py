"""测量参考图与四件部件图的关键尺寸，输出 measurements.json。

两个坑先处理掉：
1. ImageGen 的“透明背景”实际是画上去的棋盘格（白 / 浅灰方块），不是 alpha；
   这里按「灰色 + 亮」判定背景并挖掉，再用颜色直方图找主色。
2. 右下角有 “AI生成” 水印，直接清掉（部件都居中，不影响主体）。

没有目测估值：主色 bbox 就是头发 / 裙子 / 皮肤 / 靴子的实际范围。
"""
import json
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, "art", "gen")
REF = os.path.join(GEN, "Anime_game_character_reference_2026-10-21T13-55-27.png")
PARTS = {
    "head": os.path.join(GEN, "Isolate_ONLY_the_head_and_neck_2026-10-21T13-56-39.png"),
    "dress": os.path.join(GEN, "Isolate_ONLY_the_dress_of_this_2026-10-21T13-58-32.png"),
    "arm": os.path.join(GEN, "Isolate_ONLY_one_bare_arm_with_2026-10-21T13-59-35.png"),
    "leg": os.path.join(GEN, "Isolate_ONLY_one_bare_leg_with_2026-10-21T14-00-37.png"),
}


def load(path):
    return np.array(Image.open(path).convert("RGBA")).astype(np.int16)


def strip_background(a):
    """挖掉棋盘格背景、地平线与水印，返回 RGBA（uint8）。"""
    rgb = a[..., :3].astype(np.int16)
    mx, mn = rgb.max(-1), rgb.min(-1)
    fg = ~((mx - mn <= 11) & (mn >= 196))         # 白 / 浅灰棋盘格（含抗锯齿边）
    out = a.copy()
    out[..., 3][~fg] = 0
    h, w = out.shape[:2]
    out[h - 96:h, w - 170:w, 3] = 0                # 右下角 “AI生成” 水印
    # 地平线：底部附近一条几乎横贯全图的细线
    for y in range(int(h * 0.86), h):
        if (out[y, :, 3] > 128).sum() > w * 0.55:
            out[max(0, y - 2):y + 3, :, 3] = 0
    # 去掉孤立噪点，再只留够大的连通块
    from scipy import ndimage
    solid = ndimage.binary_opening(out[..., 3] > 128, np.ones((3, 3)))
    lab, n = ndimage.label(solid)
    if n:
        sizes = ndimage.sum(solid, lab, range(1, n + 1))
        keep = {i + 1 for i, s in enumerate(sizes) if s >= 1500}
        kill = (lab > 0) & ~np.isin(lab, list(keep))
        out[..., 3][kill] = 0
    return out.astype(np.uint8)


def bbox(mask):
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def dominant(a, k=8):
    """按 8 级量化统计主色，返回 [(count, [r,g,b])]，忽略 alpha=0。"""
    solid = a[..., 3] > 200
    q = (a[..., :3][solid] // 8 * 8)
    if len(q) == 0:
        return []
    uniq, cnt = np.unique(q.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(-cnt)[:k]
    return [[int(cnt[i]), [int(v) for v in uniq[i]]] for i in order]


def close_mask(a, color, tol=14):
    rgb = a[..., :3].astype(np.float32)
    d = np.abs(rgb - np.array(color, np.float32)).max(-1)
    return (d < tol) & (a[..., 3] > 200)


def measure(path):
    a = strip_background(load(path))
    alpha = a[..., 3] > 128
    out = {"size": [int(a.shape[1]), int(a.shape[0])],
           "bbox": bbox(alpha), "dominant": dominant(a)}
    out["boxes"] = {f"{i}_{c[0]}_{c[1]}_{c[2]}": bbox(close_mask(a, c)) for i, (_, c) in enumerate(out["dominant"][:6])}
    return a, out


def main():
    imgs = {}
    imgs["ref"], ref = measure(REF)
    res = {"ref": ref, "parts": {}}
    for name, p in PARTS.items():
        imgs[name], res["parts"][name] = measure(p)
    json.dump(res, open(os.path.join(HERE, "measurements.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))
    # 顺便把清理后的图存下来给后续拼装用
    outdir = os.path.join(HERE, "art", "clean")
    os.makedirs(outdir, exist_ok=True)
    for name, a in imgs.items():
        Image.fromarray(a, "RGBA").save(os.path.join(outdir, f"{name}.png"))


if __name__ == "__main__":
    main()
