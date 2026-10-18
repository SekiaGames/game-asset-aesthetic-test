"""把若干张图按行拼成一张对比图（灰底），检查渲染结果用。
    python contact-sheet.py <out.png> --rows "标签:a.png,b.png,..." "标签2:..." [--h 420] [--crop x0,y0,x1,y1（0–1 比例，统一裁每张）]
"""
import argparse
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--rows", nargs="+", required=True)
ap.add_argument("--h", type=int, default=420)
ap.add_argument("--crop")
a = ap.parse_args()
rows = []
for r in a.rows:
    label, _, files = r.partition(":")
    ims = []
    for f in files.split(","):
        im = Image.open(f).convert("RGBA")
        if a.crop:
            c = [float(v) for v in a.crop.split(",")]
            im = im.crop((int(c[0] * im.width), int(c[1] * im.height), int(c[2] * im.width), int(c[3] * im.height)))
        im = im.resize((max(1, round(im.width * a.h / im.height)), a.h))
        ims.append(im)
    rows.append((label, ims))
W = max(sum(i.width for i in ims) + 8 * len(ims) for _, ims in rows) + 8
H = sum(a.h + 26 for _ in rows) + 8
c = Image.new("RGBA", (W, H), (190, 190, 190, 255))
d = ImageDraw.Draw(c)
y = 4
for label, ims in rows:
    d.text((8, y), label, fill=(0, 0, 0, 255))
    x = 8
    for im in ims:
        c.alpha_composite(im, (x, y + 20))
        x += im.width + 8
    y += a.h + 26
c.convert("RGB").save(a.out)
print(a.out, c.size)
