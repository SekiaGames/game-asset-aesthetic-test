"""三视图设定图（一张图里并排的正 / 侧 / 背）→ 三张同画布、同比例、脚底对齐的单人图，给 See-through 拆层。

    python -I scripts/sheet-split.py <sheet.png> <out_dir> \
        [--names front,side,back] [--size 1696x2464] [--height 2184] [--ground 2316] [--model RealESRGAN_x4plus_anime_6B.pth]

为什么：2026-10-10 实测本地 Qwen 2.1 从正面图单独转侧 / 背面几乎总是画回正面（config/dir-view-prompts.json 的记录），
而「一张宽画布、左栏放正面、中右栏留空，编辑成三视图设定图」一次就出了正确的侧面和背面，三个人同高、同一地平线、服装画风一致。
做法：按 α 把设定图等分成 N 栏，每栏取最大的连通前景为人物；所有栏用同一个缩放倍数（第一栏的人物高 → --height），
保持三个视角之间的相对身高；每张的人物水平居中、脚底放在 --ground。放大用动漫超分（upscale-anime.py 的 sr_rgba）。
默认画布、身高、地平线取正面 2K 图（output/front-2k/src/front.png：人物 132–2316 行）的值，三视角与正面骨骼同一尺度。
"""
import argparse
import importlib.util
import json
import os

import cv2
import numpy as np
from PIL import Image

_spec = importlib.util.spec_from_file_location("upscale_anime", os.path.join(os.path.dirname(os.path.abspath(__file__)), "upscale-anime.py"))
UA = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(UA)


def make_input(front, out, panels):
    f = np.array(Image.open(front).convert("RGBA"))
    f[f[..., 3] == 0, :3] = 0
    H, W = f.shape[:2]
    c = np.zeros((H, W * panels, 4), np.uint8)
    c[:, :W] = f
    Image.fromarray(c).save(out)
    print(f"{out}: {W * panels}×{H}，左栏为正面图")


def main():
    import sys
    if "--make-input" in sys.argv:
        i = sys.argv.index("--make-input")
        panels = int(sys.argv[sys.argv.index("--panels") + 1]) if "--panels" in sys.argv else 3
        return make_input(sys.argv[i + 1], sys.argv[i + 2], panels)
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("out")
    ap.add_argument("--names", default="front,side,back")
    ap.add_argument("--size", default="1696x2464")
    ap.add_argument("--height", type=float, default=2184)
    ap.add_argument("--ground", type=float, default=2316)
    ap.add_argument("--model", default="RealESRGAN_x4plus_anime_6B.pth")
    a = ap.parse_args()
    names = a.names.split(",")
    TW, TH = map(int, a.size.split("x"))
    os.makedirs(a.out, exist_ok=True)
    sheet = np.array(Image.open(a.sheet).convert("RGBA"))
    H, W = sheet.shape[:2]
    al = sheet[..., 3] > 8
    boxes = []
    for i in range(len(names)):
        x0, x1 = round(W * i / len(names)), round(W * (i + 1) / len(names))
        n, lab, st, _ = cv2.connectedComponentsWithStats(al[:, x0:x1].astype(np.uint8), 8)
        k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        m = lab == k
        # 同一栏里和人物相交的其他小块（发梢、鞋带断开的部分）也算进来：取人物框内全部前景
        ys, xs = np.nonzero(m)
        bx0, by0, bx1, by1 = xs.min() + x0, ys.min(), xs.max() + x0 + 1, ys.max() + 1
        boxes.append((bx0, by0, bx1, by1))
    s = a.height / (boxes[0][3] - boxes[0][1])
    info = {"sheet": a.sheet, "scale": s, "views": {}}
    for nm, (bx0, by0, bx1, by1) in zip(names, boxes):
        pad = 24
        cx0, cy0, cx1, cy1 = max(0, bx0 - pad), max(0, by0 - pad), min(W, bx1 + pad), min(H, by1 + pad)
        crop = sheet[cy0:cy1, cx0:cx1].copy()
        # 栏外的前景（相邻人物）不要
        keep = np.zeros(crop.shape[:2], bool)
        keep[by0 - cy0:by1 - cy0, bx0 - cx0:bx1 - cx0] = True
        crop[~keep] = 0
        ow, oh = round(crop.shape[1] * s), round(crop.shape[0] * s)
        big = UA.sr_rgba(crop, a.model, ow, oh)
        canvas = np.zeros((TH, TW, 4), np.uint8)
        # 人物中心 → 画布中心，脚底 → ground
        px = round(TW / 2 - ((bx0 + bx1) / 2 - cx0) * s)
        py = round(a.ground - (by1 - cy0) * s)
        sx0, sy0 = max(0, -px), max(0, -py)
        dx0, dy0 = max(0, px), max(0, py)
        w_ = min(big.shape[1] - sx0, TW - dx0)
        h_ = min(big.shape[0] - sy0, TH - dy0)
        canvas[dy0:dy0 + h_, dx0:dx0 + w_] = big[sy0:sy0 + h_, sx0:sx0 + w_]
        canvas[canvas[..., 3] == 0, :3] = 0
        Image.fromarray(canvas).save(os.path.join(a.out, f"{nm}.png"))
        info["views"][nm] = {"sheet_box": [int(bx0), int(by0), int(bx1), int(by1)], "height_px": float((by1 - by0) * s)}
        print(f"{nm}: 设定图里 {bx1 - bx0}×{by1 - by0}px → 人物高 {(by1 - by0) * s:.0f}px")
    json.dump(info, open(os.path.join(a.out, "split.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
