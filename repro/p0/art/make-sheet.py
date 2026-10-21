"""P0 冒烟测试用的合成部件图（不是美术资源）。

目的：验证"切件 → 绑骨 → 打包 → 官方 4.2 运行时"这条链路。
坐标按 game-asset-spine-cutout 模板的常量画（body 图左上角 = 原点）：
NECK(56,10) SH(68,48) HIP(82,222) WAIST(78,150) BELT=124 ELBOW_Y=150 KNEE_Y=50。

两个关键约束（否则 parts.py 会把顺序和枢轴搞错）：
1. 每个部件的内容必须顶到自己的画布四边 —— parts.py 按 bbox+pad 裁剪，只要 bbox==画布，
   六张部件图的裁剪偏移就完全一致，枢轴常量的相对关系不变。
2. 竖排、左边缘都对齐到同一个 x —— parts.py 先按 x//50 分桶再按 y 排序，竖排才能保证顺序。
"""
import os

from PIL import Image, ImageDraw

S = 4  # 超采样
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sheet.png")
MARGIN, GAP = 10, 30

SKIN = (242, 207, 176, 255)
DRESS = (244, 244, 248, 255)
HAIR = (233, 169, 196, 255)
SHOE = (139, 46, 63, 255)
BELT = (168, 40, 52, 255)
LINE = (74, 58, 58, 255)
LW = 3


def canvas(w, h):
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def finish(im, name, w, h):
    im = im.resize((w, h), Image.LANCZOS)
    bb = im.getbbox()
    assert bb == (0, 0, w, h), f"{name} bbox {bb} != {(0, 0, w, h)}"
    return im


def head():
    w, h = 170, 144
    im, d = canvas(w, h)
    d.rectangle([72 * S, 96 * S, 94 * S, h * S], fill=SKIN)
    d.ellipse([0, 0, w * S, 130 * S], fill=HAIR)
    d.ellipse([20 * S, 22 * S, 140 * S, 122 * S], fill=SKIN)
    d.polygon([(128 * S, 64 * S), (143 * S, 80 * S), (126 * S, 84 * S)], fill=SKIN)
    d.ellipse([104 * S, 60 * S, 114 * S, 72 * S], fill=LINE)
    d.arc([102 * S, 86 * S, 124 * S, 104 * S], 20, 150, fill=LINE, width=LW * S)
    d.ellipse([-4 * S, -6 * S, 96 * S, 46 * S], fill=HAIR)
    d.line([(72 * S, 96 * S), (72 * S, h * S)], fill=LINE, width=LW * S)
    d.line([(94 * S, 96 * S), (94 * S, h * S)], fill=LINE, width=LW * S)
    return finish(im, "head", w, h)


def body():
    w, h = 176, 262
    im, d = canvas(w, h)
    d.polygon([(66 * S, 0), (96 * S, 0), (100 * S, 56 * S), (62 * S, 56 * S)], fill=SKIN)
    d.polygon([(28 * S, 52 * S), (148 * S, 52 * S), (156 * S, 126 * S),
               (176 * S, h * S), (0, h * S), (20 * S, 126 * S)],
              fill=DRESS, outline=LINE, width=LW * S)
    d.rectangle([19 * S, 121 * S, 157 * S, 127 * S], fill=BELT)
    return finish(im, "body", w, h)


def arm():
    w, h = 66, 300
    im, d = canvas(w, h)
    d.ellipse([0, 0, w * S, 54 * S], fill=SKIN)
    d.rounded_rectangle([10 * S, 30 * S, 56 * S, 156 * S], radius=14 * S, fill=SKIN)
    d.rounded_rectangle([13 * S, 146 * S, 53 * S, 286 * S], radius=12 * S, fill=SKIN)
    d.ellipse([8 * S, 274 * S, 60 * S, h * S], fill=SKIN)
    d.line([(10 * S, 40 * S), (10 * S, 150 * S)], fill=LINE, width=LW * S)
    d.line([(56 * S, 40 * S), (56 * S, 150 * S)], fill=LINE, width=LW * S)
    return finish(im, "arm", w, h)


def leg():
    w, h = 64, 273
    im, d = canvas(w, h)
    d.rectangle([0, 0, w * S, 54 * S], fill=SKIN)
    d.polygon([(10 * S, 50 * S), (54 * S, 50 * S), (46 * S, 248 * S), (20 * S, 248 * S)], fill=SKIN)
    d.polygon([(20 * S, 240 * S), (48 * S, 240 * S), (w * S, 266 * S), (w * S, h * S), (20 * S, h * S)],
              fill=SHOE)
    d.line([(10 * S, 54 * S), (20 * S, 246 * S)], fill=LINE, width=LW * S)
    d.line([(54 * S, 54 * S), (46 * S, 246 * S)], fill=LINE, width=LW * S)
    return finish(im, "leg", w, h)


def main():
    parts = {"head": head(), "body": body(), "arm": arm(), "leg": leg()}
    order = ["head", "body", "arm", "arm", "leg", "leg"]
    width = MARGIN * 2 + max(p.width for p in parts.values())
    height = MARGIN * 2 + sum(parts[n].height for n in order) + GAP * (len(order) - 1)
    sheet = Image.new("RGB", (width, height), (0, 255, 0))
    y = MARGIN
    for n in order:
        im = parts[n]
        sheet.paste(im, (MARGIN, y), im)
        y += im.height + GAP
    sheet.save(OUT)
    print(f"{OUT} {width}x{height}")
    print("expected parts.py order:", ", ".join(
        ["00 head", "01 body", "02 arm", "03 arm(far)", "04 leg", "05 leg(far)"]))


if __name__ == "__main__":
    main()
