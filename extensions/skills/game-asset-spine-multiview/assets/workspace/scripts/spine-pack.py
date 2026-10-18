"""Pack a rig's part PNGs into a Spine atlas and write a self-contained preview page.

Usage: python -I scripts/spine-pack.py <rig_dir> [--name kurumi] [--anim run]
Reads <rig_dir>/images/*.png (region name = file stem, must match attachment names in
<rig_dir>/<name>.json). Writes <name>.png, <name>.atlas (Spine 4.x "bounds:" format) and
preview.html (official spine-player 4.2 from unpkg, data embedded as data: URIs, so it
opens from file:// but needs internet for the player script).
"""
import argparse
import base64
import glob
import json
import os

import numpy as np
from PIL import Image
from scipy import ndimage

BLEED_PAD = 3


def bleed(im):
    """透明像素的 RGB 填成最近的不透明像素颜色（Spine 官方打包器默认开的 Bleed 选项），
    再往外复制 BLEED_PAD 像素边（alpha 仍为 0）：线性过滤采到边缘时不会混进黑色 / 绿色，
    否则轮廓上会出现一串深色小点（2026-10-09 kurumi 正面在 ryza app 里实测：透明处 RGB 均值 (8,7,7)）。"""
    a = np.array(im)
    rgb, al = a[..., :3], a[..., 3]
    solid = al > 0
    if solid.any() and not solid.all():
        _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
        rgb = rgb[iy, ix]
    p = BLEED_PAD
    rgb = np.pad(rgb, ((p, p), (p, p), (0, 0)), mode="edge")
    al = np.pad(al, ((p, p), (p, p)))
    return Image.fromarray(np.dstack([rgb, al]).astype(np.uint8), "RGBA")


MAX_PAGE = 4096  # 手机 WebGL 常见上限；ryza 官方图集单页也是 4096 宽
NL = chr(10)


def bleed_page(page):
    """整页的透明像素 RGB 都填成最近切件的颜色：mipmap 逐级平均时，切件之间的黑色空隙不会渗成暗边。"""
    a = np.array(page)
    solid = a[..., 3] > 0
    if solid.any() and not solid.all():
        _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
        a[..., :3] = a[..., :3][iy, ix]
    return Image.fromarray(a, "RGBA")


def pack_page(order, side, pad):
    """货架式装箱：返回装进 side×side 的 {名字: (x, y)} 和装不下的剩余项。"""
    x = y = shelf_h = 0
    pos, rest = {}, []
    for name, im in order:
        w, h = im.width + pad, im.height + pad
        if x + w > side:
            x, y, shelf_h = 0, y + shelf_h, 0
        if y + h > side or w > side:
            rest.append((name, im))
            continue
        pos[name] = (x + pad // 2, y + pad // 2)
        x += w
        shelf_h = max(shelf_h, h)
    return pos, rest


def pack(images, pad=2 * BLEED_PAD + 2):
    """装成若干页：每页取能装下剩余全部的最小 2 的幂正方形，超过 MAX_PAGE 就装满一页 MAX_PAGE 再开下一页。"""
    order = sorted(images.items(), key=lambda kv: -kv[1].height)
    pages = []
    while order:
        side = 64
        while side < MAX_PAGE:
            pos, rest = pack_page(order, side, pad)
            if not rest:
                break
            side *= 2
        pos, rest = pack_page(order, side, pad)
        if not pos:
            raise SystemExit(f"有切件超过 {MAX_PAGE}px，装不进图集")
        pages.append((side, pos))
        order = rest
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rig_dir")
    ap.add_argument("--name", default="kurumi")
    ap.add_argument("--anim", default=None, help="animation to play first")
    ap.add_argument("--images", default=None,
                    help="切件目录（默认 <rig_dir>/images）。可指向放大后的同名切件：网格按 UV 比例取图、"
                         "区域附件按 JSON 里的 width/height 显示，贴图像素数变了骨骼 JSON 不用改")
    ap.add_argument("--filter", default="MipMapLinearLinear,Linear",
                    help="atlas 过滤方式。默认开 mipmap：贴图比显示大时（高清切件缩小显示）描线不再断成虚线，"
                         "2026-10-09 实测缩小渲染高频能量 366 → 182；多占约 1/3 显存。Linear,Linear = 不开")
    a = ap.parse_args()

    images = {os.path.splitext(os.path.basename(p))[0]: Image.open(p).convert("RGBA")
              for p in sorted(glob.glob(os.path.join(a.images or os.path.join(a.rig_dir, "images"), "*.png")))}
    pages = pack(images)
    blocks, page_files = [], []
    for k, (side, pos) in enumerate(pages):
        fname = f"{a.name}.png" if k == 0 else f"{a.name}_{k + 1}.png"
        page = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        lines = [fname, f"size:{side},{side}", f"filter:{a.filter}"]
        for name in sorted(pos):
            x, y = pos[name]
            im = images[name]
            page.paste(bleed(im), (x - BLEED_PAD, y - BLEED_PAD))
            lines += [name, f"bounds:{x},{y},{im.width},{im.height}"]
        page = bleed_page(page)
        page.save(os.path.join(a.rig_dir, fname))
        blocks.append(NL.join(lines))
        page_files.append(fname)
    atlas = (NL + NL).join(blocks) + NL
    with open(os.path.join(a.rig_dir, f"{a.name}.atlas"), "w", newline=NL) as f:
        f.write(atlas)
    side = pages[0][0]

    def uri(path, mime):
        with open(path, "rb") as f:
            return f"data:{mime};base64," + base64.b64encode(f.read()).decode()

    skel_path = os.path.join(a.rig_dir, f"{a.name}.json")
    with open(skel_path, encoding="utf-8") as f:
        anims = list(json.load(f).get("animations", {}))
    raw = {
        f"{a.name}.json": uri(skel_path, "application/json"),
        f"{a.name}.atlas": "data:text/plain;base64," + base64.b64encode(atlas.encode()).decode(),
    }
    for fname in page_files:
        raw[fname] = uri(os.path.join(a.rig_dir, fname), "image/png")
    cfg = {"skeleton": f"{a.name}.json", "atlas": f"{a.name}.atlas", "rawDataURIs": raw,
           "animation": a.anim or (anims[0] if anims else None), "showControls": True,
           "premultipliedAlpha": False, "backgroundColor": "#282c3cff"}
    html = f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{a.name} rig preview</title>
<link rel="stylesheet" href="https://unpkg.com/@esotericsoftware/spine-player@4.2.*/dist/spine-player.css">
<script src="https://unpkg.com/@esotericsoftware/spine-player@4.2.*/dist/iife/spine-player.js"></script>
<style>body{{margin:0;background:#1c1f2b;color:#ccd;font:14px sans-serif}}#bar{{padding:8px;display:flex;gap:6px;flex-wrap:wrap}}
button{{background:#3a4060;color:#fff;border:0;padding:6px 12px;border-radius:4px;cursor:pointer}}#p{{width:100%;height:calc(100vh - 50px)}}</style>
</head><body><div id="bar"></div><div id="p"></div>
<script>
const cfg = {json.dumps(cfg)};
cfg.success = p => {{
  const bar = document.getElementById('bar');
  for (const n of {json.dumps(anims)}) {{
    const b = document.createElement('button'); b.textContent = n;
    b.onclick = () => p.setAnimation(n, true); bar.appendChild(b);
  }}
}};
cfg.error = (p, r) => {{ document.getElementById('bar').textContent = 'Error: ' + r; }};
new spine.SpinePlayer('p', cfg);
</script></body></html>
"""
    with open(os.path.join(a.rig_dir, "preview.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"atlas {len(pages)} 页 {[p[0] for p in pages]}, {len(images)} regions; preview.html with {anims}")


if __name__ == "__main__":
    main()
