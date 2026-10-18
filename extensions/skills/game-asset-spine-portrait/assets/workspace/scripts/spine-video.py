"""front-rig.py 出的骨骼 → 演示视频（不进 app，看「裸效果」）：全身几段动作 + 头部特写，拼成一个 mp4。

    python -I scripts/spine-video.py <layers_dir> <rig_dir> <out_dir> [--name kurumi_front]

先跑 spine-pack.py <rig_dir> --name <name> 生成 atlas。渲染用现有的 spine-render.mjs（官方 spine-webgl 4.2，物理逐帧推进），
本脚本只生成任务、调用它、再用 ffmpeg 把每段帧序列编码并拼接（自写的胶水）。
片段：待机 + 视线环视、蹦（看物理）、摇头、歪头、点头；头部特写（待机 + 环视，按原图 1:1 像素放大 1.5 倍看边缘）。
镜头固定（按原图画布算），各段之间不跳。
"""
import argparse
import json
import os
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECTS = os.path.normpath(os.path.join(HERE, ".."))


def ffmpeg_bin():
    p = shutil.which("ffmpeg")
    if p:
        return p
    raise SystemExit("找不到 ffmpeg")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("layers_dir")
    ap.add_argument("rig_dir")
    ap.add_argument("out")
    ap.add_argument("--name", default="kurumi_front")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--no-label", action="store_true", help="帧上不写片段名（给剪辑用的干净素材）")
    a = ap.parse_args()
    m = json.load(open(os.path.join(a.layers_dir, "layers.json"), encoding="utf-8"))
    L, kp = m["layers"], m["kp"]
    W, H = m["size"]
    lb = L["legs"]["bbox"]
    ground, cx = lb[1] + lb[3], (kp[8][0] + kp[11][0]) / 2
    # front-rig.py 不带 --ryza 时 1 像素 = 1 单位，x = 像素 x − cx，y = ground − 像素 y
    allb = [v["bbox"] for v in L.values()]  # 全身镜头：所有层的包围盒居中，上下各留 6%（蹦起来不出画）
    ax0, ay0 = min(b[0] for b in allb), min(b[1] for b in allb)
    ax1, ay1 = max(b[0] + b[2] for b in allb), max(b[1] + b[3] for b in allb)
    bh = (ay1 - ay0) * 1.12
    bw = bh * 720 / 1040
    body_cam = {"x": (ax0 + ax1) / 2 - cx - bw / 2, "y": ground - (ay0 + ay1) / 2 - bh / 2, "w": bw, "h": bh}
    # 头部特写以脸为中心（之前按前发 + 脸 + 后发的包围盒取中心：deepseek-chan 头发长到腰，镜头落到胸口）
    fx, fy, fw, fh = L["face"]["bbox"]
    side = 720 / 1.5  # 头部特写：720px 画面 = 原图 480px，即 1.5 倍
    hcx, hcy = fx + fw / 2, fy + fh * 0.4
    head_cam = {"x": hcx - side / 2 - cx, "y": ground - hcy - side / 2, "w": side, "h": side}
    rel = os.path.relpath(a.rig_dir, PROJECTS).replace("\\", "/")
    idle = {"track": 0, "anim": "motion_A_001_idle"}
    f = a.fps
    shots = [
        ("idle_look", [idle, {"track": 1, "anim": "look_around"}], 8 * f, body_cam, [720, 1040]),
        ("hop", [idle, {"track": 1, "anim": "motion_oneshot_D_010_active"}], 3 * f, body_cam, [720, 1040]),
        ("shake", [idle, {"track": 1, "anim": "motion_oneshot_D_003_active"}], int(2.6 * f), body_cam, [720, 1040]),
        ("tilt", [idle, {"track": 1, "anim": "motion_oneshot_D_009_active"}], int(3.2 * f), body_cam, [720, 1040]),
        ("nod", [idle, {"track": 1, "anim": "motion_oneshot_D_001_active"}], int(2.4 * f), body_cam, [720, 1040]),
        ("head_look", [idle, {"track": 1, "anim": "look_around"}], 8 * f, head_cam, [720, 720]),
        ("head_shake", [idle, {"track": 1, "anim": "motion_oneshot_D_003_active"}], int(2.6 * f), head_cam, [720, 720]),
    ]
    anims = json.load(open(os.path.join(a.rig_dir, f"{a.name}.json"), encoding="utf-8"))["animations"]
    if "blink" in anims and "talk" in anims:  # 有闭眼 / 张嘴层时才有这两段（front-rig.py 缺层就不生成）
        shots.append(("head_blink_talk", [idle, {"track": 3, "anim": "blink"}, {"track": 4, "anim": "talk"}],
                      6 * f, head_cam, [720, 720]))
    if "facial_eye_003_idle" in anims:  # 笑眼；没有大笑嘴（E4 的嘴被 See-through 并进了脸层）就配张嘴
        mouth = next((m for m in ("facial_mouth_003_idle", "facial_mouth_002_idle") if m in anims), None)
        tr = [idle, {"track": 1, "anim": "look_around"}, {"track": 2, "anim": "facial_eye_003_idle"}]
        if mouth:
            tr.append({"track": 3, "anim": mouth})
        shots.append(("head_happy", tr, 4 * f, head_cam, [720, 720]))
    if "motion_touch_A_001_active" in anims:  # 被点击的反应（游戏里点头部时调用）
        shots.append(("head_touch", [idle, {"track": 1, "anim": "motion_touch_A_001_active"}], 3 * f, head_cam, [720, 720]))
    os.makedirs(a.out, exist_ok=True)
    ff = ffmpeg_bin()
    segs = []
    for name, tracks, n, cam, size in shots:
        job = {"skel": f"{rel}/{a.name}.json", "atlas": f"{rel}/{a.name}.atlas", "size": size,
               "bg": [0.93, 0.93, 0.95, 1], "cam": cam,
               "shots": [{"name": name, "tracks": tracks, "frames": n, "fps": f, "warmup": 1.0}]}
        jp = os.path.join(a.out, f"job_{name}.json")
        json.dump(job, open(jp, "w"), indent=1)
        subprocess.run(["node", os.path.join(HERE, "spine-render.mjs"), jp, a.out], check=True)
        fdir = os.path.join(a.out, name)
        # 左上角写片段名
        for fn in ([] if a.no_label else sorted(os.listdir(fdir))):
            if fn.endswith(".png"):
                p = os.path.join(fdir, fn)
                im = Image.open(p).convert("RGB")
                ImageDraw.Draw(im).text((10, 8), name, fill=(60, 60, 70))
                im.save(p)
        seg = os.path.join(a.out, f"{name}.mp4")
        vf = "pad=720:1040:(ow-iw)/2:(oh-ih)/2:color=0xEDEDF2" if size != [720, 1040] else "null"
        subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(f), "-i", os.path.join(fdir, "f%04d.png"),
                        "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", seg], check=True)
        segs.append(seg)
    lst = os.path.join(a.out, "concat.txt")
    with open(lst, "w") as fh:
        for s in segs:
            fh.write(f"file '{os.path.abspath(s)}'\n".replace("\\", "/"))
    final = os.path.join(a.out, f"{a.name}_demo.mp4")
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", final], check=True)
    print("视频 →", final)


if __name__ == "__main__":
    main()
