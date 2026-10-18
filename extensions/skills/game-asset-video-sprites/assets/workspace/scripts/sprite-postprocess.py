"""游戏精灵后处理：视频抽帧 → 缩小 → 锁调色板 → 颜色抠图 / 蒙版时域中值 → 拼精灵表，外加衔接与一致性指标。

依赖 numpy / Pillow / opencv（ComfyUI 自带 python 里都有）：
    python scripts/sprite-postprocess.py <子命令> ...

子命令：
    extract   视频抽帧（ffmpeg），可指定 fps 与帧数上限
    palette   从参考图 k-means 取调色板（可附加保留色，如抠图用的纯色背景）
    pixelize  缩小（nearest / box）+ 锁调色板 + 按背景色抠图 → RGBA 帧
    matte     对已有 RGBA 帧（如 BiRefNet 输出）做相邻 N 帧 alpha 中值，可再缩小锁色
    sheet     多帧拼成一行精灵表 + 预览 GIF
    metrics   衔接（首尾帧差）、帧间变化、调色板外颜色数、alpha 闪烁
    loopsearch 在长视频里找最相似的两帧（间隔在给定范围内），用来截出短循环
"""
import argparse
import glob
import json
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image


def _frames(pattern):
    files = sorted(glob.glob(pattern))
    if not files:
        sys.exit(f"没有匹配的帧: {pattern}")
    return files


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c)


def _parse_hex(s):
    s = s.lstrip("#")
    return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.uint8)


def load_palette(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return np.array([_parse_hex(c) for c in data["colors"]], dtype=np.uint8), data


def quantize(rgb, palette):
    """每个像素映射到调色板里最近的颜色（RGB 欧氏距离，不抖动）。返回索引图。"""
    flat = rgb.reshape(-1, 3).astype(np.int32)
    pal = palette.astype(np.int32)
    idx = np.empty(len(flat), dtype=np.int32)
    step = 1 << 16
    for s in range(0, len(flat), step):
        d = ((flat[s:s + step, None, :] - pal[None, :, :]) ** 2).sum(-1)
        idx[s:s + step] = d.argmin(1)
    return idx.reshape(rgb.shape[:2])


def chroma_key(rgb, t0=20, t1=70):
    """绿幕抠图 + 去溢色（高清阶段做）。greenness = G - max(R,B)：<=t0 全不透明，>=t1 全透明。"""
    f = rgb.astype(np.float32)
    rb = np.maximum(f[..., 0], f[..., 2])
    gness = f[..., 1] - rb
    alpha = np.clip((t1 - gness) / (t1 - t0), 0, 1)
    f[..., 1] = np.where(gness > 0, rb, f[..., 1])  # 去溢色：G 压到 max(R,B)
    return f.clip(0, 255).astype(np.uint8), (alpha * 255).astype(np.uint8)


def cmd_extract(a):
    os.makedirs(a.out, exist_ok=True)
    vf = [f"fps={a.fps}"] if a.fps else []
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", a.video]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    if a.max:
        cmd += ["-frames:v", str(a.max)]
    cmd += [os.path.join(a.out, "f_%04d.png")]
    subprocess.run(cmd, check=True)
    print(len(glob.glob(os.path.join(a.out, "f_*.png"))), "帧 →", a.out)


def cmd_palette(a):
    img = np.array(Image.open(a.image).convert("RGBA"))
    rgb, alpha = img[..., :3], img[..., 3]
    if a.chroma:
        rgb, alpha = chroma_key(rgb)
        alpha = np.where(alpha >= 250, 255, 0).astype(np.uint8)  # 只用完全不透明的像素取色
    px = rgb[alpha > 127].reshape(-1, 3)
    if a.exclude:
        ex = _parse_hex(a.exclude).astype(np.int32)
        px = px[((px.astype(np.int32) - ex) ** 2).sum(1) > a.exclude_dist ** 2]
    if len(px) > 200000:
        px = px[np.random.default_rng(0).choice(len(px), 200000, replace=False)]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
    _, labels, centers = cv2.kmeans(px.astype(np.float32), a.k, None, crit, 4, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=a.k)
    order = np.argsort(-counts)
    colors = [_hex(np.clip(centers[i], 0, 255)) for i in order]
    data = {"source": a.image, "k": a.k, "colors": colors, "key": a.key}
    if a.key:
        data["colors"] = colors + [a.key]  # 抠图色放最后一位
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    sw = np.array([_parse_hex(c) for c in data["colors"]], dtype=np.uint8)[None].repeat(16, 0).repeat(16, 1)
    Image.fromarray(sw).save(os.path.splitext(a.out)[0] + ".png")
    print(f"{len(data['colors'])} 色 →", a.out)


def _crop_box(files, a):
    if a.crop == "auto":
        # 所有帧前景（绿幕抠图）的并集框，四周留边；全片共用一个框，角色不会跳
        x0 = y0 = 10 ** 9
        x1 = y1 = 0
        for fp in files[::max(1, len(files) // 24)]:
            im = Image.open(fp).convert("RGB")
            al = chroma_key(np.array(im))[1] > 128
            ys, xs = np.nonzero(al)
            if len(xs):
                x0, x1 = min(x0, xs.min()), max(x1, xs.max())
                y0, y1 = min(y0, ys.min()), max(y1, ys.max())
        m = int(0.03 * (y1 - y0))
        w, h = im.size
        box = (max(0, x0 - m), max(0, y0 - m), min(w, x1 + m), min(h, y1 + m))
        print("auto crop", box)
        return box
    if a.crop:
        return tuple(float(v) for v in a.crop.split(","))
    return None


def cmd_pixelize(a):
    palette, meta = load_palette(a.palette)
    key = _parse_hex(meta["key"]) if meta.get("key") else None
    os.makedirs(a.out, exist_ok=True)
    files = _frames(a.frames)
    box = _crop_box(files, a)
    for i, fp in enumerate(files):
        im = Image.open(fp).convert("RGB")
        if box:
            if all(v <= 1 for v in box) and a.crop != "auto":  # 比例坐标，适配不同分辨率的视频帧
                box = tuple(round(v * s) for v, s in zip(box, im.size * 2))
            im = im.crop(box)
        w, h = im.size
        tw = round(w * a.height / h) if a.height else a.width
        if a.chroma:
            rgb_hi, al_hi = chroma_key(np.array(im))
            th = round(h * tw / w)
            prem = Image.fromarray(np.dstack([rgb_hi, al_hi]), "RGBA").resize((tw, th), Image.BOX)
            arr = np.array(prem)
            fg = arr[..., 3] >= a.alpha_cut
            pal = palette[:-1] if key is not None else palette
            if a.perframe:
                q = Image.fromarray(arr[..., :3]).quantize(a.perframe, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
                rgb = np.array(q.convert("RGB"))
            else:
                rgb = pal[quantize(arr[..., :3], pal)]
            alpha = np.where(fg, 255, 0).astype(np.uint8)
            if a.despeckle:
                op = alpha > 0
                pad = np.pad(op, 1)
                nb = pad[:-2, 1:-1].astype(int) + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:]
                alpha[op & (nb == 0)] = 0
            Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(os.path.join(a.out, f"p_{i:04d}.png"))
            continue
        th = round(h * tw / w)
        if a.mode == "nearest":
            small = im.resize((tw, th), Image.NEAREST)
        else:  # box：区域平均，再锁色
            small = im.resize((tw, th), Image.BOX)
        if a.perframe:
            # 对照组：每帧各自 MEDIANCUT 限色（kurumi-fx-rogue 现有做法），不锁全局调色板
            q = small.quantize(a.perframe, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
            rgb = np.array(q.convert("RGB"))
            idx = quantize(rgb, palette)  # 只用来判断背景
            idx = np.where(idx == len(palette) - 1, idx, 0)
        else:
            idx = quantize(np.array(small), palette)
            rgb = palette[idx]
        alpha = np.full(idx.shape, 255, np.uint8)
        if key is not None:
            alpha[idx == len(palette) - 1] = 0
        if a.despeckle and key is not None:
            # 去掉孤立的不透明像素（四邻全透明）
            op = alpha > 0
            pad = np.pad(op, 1)
            nb = pad[:-2, 1:-1].astype(int) + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:]
            alpha[op & (nb == 0)] = 0
        out = np.dstack([rgb, alpha])
        Image.fromarray(out, "RGBA").save(os.path.join(a.out, f"p_{i:04d}.png"))
    print(len(files), "帧 →", a.out)


def cmd_loopsearch(a):
    files = _frames(a.frames)
    ims = np.stack([np.asarray(Image.open(f).convert("RGB").resize((96, 72), Image.BOX), np.float32) for f in files])
    best = []
    for i in range(len(ims)):
        for j in range(i + a.min_len, min(len(ims), i + a.max_len + 1)):
            best.append((float(np.abs(ims[i] - ims[j]).mean()), i, j))
    best.sort()
    out, used = [], []
    for d, i, j in best:
        if all(abs(i - u) > a.min_len for u in used):
            out.append({"diff": round(d, 3), "start": i, "end": j, "len": j - i})
            used.append(i)
        if len(out) >= a.top:
            break
    print(json.dumps(out, ensure_ascii=False))


def cmd_matte(a):
    files = _frames(a.frames)
    imgs = [np.array(Image.open(f).convert("RGBA")) for f in files]
    alphas = np.stack([im[..., 3] for im in imgs]).astype(np.float32)
    r = a.window // 2
    os.makedirs(a.out, exist_ok=True)
    pal = load_palette(a.palette)[0] if a.palette else None
    if pal is not None and len(pal) and a.drop_key:
        pal = pal[:-1]
    for i, im in enumerate(imgs):
        lo, hi = max(0, i - r), min(len(imgs), i + r + 1)
        al = np.median(alphas[lo:hi], 0) if a.window > 1 else alphas[i]
        out = im.copy()
        out[..., 3] = al.astype(np.uint8)
        pim = Image.fromarray(out, "RGBA")
        if a.width:
            th = round(pim.height * a.width / pim.width)
            pim = pim.resize((a.width, th), Image.BOX)
            arr = np.array(pim)
            arr[..., 3] = np.where(arr[..., 3] >= 128, 255, 0)
            if pal is not None:
                arr[..., :3] = pal[quantize(arr[..., :3], pal)]
            pim = Image.fromarray(arr, "RGBA")
        pim.save(os.path.join(a.out, f"m_{i:04d}.png"))
    print(len(files), "帧 →", a.out)


def cmd_sheet(a):
    files = _frames(a.frames)
    if a.step > 1:
        files = files[::a.step]
    if a.drop_last:
        files = files[:-1]
    ims = [Image.open(f).convert("RGBA") for f in files]
    w, h = ims[0].size
    sheet = Image.new("RGBA", (w * len(ims), h), (0, 0, 0, 0))
    for i, im in enumerate(ims):
        sheet.paste(im, (i * w, 0))
    sheet.save(a.out)
    if a.gif:
        sc = a.preview_scale
        bg = Image.new("RGBA", (w * sc, h * sc), a.bg)
        frames = []
        for im in ims:
            f = bg.copy()
            f.alpha_composite(im.resize((w * sc, h * sc), Image.NEAREST))
            frames.append(f.convert("RGB"))
        frames[0].save(a.gif, save_all=True, append_images=frames[1:], duration=int(1000 / a.fps), loop=0)
    print(f"{len(ims)} 帧 {w}x{h} →", a.out)


def cmd_metrics(a):
    files = _frames(a.frames)
    ims = [np.array(Image.open(f).convert("RGBA")).astype(np.float32) for f in files]
    rgb = [im[..., :3] for im in ims]
    al = [im[..., 3] for im in ims]

    def mad(x, y):
        return float(np.abs(x - y).mean())

    res = {"frames": len(files), "size": list(ims[0].shape[1::-1])}
    res["seam_first_last"] = mad(rgb[0], rgb[-1])
    steps = [mad(rgb[i], rgb[i + 1]) for i in range(len(rgb) - 1)]
    res["step_mean"] = float(np.mean(steps))
    res["step_max"] = float(np.max(steps))
    res["step_max_at"] = int(np.argmax(steps))
    # 首尾帧差 / 平均帧间差：<1 说明首尾接得比普通相邻帧还紧
    res["seam_ratio"] = res["seam_first_last"] / max(res["step_mean"], 1e-6)
    # 运动量：每帧与首帧的最大差，判断“首尾同图时有没有动起来”
    res["motion_peak_vs_first"] = float(max(mad(r, rgb[0]) for r in rgb))
    if a.other:
        oim = Image.open(a.other).convert("RGB")
        if oim.size != tuple(res["size"]):
            oim = oim.resize(tuple(res["size"]), Image.LANCZOS)
        other = np.array(oim).astype(np.float32)
        res["seam_last_to_other"] = mad(rgb[-1], other)
    if any((x < 255).any() for x in al):
        flick = [float(np.abs(al[i] - al[i + 1]).mean()) for i in range(len(al) - 1)]
        res["alpha_flicker_mean"] = float(np.mean(flick))
        res["alpha_flicker_max"] = float(np.max(flick))
        # 半透明像素占比（像素路线应为 0）
        res["alpha_partial_ratio"] = float(np.mean([((x > 0) & (x < 255)).mean() for x in al]))
    if a.palette:
        pal = load_palette(a.palette)[0]
        palset = {tuple(c) for c in pal.tolist()}
        off = []
        for r_, a_ in zip(rgb, al):
            px = r_[a_ > 0].astype(np.uint8)
            uniq = {tuple(c) for c in np.unique(px.reshape(-1, 3), axis=0).tolist()}
            off.append(len(uniq - palset))
        res["off_palette_colors_max"] = int(max(off))
    # 颜色稳定：前景平均色的逐帧标准差
    means = [r_[a_ > 0].mean(0) if (a_ > 0).any() else np.zeros(3) for r_, a_ in zip(rgb, al)]
    res["fg_mean_color_std"] = float(np.std(np.stack(means), 0).mean())
    out = json.dumps(res, ensure_ascii=False, indent=1)
    print(out)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("extract")
    s.add_argument("video")
    s.add_argument("out")
    s.add_argument("--fps", type=float, default=0)
    s.add_argument("--max", type=int, default=0)
    s.set_defaults(fn=cmd_extract)

    s = sp.add_parser("palette")
    s.add_argument("image")
    s.add_argument("out", help="输出 .json（同名 .png 色板预览）")
    s.add_argument("-k", type=int, default=24)
    s.add_argument("--key", help="附加的抠图背景色，如 #ff00ff")
    s.add_argument("--exclude", help="取色时排除接近该色的像素（背景）")
    s.add_argument("--exclude-dist", type=float, default=90)
    s.add_argument("--chroma", action="store_true", help="先绿幕抠图去溢色再取色")
    s.set_defaults(fn=cmd_palette)

    s = sp.add_parser("pixelize")
    s.add_argument("frames", help="glob，如 out/f_*.png")
    s.add_argument("palette")
    s.add_argument("out")
    s.add_argument("--width", type=int, default=64)
    s.add_argument("--mode", choices=["nearest", "box"], default="box")
    s.add_argument("--crop", help="x0,y0,x1,y1 先裁再缩（≤1 为比例坐标）；auto = 全片前景并集框")
    s.add_argument("--height", type=int, default=0, help="按目标高度缩放（优先于 --width）")
    s.add_argument("--despeckle", action="store_true")
    s.add_argument("--perframe", type=int, default=0, help="对照组：每帧单独 MEDIANCUT 到 N 色")
    s.add_argument("--chroma", action="store_true", help="高清阶段绿幕抠图 + 去溢色，再 BOX 缩小（推荐）")
    s.add_argument("--alpha-cut", type=int, default=128)
    s.set_defaults(fn=cmd_pixelize)

    s = sp.add_parser("loopsearch")
    s.add_argument("frames")
    s.add_argument("--min-len", type=int, default=8)
    s.add_argument("--max-len", type=int, default=24)
    s.add_argument("--top", type=int, default=5)
    s.set_defaults(fn=cmd_loopsearch)

    s = sp.add_parser("matte")
    s.add_argument("frames")
    s.add_argument("out")
    s.add_argument("--window", type=int, default=3)
    s.add_argument("--width", type=int, default=0, help="非 0 时缩小并二值化 alpha")
    s.add_argument("--palette")
    s.add_argument("--drop-key", action="store_true", help="调色板最后一位是抠图色时去掉")
    s.set_defaults(fn=cmd_matte)

    s = sp.add_parser("sheet")
    s.add_argument("frames")
    s.add_argument("out")
    s.add_argument("--step", type=int, default=1)
    s.add_argument("--drop-last", action="store_true", help="循环动画去掉与首帧重复的末帧")
    s.add_argument("--gif")
    s.add_argument("--fps", type=float, default=12)
    s.add_argument("--preview-scale", type=int, default=4)
    s.add_argument("--bg", default="#808080")
    s.set_defaults(fn=cmd_sheet)

    s = sp.add_parser("metrics")
    s.add_argument("frames")
    s.add_argument("--palette")
    s.add_argument("--other", help="与另一张图比较末帧（如 A→R 的末帧对 R）")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_metrics)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
