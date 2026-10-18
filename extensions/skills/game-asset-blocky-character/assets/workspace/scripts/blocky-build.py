"""方块风角色：部件表 JSON → 像素贴图图集 + Blockbench MCP bbmodel_edit 操作表。

自写胶水（headless Blockbench MCP 没有贴图模板 / 画笔工具）：
- 每个方块的每个面按统一像素密度（texel_per_unit）分到图集里自己的一块，不拉伸、不共用。
- 面的颜色来自「材质」：平涂 fill、上下渐变 gradient、竖条纹 vstripes、底部横带 hband、顶部横带 tband、
  中间竖面板 panel、按列随机深浅 streaks、全局像素明暗 shade（暗边 / 顶边提亮 / 颗粒）、头发高光带 hl、描边 frame、轻噪声 noise；可再叠 ASCII 像素贴花（decal，调色板字母；'.' 保留底色，'-' 透明）。
- 只用方块（YSM / 基岩版几何不支持网格），骨骼即 groups。

建模、校验、导出、渲染交给 extensions/mcp/blockbench-mcp（headless）。

用法：
  python scripts/blocky-build.py config/blocky/deepseek-chan.json \
      --out output/blocky/deepseek-chan --bbmodel projects/game-aesthetic-asset/output/blocky/deepseek-chan/deepseek-chan.bbmodel
输出：<out>/atlas.png、<out>/ops.json、<out>/atlas_preview.png、<out>/meta.json
"""
import argparse
import json
import math
import random
from pathlib import Path

from PIL import Image

FACES = ["north", "south", "east", "west", "up", "down"]


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def face_dims(fr, to, face):
    dx, dy, dz = (to[i] - fr[i] for i in range(3))
    return {"north": (dx, dy), "south": (dx, dy), "east": (dz, dy), "west": (dz, dy),
            "up": (dx, dz), "down": (dx, dz)}[face]


class Painter:
    def __init__(self, spec):
        self.pal = {k: hex2rgb(v) for k, v in spec["palette"].items()}
        self.mats = spec["materials"]
        self.rng = random.Random(7)
        # 全局像素明暗（材质可用 "shade": false 关掉，或给 dict 覆盖）
        self.shade = spec.get("shade", {"edge": 14, "top": 9, "noise": 6})

    def color(self, c):
        return self.pal[c] if c in self.pal else hex2rgb(c)

    def paint(self, w, h, mat_name, face, decal=None):
        if mat_name.startswith("#"):
            m = {"fill": mat_name}  # 纯色直写（生成器给每块单独配色时用）
        else:
            m = self.mats[mat_name]
        if "inherit" in m:
            base = dict(self.mats[m["inherit"]])
            base.update({k: v for k, v in m.items() if k != "inherit"})
            m = base
        img = Image.new("RGBA", (w, h))
        px = img.load()
        top = self.color(m.get("gradient", [m.get("fill")])[0])
        bot = self.color(m.get("gradient", [None, m.get("fill")])[-1])
        noise = m.get("noise", 0)
        side_faces = face in ("north", "south", "east", "west")
        for y in range(h):
            t = (y + 0.5) / h if side_faces else 0.0
            c = lerp(top, bot, t) if side_faces else (top if face == "up" else bot)
            for x in range(w):
                n = int(self.rng.uniform(-noise, noise) * 255) if noise else 0
                px[x, y] = tuple(max(0, min(255, v + n)) for v in c) + (255,)
        if side_faces and "vstripes" in m:
            s = m["vstripes"]
            col = self.color(s["color"])
            for x in range(s.get("offset", 0), w, s["every"]):
                for y in range(h):
                    px[x, y] = col + (255,)
        if side_faces and "plaid" in m:
            # Pixel tartan, repeated in face UV space. No copied character artwork.
            p = m["plaid"]; period = p.get("period", 6)
            for y in range(h):
                for x in range(w):
                    a, b = x % period, y % period
                    if a == 0 or b == 0:
                        col = self.color(p["line"])
                    elif a < period // 2 and b < period // 2:
                        col = self.color(p["dark"])
                    elif a >= period // 2 and b >= period // 2:
                        col = self.color(p["light"])
                    else:
                        continue
                    px[x, y] = col + (255,)
        if side_faces and "streaks" in m:
            # 发丝：每列按确定性哈希取 加深 / 不变 / 提亮（比固定间隔竖条自然）
            st_ = m["streaks"]
            amt = st_.get("amount", 18)
            for x in range(w):
                hsh = (x * 73856093 ^ (w * 19349663) ^ (h * 83492791)) % 7
                f = -1 if hsh in (0, 3) else (1 if hsh == 5 else 0)
                if f == 0:
                    continue
                for y in range(h):
                    r_, g_, b_, a_ = px[x, y]
                    px[x, y] = (max(0, min(255, r_ + f * amt)), max(0, min(255, g_ + f * amt)), max(0, min(255, b_ + f * amt)), a_)
        if side_faces and "panel" in m and face in m["panel"].get("faces", ["north"]):
            p = m["panel"]
            pw = max(1, int(round(w * p["width_frac"])))
            x0 = (w - pw) // 2
            for x in range(x0, x0 + pw):
                stripe = "stripe" in p and (x - x0) % p.get("every", 2) == 1
                col = self.color(p["stripe"] if stripe else p["color"])
                for y in range(h):
                    px[x, y] = col + (255,)
            if "edge" in p:
                ec = self.color(p["edge"])
                for y in range(h):
                    px[x0, y] = ec + (255,)
                    px[x0 + pw - 1, y] = ec + (255,)
        if side_faces:
            for band in m.get("tband", []):
                col = self.color(band["color"])
                for r in range(band.get("rows", 1)):
                    y = band.get("from_top", 0) + r
                    if 0 <= y < h:
                        for x in range(w):
                            if band.get("dots") and (x + r) % band["dots"]:
                                continue
                            px[x, y] = col + (255,)
            for band in m.get("hband", []):
                col = self.color(band["color"])
                for r in range(band.get("rows", 1)):
                    y = h - 1 - band["from_bottom"] - r
                    if 0 <= y < h:
                        for x in range(w):
                            if band.get("dots") and (x + r) % band["dots"]:
                                continue
                            px[x, y] = col + (255,)
        if "frame" in m and side_faces:
            fc = self.color(m["frame"])
            for x in range(w):
                px[x, h - 1] = fc + (255,)
            if m.get("frame_all"):
                for x in range(w):
                    px[x, 0] = fc + (255,)
                for y in range(h):
                    px[0, y] = fc + (255,)
                    px[w - 1, y] = fc + (255,)
        if "scallop" in m and side_faces:
            sc = self.color(m["scallop"])
            for x in range(0, w, 2):
                px[x, h - 1] = sc + (255,)
        sh = m.get("shade", self.shade)
        if sh:
            self.shade_pass(px, w, h, face, sh, m.get("hl"))
        if decal:
            rows = decal["rows"]
            dw = len(rows[0])
            assert all(len(r) == dw for r in rows), f"decal rows uneven in {mat_name}/{face}"
            ax, ay = decal.get("at", ["center", "center"])
            x0 = (w - dw) // 2 if ax == "center" else (ax if ax >= 0 else w - dw + ax + 1)
            y0 = (h - len(rows)) // 2 if ay == "center" else (ay if ay >= 0 else h - len(rows) + ay + 1)
            for j, row in enumerate(rows):
                for i, ch in enumerate(row):
                    if ch == "." or not (0 <= x0 + i < w and 0 <= y0 + j < h):
                        continue
                    if ch == "-":  # 透明（刘海锯齿、镂空）
                        px[x0 + i, y0 + j] = (0, 0, 0, 0)
                        continue
                    px[x0 + i, y0 + j] = self.color(ch) + (255,)
        return img


def _adj(c, d):
    return tuple(max(0, min(255, v + d)) for v in c[:3]) + (c[3],)


def _shade_pass(self, px, w, h, face, sh, hl):
    """像素明暗：侧面底边 / 两侧压暗、顶边提亮，2×2 小块颗粒；头发再加一条断续高光带。"""
    side = face in ("north", "south", "east", "west")
    edge, top, noise = sh.get("edge", 0), sh.get("top", 0), sh.get("noise", 0)
    seed = (w * 7919 + h * 104729 + len(face) * 31) & 0xFFFF
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            if c[3] == 0:
                continue
            dlt = 0
            if noise:
                hsh = ((x // 2) * 73856093 ^ (y // 2) * 19349663 ^ seed * 83492791) % 5
                dlt += (hsh - 2) * noise // 2
            if side and w >= 3 and h >= 3:
                if y == h - 1:
                    dlt -= edge
                elif y == 0:
                    dlt += top
                if x == 0 or x == w - 1:
                    dlt -= edge // 2
            elif face == "up":
                dlt += top // 2
            elif face == "down":
                dlt -= edge
            px[x, y] = _adj(c, dlt)
    if hl and side and h >= 5 and w >= 2 and seed % 3:
        # 每个面高度错开、约三分之一不画，避免连成一圈虚线
        yy = int(h * (hl.get("at", 0.3) + ((seed % 5) - 2) * 0.05))
        col = hex2rgb(hl["color"])
        for x in range(w):
            if ((x * 5 + seed) % 9) == 0:
                continue
            for r in range(hl.get("rows", 1)):
                if 0 <= yy + r < h and px[x, yy + r][3]:
                    px[x, yy + r] = col + (255,)


Painter.shade_pass = _shade_pass


def mirror_cube(c):
    """X 镜像（_R ↔ _L）：from/to/origin 取反 X，Z 旋转、Y 旋转取反，east/west 面互换。"""
    m = json.loads(json.dumps(c))
    m["name"] = c["name"].replace("_R", "_L") if "_R" in c["name"] else c["name"] + "_m"
    if "group" in m:
        m["group"] = m["group"].replace("_R", "_L")
    m["from"], m["to"] = [-c["to"][0], c["from"][1], c["from"][2]], [-c["from"][0], c["to"][1], c["to"][2]]
    if "origin" in c:
        m["origin"] = [-c["origin"][0], c["origin"][1], c["origin"][2]]
    if "rotation" in c:
        r = c["rotation"]
        m["rotation"] = [r[0], -r[1], -r[2]]
    if "faces" in c:
        f = dict(c["faces"])
        if "east" in f or "west" in f:
            f["east"], f["west"] = c["faces"].get("west"), c["faces"].get("east")
            f = {k: v for k, v in f.items() if v is not None}
        m["faces"] = f
    m.pop("mirror", None)
    return m


def mirror_group(g):
    m = dict(g)
    m["name"] = g["name"].replace("_R", "_L")
    m["origin"] = [-g["origin"][0], g["origin"][1], g["origin"][2]]
    if "rotation" in g:
        r = g["rotation"]
        m["rotation"] = [r[0], -r[1], -r[2]]
    if "parent" in g:
        m["parent"] = g["parent"].replace("_R", "_L")
    m.pop("mirror", None)
    return m


def pack(images, width):
    order = sorted(images, key=lambda k: (-images[k].height, -images[k].width))
    pos, x, y, row_h = {}, 0, 0, 0
    for k in order:
        im = images[k]
        if x + im.width > width:
            x, y, row_h = 0, y + row_h, 0
        pos[k] = (x, y)
        x += im.width
        row_h = max(row_h, im.height)
    return pos, y + row_h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--out", required=True)
    ap.add_argument("--bbmodel", required=True)
    args = ap.parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tpu = spec["texel_per_unit"]
    painter = Painter(spec)

    groups = []
    for g in spec["groups"]:
        groups.append(g)
        if g.get("mirror"):
            groups.append(mirror_group(g))
    cubes = []
    for c in spec["cubes"]:
        cubes.append(c)
        if c.get("mirror"):
            cubes.append(mirror_cube(c))
    names = [c["name"] for c in cubes]
    dup = {n for n in names if names.count(n) > 1}
    assert not dup, f"duplicate cube names: {dup}"

    face_imgs = {}
    for c in cubes:
        faces_cfg = c.get("faces", {})
        for fn in FACES:
            if fn in c.get("hide", []):
                continue
            cfg = faces_cfg.get(fn, c["mat"])
            if isinstance(cfg, str):
                cfg = {"mat": cfg}
            mat = cfg.get("mat", c["mat"])
            decal = None
            if "decal" in cfg:
                decal = {"rows": spec["decals"][cfg["decal"]], "at": cfg.get("at", ["center", "center"])}
            fw, fh = face_dims(c["from"], c["to"], fn)
            # Optional higher density for details requested by the user (e.g. fine hair).
            face_tpu = spec.get("materials", {}).get(mat, {}).get("texel_per_unit", tpu)
            w, h = max(1, int(round(fw * face_tpu))), max(1, int(round(fh * face_tpu)))
            face_imgs[(c["name"], fn)] = painter.paint(w, h, mat, fn, decal)

    width = spec.get("atlas_width", 256)
    pos, height = pack(face_imgs, width)
    H = max(16, 1 << math.ceil(math.log2(max(height, 1))))
    W = max(width, H) if spec.get("square_atlas", True) else width
    H = max(H, W) if spec.get("square_atlas", True) else H
    atlas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for k, im in face_imgs.items():
        atlas.paste(im, pos[k])
    atlas.save(out / "atlas.png")

    ops = [{"op": "set_model_properties", "resolution": {"width": W, "height": H}}]
    for g in groups:
        op = {"op": "add_group", "name": g["name"], "origin": g["origin"]}
        if g.get("rotation"):
            op["rotation"] = g["rotation"]
        if g.get("parent"):
            op["parent"] = g["parent"]
        ops.append(op)
    for c in cubes:
        faces = {}
        for fn in FACES:
            if (c["name"], fn) in face_imgs:
                x, y = pos[(c["name"], fn)]
                im = face_imgs[(c["name"], fn)]
                faces[fn] = {"uv": [x, y, x + im.width, y + im.height], "texture": "atlas"}
            else:
                faces[fn] = {"texture": None}
        op = {"op": "add_cube", "name": c["name"], "from": c["from"], "to": c["to"], "parent": c["group"], "faces": faces}
        if c.get("origin"):
            op["origin"] = c["origin"]
        if c.get("rotation"):
            op["rotation"] = c["rotation"]
        ops.append(op)
    (out / "ops.json").write_text(json.dumps({"file": args.bbmodel, "operations": ops}, indent=1), encoding="utf-8")
    meta = {"atlas": [W, H], "cubes": len(cubes), "groups": len(groups), "faces": len(face_imgs)}
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    prev = Image.new("RGBA", (W, H), (50, 50, 55, 255))
    prev.alpha_composite(atlas)
    prev.resize((W * 3, H * 3), Image.NEAREST).convert("RGB").save(out / "atlas_preview.png")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
