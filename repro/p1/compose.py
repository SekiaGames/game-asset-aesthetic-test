"""把四件生成部件套到切件模板的骨架比例上，输出可直接喂给 spine-cutout-rig.py 的部件目录。

思路（= 计划里的「方案 A：把部件标定到模板尺寸」）：
- 每件按「目标跨度 / 实际跨度」单独缩放，锚点对到模板枢轴；
- 部件的关节位置由我给的跨度反推，所以骨架仍用模板的 NECK/SH/HIP/WAIST，
  只改 KNEE_Y / THIGH_LEN 两个数（见 rig-constants.json）；
- 直接产出 part_00..05，跳过「绿幕母版 → 色键切件」那一步：
  这些部件本身就是分开生成的透明图，再走一遍色键只会引入 ±4px 的 pad 偏移。

模板目标跨度（body 图坐标系，y 向下）：
  头顶 -116 / 颈 10 / 肩 48 / 腰 150 / 胯 222 / 膝 402 / 脚底 621
"""
import json
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CLEAN = os.path.join(HERE, "art", "clean")
OUT = os.path.join(HERE, "out", "parts")

NECK_Y = 10
HEAD_TOP = -116          # 头顶目标位置
BELT_Y = 150
HEM_Y = 390
SHOULDER_Y = 48
HIP_Y = 222
KNEE_Y = 402
SOLE_Y = 621

CANVAS = {"head": (170, 144), "body": (176, 410), "arm": (66, 305), "leg": (160, 412)}
LEG_AXIS_X = 70      # 腿图里的腿轴线 x（= 补丁里的 P["leg-upper/lower"] x）


def fill_holes(im, min_area=30):
    """把部件内部封闭的透明洞（袖窿、腋下）用最近的不透明颜色补上。
    不封闭的开口（领口）不会被填，因为洪水会从边缘连出去。"""
    from scipy import ndimage
    a = np.array(im)
    solid = a[..., 3] > 8
    lab, n = ndimage.label(~solid)
    if not n:
        return im
    edge = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])
    sizes = ndimage.sum(~solid, lab, range(1, n + 1))
    fill = np.zeros_like(solid)
    for i in range(1, n + 1):
        if i not in edge and sizes[i - 1] >= min_area:
            fill |= (lab == i)
    if not fill.any():
        return im
    _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
    a[..., :3][fill] = a[..., :3][iy, ix][fill]
    a[..., 3][fill] = 255
    return Image.fromarray(a, "RGBA")


def load(name):
    return fill_holes(Image.open(os.path.join(CLEAN, f"{name}.png")).convert("RGBA"))


def trim(im):
    bb = im.getbbox()
    return im.crop(bb), bb


def belt_row(im):
    """裙子图里腰带那一行：棕色像素最多的一段的中位行。"""
    a = np.array(im)
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    brown = (a[..., 3] > 200) & (r > 120) & (r < 210) & (g > 80) & (g < 160) & (b < 120)
    rows = brown.sum(1)
    if rows.max() < 20:
        return None
    lo, hi = int(im.height * 0.25), int(im.height * 0.75)
    band = np.argmax(rows[lo:hi]) + lo
    ys = [y for y in range(max(0, band - 6), min(im.height, band + 7)) if rows[y] > rows.max() * 0.5]
    return int(np.mean(ys)), int(np.median(np.where(brown[int(np.mean(ys))])[0]))


def place(part, k, anchor_src, anchor_dst, canvas):
    """按比例 k 缩放，使 anchor_src（部件图坐标）落在画布 anchor_dst 上。"""
    w = max(1, round(part.width * k))
    h = max(1, round(part.height * k))
    im = part.resize((w, h), Image.LANCZOS)
    ax, ay = anchor_src[0] * k, anchor_src[1] * k
    dst = Image.new("RGBA", canvas, (0, 0, 0, 0))
    dst.alpha_composite(im, (round(anchor_dst[0] - ax), round(anchor_dst[1] - ay)))
    return dst


def main():
    os.makedirs(OUT, exist_ok=True)
    info = {}

    # ---- 头：头顶对齐 HEAD_TOP，颈底对齐 NECK_Y ----
    head, _ = trim(load("head"))
    k = (NECK_Y - HEAD_TOP) / head.height
    # 锚点必须用「部件图里的枢轴坐标」(83,128)，不是世界坐标 NECK_Y
    img = place(head, k, (head.width / 2, head.height), (83, 128), CANVAS["head"])
    img.save(os.path.join(OUT, "part_00.png"))
    info["head"] = {"scale": round(k, 4), "pivot": [83, 128]}

    # ---- 身：腰带对齐 BELT_Y，裙摆对齐 HEM_Y ----
    body, _ = trim(load("dress"))
    br = belt_row(body)
    belt_y, belt_x = br if br else (int(body.height * 0.35), body.width // 2)
    k = (HEM_Y - BELT_Y) / max(1, body.height - belt_y)
    img = place(body, k, (belt_x, belt_y), (78, BELT_Y), CANVAS["body"])
    img.save(os.path.join(OUT, "part_01.png"))
    info["body"] = {"scale": round(k, 4), "pivot": [78, 150], "belt_row": belt_y}

    # ---- 臂：肩顶对齐 20，手尖对齐 300 ----
    arm, _ = trim(load("arm"))
    k = 280.0 / arm.height
    img = place(arm, k, (arm.width / 2, 0), (35, 20), CANVAS["arm"])
    img.save(os.path.join(OUT, "part_02.png"))
    info["arm"] = {"scale": round(k, 4), "pivot_top": [35, 20]}

    # ---- 腿：按腿轴线对齐（不是 bbox 中心，靴子向前伸很长），脚底对齐 409 ----
    leg, _ = trim(load("leg"))
    k = 401.0 / leg.height
    a = np.array(leg)
    skin = (a[..., 3] > 200) & (a[..., 0] > 225) & (a[..., 1] > 195) & (a[..., 2] > 165) & (a[..., 2] < 215)
    rows = skin[: int(leg.height * 0.30)]
    axis = float(np.median(np.where(rows)[1])) if rows.any() else leg.width / 2
    img = place(leg, k, (axis, leg.height), (LEG_AXIS_X, 409), CANVAS["leg"])
    img.save(os.path.join(OUT, "part_04.png"))
    info["leg"] = {"scale": round(k, 4), "axis_part_x": round(axis, 1), "pivot_top": [LEG_AXIS_X, 8]}

    # 远侧：模板只读 00/01/02/04，03/05 占位
    for src, dst in (("part_02.png", "part_03.png"), ("part_04.png", "part_05.png")):
        Image.open(os.path.join(OUT, src)).save(os.path.join(OUT, dst))

    # 拼一张 exploded 预览，方便肉眼核对比例
    sheet = Image.new("RGBA", (700, 440), (44, 48, 60, 255))
    x = 20
    for i, name in enumerate(["part_00", "part_01", "part_02", "part_04"]):
        im = Image.open(os.path.join(OUT, f"{name}.png"))
        sheet.alpha_composite(im, (x, 20))
        x += im.width + 16
    sheet.save(os.path.join(HERE, "out", "exploded.png"))

    # 骨架需要改的两个数：膝盖在腿图里的位置（胯 8 + 大腿长），大腿长取胯到脚底的 44.4%
    # （参考图实测 328/738，和模板的 180/399 一致）
    thigh = round((CANVAS["leg"][1] - 8 - 3) * 0.444)
    knee_y = 8 + thigh
    json.dump({"KNEE_Y": knee_y, "THIGH_LEN": thigh,
               "P_leg_upper": [LEG_AXIS_X, 8], "P_leg_lower": [LEG_AXIS_X, 12],
               "GROUND_expected": HIP_Y + thigh + (CANVAS["leg"][1] - knee_y) - 4,
               "parts": info}, open(os.path.join(HERE, "rig-constants.json"), "w"), indent=1)
    print(json.dumps(info, indent=1))
    print("KNEE_Y", knee_y, "THIGH_LEN", thigh, "GROUND", HIP_Y + thigh + (CANVAS["leg"][1] - knee_y) - 4)


if __name__ == "__main__":
    main()
