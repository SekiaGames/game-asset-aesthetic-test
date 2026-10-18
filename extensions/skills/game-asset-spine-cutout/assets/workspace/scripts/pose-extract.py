"""Run DWPose (comfyui_controlnet_aux, models yzd-v/DWPose: yolox_l.onnx + dw-ll_ucoco_384.onnx)
on a frame sequence and save body keypoints in pixel coordinates, plus skeleton overlays to eyeball.

Usage: python scripts/pose-extract.py "<frames glob>" <out_dir>
(no -I: the controlnet_aux package is imported from the ComfyUI install.)
Add --on-white for green-screen frames: the green is keyed with a soft alpha and composited on white first.
Measured 2026-10-09 on front views: raw green gave 0 people on 1/1 image; a hard green->white swap still
left a green fringe and gave 0 people on 4/8 gesture images; the soft composite found 14/14 points on all.
Add --ref <front poses.json> for same-canvas gesture edits (body fixed, only arms move): tries 2 backgrounds x
3 scales, un-swaps L/R against the reference body and keeps the result with fewest missing / over-long arm
points (a segment > 1.4x the reference), then the smallest body error (自写; 2K transparent-route images: 3/8 came back L/R-swapped, 1/8 with no person at 1x).
A missing wrist is filled from hand point 0 when the hand was found.
Writes <out_dir>/poses.json: [{"file", "w", "h", "kp": [[x, y, score] | null] * 18}] in OpenPose-18
order (0 nose, 1 neck, 2 R-shoulder, 3 R-elbow, 4 R-wrist, 5 L-shoulder, 6 L-elbow, 7 L-wrist,
8 R-hip, 9 R-knee, 10 R-ankle, 11 L-hip, 12 L-knee, 13 L-ankle, 14-17 eyes/ears), and
<out_dir>/overlay/*.png. Each entry also has "face" (68 points, iBUG order: 0-16 jaw, 17-26 brows,
27-35 nose, 36-47 eyes, 48-67 mouth) and "hand_l" / "hand_r" (21 points), [x, y] in pixels or null. Models are downloaded on first use into the node's ckpts/ folder.
"""
import glob
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

COMFY = os.environ.get("COMFYUI_DIR", "ComfyUI")  # ComfyUI 目录（含 custom_nodes / models / output）
AUX = os.path.join(COMFY, "custom_nodes/comfyui_controlnet_aux/src")
sys.path.insert(0, AUX)
from custom_controlnet_aux.dwpose import DwposeDetector  # noqa: E402

LIMBS = [(1, 2), (2, 3), (3, 4), (1, 5), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10), (1, 11), (11, 12),
         (12, 13), (1, 0)]
COL = {"R": (255, 80, 80), "L": (80, 160, 255), "C": (255, 230, 80)}


def side(a, b):
    if {a, b} & {2, 3, 4, 8, 9, 10}:
        return "R"
    if {a, b} & {5, 6, 7, 11, 12, 13}:
        return "L"
    return "C"


def on_white(im):
    a = np.array(im).astype(np.float32)
    spill = a[..., 1] - np.maximum(a[..., 0], a[..., 2])
    al = np.clip((80 - spill) / 60.0, 0, 1)[..., None]
    return Image.fromarray((a * al + 255 * (1 - al)).astype(np.uint8))


SWAP = {2: 5, 3: 6, 4: 7, 5: 2, 6: 3, 7: 4, 8: 11, 9: 12, 10: 13, 11: 8, 12: 9, 13: 10, 14: 15, 15: 14, 16: 17, 17: 16}
BODY = (1, 2, 5, 8, 11)  # 同画布编辑时不动的点：脖子、双肩、双胯


def body_err(kp, ref):
    """与参照（正面图）身体点的平均偏差 px；缺点记 9999。"""
    if any(kp[i] is None or ref[i] is None for i in BODY):
        return 9999.0
    return float(np.mean([np.hypot(kp[i][0] - ref[i][0], kp[i][1] - ref[i][1]) for i in BODY]))


def bad_arm_points(kp, ref):
    """缺的手臂点 + 比参照对应段长 40% 以上的段（同一角色同一画布，手臂不会变长；透视只会变短）。"""
    n = sum(kp[i] is None for i in (3, 4, 6, 7))
    for a, b in ((2, 3), (3, 4), (5, 6), (6, 7)):
        if kp[a] and kp[b] and ref[a] and ref[b]:
            seg = np.hypot(kp[a][0] - kp[b][0], kp[a][1] - kp[b][1])
            if seg > 1.4 * np.hypot(ref[a][0] - ref[b][0], ref[a][1] - ref[b][1]):
                n += 1
    return n


def read_pose(best, s):
    kp = [None if k is None else [k.x / s, k.y / s, k.score] for k in best.body.keypoints]
    extra = {"face": None, "hand_l": None, "hand_r": None}
    for key, pts in (("face", best.face), ("hand_l", best.left_hand), ("hand_r", best.right_hand)):
        if pts:  # same pixel units as the body; face is padded to 70 with the body eyes, keep 68
            extra[key] = [None if k is None else [k.x / s, k.y / s] for k in pts[:68]]
    return kp, extra


def swapped(kp, extra):
    return [kp[SWAP.get(i, i)] for i in range(18)], {**extra, "hand_l": extra["hand_r"], "hand_r": extra["hand_l"]}


def fill_wrists(kp, extra):
    """手腕漏检但手部点在：用手部第 0 点（手腕）或手部点均值补上。返回补了哪些。"""
    done = []
    for wi, hk in ((4, "hand_r"), (7, "hand_l")):
        pts = [q for q in (extra[hk] or []) if q is not None]
        if kp[wi] is None and len(pts) >= 5:
            w = extra[hk][0] or list(np.mean(pts, 0))
            kp[wi] = [float(w[0]), float(w[1]), 0.0]
            done.append(wi)
    return done


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    white = "--on-white" in sys.argv
    ref = None
    if "--ref" in sys.argv:
        ref = json.load(open(sys.argv[sys.argv.index("--ref") + 1]))[0]["kp"]
        args.remove(sys.argv[sys.argv.index("--ref") + 1])
    pattern, out = args[0], args[1]
    os.makedirs(os.path.join(out, "overlay"), exist_ok=True)
    det = DwposeDetector.from_pretrained("yzd-v/DWPose", "yzd-v/DWPose", det_filename="yolox_l.onnx",
                                         pose_filename="dw-ll_ucoco_384.onnx", torchscript_device="cuda")
    res = []
    for f in sorted(glob.glob(pattern)):
        src_im = Image.open(f)
        rgba = src_im.mode == "RGBA" and (np.array(src_im)[..., 3] < 128).mean() > 0.05

        def composite(g):
            # 真透明图（Qwen 透明路线）：按 alpha 合成到纯色底；透明处的 RGB 是杂色，直接丢 alpha 会干扰检测
            bg = Image.new("RGBA", src_im.size, (g, g, g, 255))
            bg.alpha_composite(src_im)
            return bg.convert("RGB")

        if rgba:
            im = composite(255)
        else:
            im = src_im.convert("RGB")
            if white:
                im = on_white(im)
        w, h = im.size
        kp, extra, n_people, tta = [None] * 18, {"face": None, "hand_l": None, "hand_r": None}, 0, None
        if ref is None:
            poses = det.detect_poses(np.array(im))
            n_people = len(poses)
            if poses:
                kp, extra = read_pose(max(poses, key=lambda p: p.body.total_score), 1.0)
        else:
            # 同画布编辑的手势图：身体不动，只有手臂变。DWPose 在 2K 透明路线图上常整套左右标反、个别尺寸检不出人
            # （2026-10-09 实测 8 张里 3 张反、1 张 0 人、1 张肩膀全错）。这里试 2 种底色 × 3 种缩放，
            # 左右反了按参照纠正，挑「手臂点缺得最少、身体点和参照最吻合」的一组。
            cands = []
            for g in ((255, 128) if rgba else (None,)):
                base = composite(g) if g else im
                for s in (1.0, 0.75, 0.6):
                    x = base if s == 1.0 else base.resize((round(w * s), round(h * s)), Image.LANCZOS)
                    poses = det.detect_poses(np.array(x))
                    if not poses:
                        continue
                    k0, e0 = read_pose(max(poses, key=lambda p: p.body.total_score), s)
                    k1, e1 = swapped(k0, e0)
                    for kk, ee, sw in ((k0, e0, False), (k1, e1, True)):
                        filled = fill_wrists(kk, ee)
                        miss = bad_arm_points(kk, ref)
                        cands.append((miss, body_err(kk, ref), kk, ee, len(poses),
                                      {"bg": g, "scale": s, "swapped": sw, "wrist_from_hand": filled}))
            if cands:
                miss, err, kp, extra, n_people, tta = min(cands, key=lambda c: (c[0], c[1]))
                tta["body_err"] = round(err, 1)
        if ref is None:
            fill_wrists(kp, extra)
        res.append({"file": os.path.basename(f), "w": w, "h": h, "n_people": n_people, "kp": kp, **extra,
                    **({"tta": tta} if tta else {})})
        d = ImageDraw.Draw(im)
        for a, b in LIMBS:
            if kp[a] and kp[b]:
                d.line([tuple(kp[a][:2]), tuple(kp[b][:2])], fill=COL[side(a, b)], width=6)
        for k in kp:
            if k:
                d.ellipse([k[0] - 6, k[1] - 6, k[0] + 6, k[1] + 6], fill=(255, 255, 255))
        im.save(os.path.join(out, "overlay", os.path.basename(f)))
        found = sum(k is not None for k in kp[:14])
        print(f"{os.path.basename(f)} people={n_people} body_kp={found}/14" + (f" tta={tta}" if tta else ""))
    with open(os.path.join(out, "poses.json"), "w") as fp:
        json.dump(res, fp)


if __name__ == "__main__":
    main()
