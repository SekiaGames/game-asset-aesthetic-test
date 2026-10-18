"""Quick side-view cutout rig: parts -> Spine 4.2 JSON + atlas images + preview GIFs.

Usage: python -I scripts/spine-cutout-rig.py <parts_raw_dir> <out_dir> [extra.anim.json ...] [--skirt] [--debug-skin]
extra.anim.json: animations made elsewhere (e.g. pose-to-rig.py), {"name": {"bones": ...}}; keys starting
with "_" are ignored.
--skirt: cut the body at the belt into a bodice (rigid, on the torso) and a skirt mesh weighted to
  skirt-front / skirt-back bones; their rotation is baked per animation from the legs (front panel
  pushed by the forward thigh, back panel by the backward one) through a damped spring that also
  reacts to the hip's vertical acceleration (see skirt_motion()).
--debug-skin: previews only — draw arms/legs as flat magenta to spot where body shows through cloth.
--base-body/--base-pose: cut the thigh out of a grey mannequin (Qwen edit of the standing pose,
  same outline) between the hip and knee of the standing pose's DWPose keypoints, scale it to the
  rig's thigh length and shin width, recolour the grey to the shin's skin tones, add the outline.
--weapon <dir>: spine-cutout-parts.py output of a katana sheet (part_00 drawn sword, tip to the right,
  part_01 empty scabbard, mouth on the left). Adds bones "scabbard" (mouth at the belt front) and
  "sword" (pivot at the upper grip), both children of the hip, and the attack animation from
  katana-action.py. Other animations keep the sword sheathed. The root bone gets a scale timeline
  (scaleX 1 -> -1 = turning round).
parts_raw_dir comes from spine-cutout-parts.py; part order is fixed for the
kurumi side-view sheet: 00 head, 01 body, 02/03 arms, 04/05 legs.
Layout is authored in pixel space (y down, body image top-left = 0,0);
Spine output converts to y-up with root at the feet.
All bones keep setup rotation 0, so a positive animated rotation is CCW:
a hanging limb swings its tip forward (+x, the character faces right).
"""
import argparse
import glob
import json
import math
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw

_ap = argparse.ArgumentParser()
_ap.add_argument("src")
_ap.add_argument("out")
_ap.add_argument("extra", nargs="*")
_ap.add_argument("--skirt", action="store_true")
_ap.add_argument("--debug-skin", action="store_true")
_ap.add_argument("--base-body", help="grey mannequin of the standing pose (aligned with it): its thigh replaces the stretched one")
_ap.add_argument("--base-pose", help="pose-extract.py poses.json of the standing pose (hip/knee positions; DWPose finds nothing on the mannequin itself)")
_ap.add_argument("--skirt-calib", help="skirt-measure.py output: fit the skirt gains to it")
_ap.add_argument("--calib-anim", default="run_video", help="animation the measured clip corresponds to")
_ap.add_argument("--calib-fps", type=float, default=24)
_ap.add_argument("--weapon", help="katana parts dir (part_00 sword, part_01 scabbard)")
_ap.add_argument("--weapon-scale", type=float, default=0.40, help="sword sheet px -> rig px")
_args = _ap.parse_args()
SRC, OUT, EXTRA, SKIRT, DEBUG_SKIN = _args.src, _args.out, _args.extra, _args.skirt, _args.debug_skin
IMG = os.path.join(OUT, "images")
os.makedirs(IMG, exist_ok=True)
for _old in glob.glob(os.path.join(IMG, "*.png")):  # the atlas packs everything in here
    os.remove(_old)


def load(i):
    return Image.open(os.path.join(SRC, f"part_{i:02d}.png")).convert("RGBA")


# ---- cut parts ---------------------------------------------------------------
head, body, arm, leg = load(0), load(1), load(2), load(4)
ELBOW_Y, KNEE_Y, THIGH_LEN = 150, 50, 180
BELT = 124  # belt rows 121-125 in the body image (dark red)
parts = {
    "head": head,
    "arm-upper": arm.crop((0, 0, arm.width, ELBOW_Y + 10)),
    "arm-lower": arm.crop((0, ELBOW_Y - 10, arm.width, arm.height)),
    "leg-lower": leg.crop((0, KNEE_Y - 12, leg.width, leg.height)),
    # the sheet's legs start at the knee: stretch the top band into a thigh
    "leg-upper": leg.crop((0, 8, leg.width, KNEE_Y + 4)).resize((leg.width, THIGH_LEN + 16), Image.LANCZOS),
}


def _ss(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


P_LEG_LOWER_X = 30   # shin pivot x inside the shin image (same as P["leg-lower"])


def thigh_from_mannequin(mpath, ppath, leg_img):
    """Returns (thigh RGBA, hip pivot (x, y)) with the knee THIGH_LEN below the hip pivot."""
    kp = json.load(open(ppath))[0]["kp"]
    hip = np.array([np.mean([kp[i][0] for i in (8, 11)]), np.mean([kp[i][1] for i in (8, 11)])])
    knee = np.array(kp[9][:2]) if kp[9] else np.array(kp[12][:2])
    a = np.array(Image.open(mpath).convert("RGB")).astype(int)
    mask = (a[..., 1] - np.maximum(a[..., 0], a[..., 2])) < 60
    pad = 14
    x0, x1 = int(hip[0] - 110), int(hip[0] + 110)     # wide enough not to cut the buttock
    y0, y1 = int(hip[1] - pad), int(knee[1] + pad)
    crop_m = mask[y0:y1, x0:x1]
    grey = a[y0:y1, x0:x1].mean(-1)
    # skin tones and outline colour from the shin image
    la = np.array(leg_img).astype(int)
    lv = la[..., 3] > 200
    lum = la[..., :3].mean(-1)
    skin = la[lv & (lum > 170)][:, :3]
    base = np.median(skin, 0)
    line = np.median(la[lv & (lum < 110)][:, :3], 0)
    ref = np.median(grey[crop_m])
    rgb = np.clip(base[None, None, :] * (grey / ref)[..., None] ** 1.2, 0, 255)
    m8 = crop_m.astype(np.uint8)
    edge = m8 - cv2.erode(m8, np.ones((5, 5), np.uint8))
    rgb[edge > 0] = line
    rgba = np.dstack([rgb, crop_m * 255]).astype(np.uint8)
    im = Image.fromarray(rgba, "RGBA")
    # scale: hip->knee to THIGH_LEN, knee width to the shin's top width
    sy = THIGH_LEN / (knee[1] - hip[1])
    kr = crop_m[int(knee[1] - y0) - 6]
    knee_w = np.ptp(np.where(kr)[0]) + 1
    shin_top = np.where(la[12, :, 3] > 128)[0]
    sx = (np.ptp(shin_top) + 1) / knee_w
    im = im.resize((max(1, round(im.width * sx)), max(1, round(im.height * sy))), Image.LANCZOS)
    pivot = ((hip[0] - x0) * sx, (hip[1] - y0) * sy)
    # taper the lower 45% so the knee meets the shin: each row is squeezed toward the shin's
    # width and its centre slid onto the knee axis (pivot x), smoothstep-blended
    arr = np.array(im)
    shin_w = np.ptp(shin_top) + 1
    shin_c = pivot[0] + (shin_top.mean() - P_LEG_LOWER_X)
    yk = pivot[1] + THIGH_LEN
    y_start = pivot[1] + 0.55 * THIGH_LEN
    H_ = arr.shape[0]
    L_, R_ = np.full(H_, np.nan), np.full(H_, np.nan)
    for y in range(H_):
        xs = np.where(arr[y, :, 3] > 128)[0]
        if len(xs) >= 2:
            L_[y], R_[y] = xs.min(), xs.max() + 1
    # smooth the per-row extents along y first: raw alpha extents are noisy and give a sawtooth edge
    ok = ~np.isnan(L_)
    k = np.ones(15) / 15
    pad_ = lambda v: np.convolve(np.pad(v, 7, mode="edge"), k, mode="valid")  # noqa: E731
    W0 = pad_(np.where(ok, R_ - L_, np.nanmedian(R_ - L_)))
    C0 = pad_(np.where(ok, (L_ + R_) / 2, np.nanmedian((L_ + R_) / 2)))
    out = arr.copy()
    for y in range(H_):
        if y < y_start or not ok[y]:
            continue
        t = _ss((y - y_start) / (yk - y_start))
        w1 = W0[y] + (shin_w - W0[y]) * t
        c1 = C0[y] + (shin_c - C0[y]) * t
        # map the smoothed source span [C0 - W0/2, C0 + W0/2] onto the target span
        src_l, src_r = C0[y] - W0[y] / 2, C0[y] + W0[y] / 2
        xs_t = np.arange(arr.shape[1]) + 0.5
        src_x = src_l + (xs_t - (c1 - w1 / 2)) * (W0[y] / max(w1, 1))
        inside = (src_x >= 0) & (src_x < arr.shape[1] - 1) & (xs_t >= c1 - w1 / 2) & (xs_t <= c1 + w1 / 2)
        row = np.zeros_like(arr[y])
        sx_i = np.clip(src_x, 0, arr.shape[1] - 1.001)
        i0 = np.floor(sx_i).astype(int)
        fr_ = (sx_i - i0)[:, None]
        interp_ = arr[y, i0].astype(float) * (1 - fr_) + arr[y, i0 + 1].astype(float) * fr_
        row[inside] = interp_[inside].astype(np.uint8)
        out[y] = row
    im = Image.fromarray(out, "RGBA")
    return im, pivot, {"thigh_px": float(knee[1] - hip[1]), "sx": round(float(sx), 3), "sy": round(float(sy), 3)}


if _args.base_body:
    parts["leg-upper"], _thigh_pivot, _thigh_info = thigh_from_mannequin(_args.base_body, _args.base_pose, parts["leg-lower"])
    print("thigh from mannequin", _thigh_info)
SKIRT_TOP = BELT - 6
if SKIRT:
    parts["bodice"] = body.crop((0, 0, body.width, BELT + 10))     # belt stays on the bodice, over the seam
    parts["skirt"] = body.crop((0, SKIRT_TOP, body.width, body.height))
else:
    parts["body"] = body


def prepare_weapon(wdir, k):
    """Sword + scabbard from the katana sheet. The scabbard is scaled to the blade length and each
    column shifted so its centre line follows the blade's (Qwen bent it more than the blade, so the
    sheathed blade poked out). Returns images, pivots (image px) and geometry in sword-bone space
    (rig px, y up, pivot = upper grip next to the guard)."""
    sw = Image.open(os.path.join(wdir, "part_00.png")).convert("RGBA")
    sc = Image.open(os.path.join(wdir, "part_01.png")).convert("RGBA")
    a = np.array(sw)[..., 3] > 128
    hgt = a.sum(0)
    cols = np.where(hgt > 0)[0]
    cy = np.array([np.where(a[:, x])[0].mean() if hgt[x] else np.nan for x in range(a.shape[1])])
    guard = np.where(hgt > 2.0 * np.median(hgt[cols]))[0]          # the tsuba is the only tall part
    g0, g1 = int(guard.min()), int(guard.max())
    bs = g1 + 1 + int(np.argmax(hgt[g1 + 1:] < 1.2 * np.median(hgt[g1 + 1:g1 + 200])))  # blade start
    tip, butt = int(cols.max()), int(cols.min())
    grip, far = g0 - 30, butt + int(0.25 * (g0 - butt))
    # smooth blade centre line (the tip narrows to a point)
    xb = np.arange(bs, tip + 1)
    cb = np.polyval(np.polyfit(xb[:-20], cy[bs:tip + 1][:-20], 3), np.arange(a.shape[1]))
    # scabbard: uniform scale to blade length + a little, then column shifts onto the blade line
    sa = np.array(sc)[..., 3] > 128
    sx0, sx1 = np.where(sa.any(0))[0][[0, -1]]
    sy0, sy1 = np.where(sa.any(1))[0][[0, -1]]
    sc = sc.crop((sx0, sy0, sx1 + 1, sy1 + 1))
    f = (tip - bs + 6) / sc.width
    # 1.35x thicker than the uniform scale: the curved blade slides out along a straight line, so
    # mid-draw it drifts ~8 sheet px off the scabbard's centre line and showed a silver edge
    sc = sc.resize((round(sc.width * f), round(sc.height * f * 1.35)), Image.LANCZOS)
    s_arr = np.array(sc)
    s_a = s_arr[..., 3] > 128
    pad = 30
    out = np.zeros((a.shape[0] + 2 * pad, s_arr.shape[1], 4), np.uint8)
    for i in range(s_arr.shape[1]):
        ys = np.where(s_a[:, i])[0]
        if not len(ys):
            continue
        want = cb[min(bs + i, len(cb) - 1)] + pad
        dy = int(round(want - (ys.min() + ys.max()) / 2))
        lo, hi = max(0, -dy), min(s_arr.shape[0], out.shape[0] - dy)
        out[lo + dy:hi + dy, i] = s_arr[lo:hi, i]
    sc = Image.fromarray(out, "RGBA")
    sw = sw.resize((round(sw.width * k), round(sw.height * k)), Image.LANCZOS)
    sc = sc.resize((round(sc.width * k), round(sc.height * k)), Image.LANCZOS)
    cg = cb[grip] if grip >= bs else cy[grip]

    def loc(x, y):  # sword sheet px -> sword-bone space
        return ((x - grip) * k, -(y - cg) * k)
    geo = {"far_grip": loc(far, cy[far]), "mouth": loc(bs, cb[bs]), "tip": loc(tip, cb[tip]),
           "blade_len": (tip - bs) * k, "guard": (g0, g1), "blade_start": bs, "scale": k}
    pivots = {"sword": (grip * k, cg * k), "scabbard": (0.0, (cb[bs] + pad) * k)}
    return sw, sc, pivots, geo


WEAPON = None
if _args.weapon:
    parts["sword"], parts["scabbard"], _wp, WEAPON = prepare_weapon(_args.weapon, _args.weapon_scale)
    print("weapon", {k_: (tuple(round(v, 1) for v in v_) if isinstance(v_, tuple) else v_) for k_, v_ in WEAPON.items()})
for k, im in parts.items():
    im.save(os.path.join(IMG, k + ".png"))

# ---- layout: pivots (pixel space, body top-left = origin) --------------------
NECK = (56, 10)
SH_NEAR, SH_FAR = (68, 48), (58, 46)
HIP_JOINT_NEAR, HIP_JOINT_FAR = (82, 222), (66, 220)
WAIST = (78, 150)
# pivot positions inside each image (image pixels)
P = {
    "head": (83, 128),
    "arm-upper": (35, 25), "arm-upper.elbow": (36, ELBOW_Y),
    "arm-lower": (36, 10),
    "leg-upper": (30, 8), "leg-upper.knee": (30, THIGH_LEN + 8),
    "leg-lower": (30, 12),
    "body": WAIST,  # body image top-left is the layout origin
    "bodice": WAIST,
}
if WEAPON:
    P.update(_wp)
if _args.base_body:
    P["leg-upper"] = tuple(round(v, 1) for v in _thigh_pivot)
GROUND = HIP_JOINT_NEAR[1] + THIGH_LEN + (leg.height - KNEE_Y) - 4
CX = WAIST[0]


def sp(pt):  # pixel -> spine (y up, root at feet centre)
    return pt[0] - CX, GROUND - pt[1]


def sub(a, b):
    return a[0] - b[0], a[1] - b[1]


bones, slots, atts = [], [], {}
BONE_WORLD = {}  # setup-pose world position (spine coords); all setup rotations are 0


def bone(name, parent, world_px, parent_world_px):
    BONE_WORLD[name] = sp(world_px)
    x, y = sub(sp(world_px), sp(parent_world_px)) if parent else sp(world_px)
    b = {"name": name, "x": round(x, 2), "y": round(y, 2)}
    if parent:
        b["parent"] = parent
    bones.append(b)


def attach(slot, bone_name, img_key, bone_world_px, img_pivot_px, img_pivot_key=None, color=None):
    im = parts[img_key]
    pv = P[img_pivot_key or img_key]
    # image top-left in world so that image pivot sits on the bone
    tl = sub(bone_world_px, pv)
    centre = (tl[0] + im.width / 2, tl[1] + im.height / 2)
    off = sub(sp(centre), sp(bone_world_px))
    s = {"name": slot, "bone": bone_name, "attachment": img_key}
    if color:
        s["color"] = color
    slots.append(s)
    atts[slot] = {img_key: {"x": round(off[0], 2), "y": round(off[1], 2),
                            "width": im.width, "height": im.height}}


def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def attach_mesh(slot, img_key, img_tl_px, weights_fn, nx=6, ny=6):
    """Grid mesh over the whole image, weighted per vertex by weights_fn(x, y) -> {bone: w}
    (image pixels). Spine weighted vertices: per vertex [n, (bone index, bind x, bind y, w) * n],
    bind = vertex in the bone's setup space. Hull (outline) vertices come first."""
    im = parts[img_key]
    w, h = im.width, im.height
    grid = {(i, j): (w * i / nx, h * j / ny) for i in range(nx + 1) for j in range(ny + 1)}
    hull = ([(i, 0) for i in range(nx + 1)] + [(nx, j) for j in range(1, ny + 1)]
            + [(i, ny) for i in range(nx - 1, -1, -1)] + [(0, j) for j in range(ny - 1, 0, -1)])
    order = hull + [(i, j) for j in range(1, ny) for i in range(1, nx)]
    idx = {k: n for n, k in enumerate(order)}
    tris = []
    for j in range(ny):
        for i in range(nx):
            a, b, c, d = idx[(i, j)], idx[(i + 1, j)], idx[(i + 1, j + 1)], idx[(i, j + 1)]
            tris += [a, b, c, a, c, d]
    bone_index = {b["name"]: n for n, b in enumerate(bones)}
    uvs, verts, vw = [], [], []
    for k in order:
        x, y = grid[k]
        uvs += [round(x / w, 5), round(y / h, 5)]
        world = sp((img_tl_px[0] + x, img_tl_px[1] + y))
        ws = {b: v for b, v in weights_fn(x, y).items() if v > 1e-4}
        tot = sum(ws.values())
        verts.append(len(ws))
        entry = []
        for b, v in ws.items():
            bx, by = BONE_WORLD[b]
            verts += [bone_index[b], round(world[0] - bx, 3), round(world[1] - by, 3), round(v / tot, 5)]
            entry.append((b, world[0] - bx, world[1] - by, v / tot))
        vw.append(entry)
    slots.append({"name": slot, "bone": "root", "attachment": img_key})
    atts[slot] = {img_key: {"type": "mesh", "uvs": uvs, "triangles": tris, "vertices": verts,
                            "hull": len(hull), "width": w, "height": h}}
    MESH_CACHE[slot] = (order, grid, tris, vw)


MESH_CACHE = {}
ROOT = (CX, GROUND)
bone("root", None, ROOT, None)
bone("hip", "root", WAIST, ROOT)
bone("torso", "hip", WAIST, WAIST)
bone("head", "torso", NECK, WAIST)
for side, sh in (("near", SH_NEAR), ("far", SH_FAR)):
    elbow = (sh[0] + 1, sh[1] + ELBOW_Y - 25)
    bone(f"{side}-upper-arm", "torso", sh, WAIST)
    bone(f"{side}-lower-arm", f"{side}-upper-arm", elbow, sh)
for side, hj in (("near", HIP_JOINT_NEAR), ("far", HIP_JOINT_FAR)):
    knee = (hj[0], hj[1] + THIGH_LEN)
    bone(f"{side}-upper-leg", "hip", hj, WAIST)
    bone(f"{side}-lower-leg", f"{side}-upper-leg", knee, hj)
if SKIRT:
    # skirt hangs from the torso (so the belt seam never opens); panels pivot at the belt edges
    _sk = np.array(parts["skirt"])[..., 3] > 128
    _xs = np.where(_sk[-12:].any(0))[0]
    SK_BACK_X, SK_FRONT_X = int(_xs.min()), int(_xs.max())        # hem extent, image x
    SKIRT_ROOT, SK_FRONT, SK_BACK = (84, BELT), (108, BELT + 4), (60, BELT + 4)
    bone("skirt", "torso", SKIRT_ROOT, WAIST)
    bone("skirt-front", "skirt", SK_FRONT, SKIRT_ROOT)
    bone("skirt-back", "skirt", SK_BACK, SKIRT_ROOT)
if WEAPON:
    # worn at the hip (koshi), tail down behind (the scabbard axis mouth->tail points back-down at
    # SHEATH degrees). Not on kurumi's dress belt: that is a high waist right under the chest, which
    # put the hilt at chest height. Setup rotations stay 0, so every animation keys rotate = SHEATH.
    SHEATH = 195.0
    MOUTH_PX = (122, 188)   # dress front edge at body row 188, ~34 px above the hip joints
    _m = sp(MOUTH_PX)
    _c, _s = math.cos(math.radians(SHEATH)), math.sin(math.radians(SHEATH))
    _ml = WEAPON["mouth"]
    _g = (_m[0] - (_c * _ml[0] - _s * _ml[1]), _m[1] - (_s * _ml[0] + _c * _ml[1]))
    SWORD_PX = (_g[0] + CX, GROUND - _g[1])
    bone("scabbard", "hip", MOUTH_PX, WAIST)
    bone("sword", "hip", SWORD_PX, WAIST)

# draw order back -> front; far limbs tinted darker for depth
FAR = "c8c0c8ff"
attach("far-upper-arm", "far-upper-arm", "arm-upper", SH_FAR, None, color=FAR)
attach("far-lower-arm", "far-lower-arm", "arm-lower", (SH_FAR[0] + 1, SH_FAR[1] + ELBOW_Y - 25), None, color=FAR)
if WEAPON:
    # worn on the left hip = the far side when facing right: behind the body and legs, in front of
    # the far arm only (the left hand holds the scabbard / handle from the outside). The scabbard is
    # drawn over the sword so the part of the blade still inside it stays hidden. Once drawn, the
    # attack's drawOrder timeline brings the sword in front of the body (katana-action.py).
    attach("sword", "sword", "sword", SWORD_PX, None)
    attach("scabbard", "scabbard", "scabbard", MOUTH_PX, None)
attach("far-lower-leg", "far-lower-leg", "leg-lower", (HIP_JOINT_FAR[0], HIP_JOINT_FAR[1] + THIGH_LEN), None, color=FAR)
attach("far-upper-leg", "far-upper-leg", "leg-upper", HIP_JOINT_FAR, None, color=FAR)
attach("near-lower-leg", "near-lower-leg", "leg-lower", (HIP_JOINT_NEAR[0], HIP_JOINT_NEAR[1] + THIGH_LEN), None)
attach("near-upper-leg", "near-upper-leg", "leg-upper", HIP_JOINT_NEAR, None)
if SKIRT:
    def _skirt_w(x, y):
        h = parts["skirt"].height
        t = y / h
        pin = (1 - smoothstep(t * 1.25)) ** 2        # top rows stay on the belt
        f = smoothstep((x - SK_BACK_X) / max(SK_FRONT_X - SK_BACK_X, 1))
        return {"skirt": pin, "skirt-front": (1 - pin) * f, "skirt-back": (1 - pin) * (1 - f)}
    attach_mesh("skirt", "skirt", (0, SKIRT_TOP), _skirt_w)
    attach("bodice", "torso", "bodice", WAIST, None)
else:
    attach("body", "torso", "body", WAIST, None)
attach("head", "head", "head", NECK, None)
attach("near-upper-arm", "near-upper-arm", "arm-upper", SH_NEAR, None)
attach("near-lower-arm", "near-lower-arm", "arm-lower", (SH_NEAR[0] + 1, SH_NEAR[1] + ELBOW_Y - 25), None)


# ---- animations (sampled, linear) --------------------------------------------
def sample(dur, n, fn):
    """fn(t01) -> {bone: {"rotate": deg, "x": dx, "y": dy}}"""
    tl = {}
    for i in range(n + 1):
        u = i / n
        for b, v in fn(u % 1.0 if i < n else 0.0).items():
            d = tl.setdefault(b, {})
            if "rotate" in v:
                d.setdefault("rotate", []).append({"time": round(u * dur, 4), "value": round(v["rotate"], 3)})
            if "x" in v or "y" in v:
                d.setdefault("translate", []).append({"time": round(u * dur, 4), "x": round(v.get("x", 0), 3), "y": round(v.get("y", 0), 3)})
    return {"bones": tl}


TAU = 2 * math.pi


def gait(u, thigh_amp, thigh_bias, knee_base, knee_amp, arm_amp, elbow, bob, lean, head_comp, drop=0):
    out = {}
    ph = TAU * u
    for side, off in (("near", 0.0), ("far", math.pi)):
        p = ph + off
        out[f"{side}-upper-leg"] = {"rotate": thigh_bias + thigh_amp * math.sin(p)}
        swing = max(0.0, math.cos(p)) ** 1.5  # knee folds while the leg swings forward
        out[f"{side}-lower-leg"] = {"rotate": -(knee_base + knee_amp * swing)}
        out[f"{side}-upper-arm"] = {"rotate": -arm_amp * math.sin(p)}
        out[f"{side}-lower-arm"] = {"rotate": elbow + 0.3 * elbow * max(0.0, -math.sin(p))}
    out["hip"] = {"x": 0, "y": -bob * math.cos(2 * ph) - drop}
    out["torso"] = {"rotate": lean + 1.5 * math.sin(2 * ph)}
    out["head"] = {"rotate": head_comp - 1.5 * math.sin(2 * ph)}
    return out


def idle(u):
    s = math.sin(TAU * u)
    return {"torso": {"rotate": -0.8 * s, "x": 0, "y": 1.5 * s},
            "head": {"rotate": 1.2 * math.sin(TAU * u - 0.6)},
            "near-upper-arm": {"rotate": 2.0 * math.sin(TAU * u - 0.4)},
            "near-lower-arm": {"rotate": 3.0 * math.sin(TAU * u - 0.8)},
            "far-upper-arm": {"rotate": 1.5 * math.sin(TAU * u - 0.5)},
            "far-lower-arm": {"rotate": 2.5 * math.sin(TAU * u - 0.9)}}


def jump(u):
    # 0-.25 crouch, .25-.35 launch, .35-.75 air, .75-.9 land, .9-1 recover
    def k(a, b, t):
        t = min(max(t, 0), 1)
        t = t * t * (3 - 2 * t)
        return a + (b - a) * t
    if u < 0.25:
        c = k(0, 1, u / 0.25); air = 0
    elif u < 0.35:
        c = k(1, -0.3, (u - 0.25) / 0.1); air = 0
    elif u < 0.75:
        c = -0.3 + 0.5 * math.sin(math.pi * (u - 0.35) / 0.4); air = math.sin(math.pi * (u - 0.35) / 0.4)
    elif u < 0.9:
        c = k(0.2, 0.8, (u - 0.75) / 0.15); air = 0
    else:
        c = k(0.8, 0, (u - 0.9) / 0.1); air = 0
    cr = max(c, 0)
    tuck = max(0.0, air - 0.3) * 1.4
    return {
        "hip": {"x": 0, "y": -38 * cr + 120 * air},
        "torso": {"rotate": -14 * cr - 4 * air},
        "head": {"rotate": 8 * cr},
        "near-upper-leg": {"rotate": 40 * cr + 35 * tuck},
        "near-lower-leg": {"rotate": -70 * cr - 60 * tuck},
        "far-upper-leg": {"rotate": 34 * cr + 20 * tuck},
        "far-lower-leg": {"rotate": -64 * cr - 45 * tuck},
        "near-upper-arm": {"rotate": -40 * cr + 150 * max(0, -c) * 2 + 120 * air},
        "near-lower-arm": {"rotate": 20 * cr + 10 * air},
        "far-upper-arm": {"rotate": -35 * cr + 110 * air},
        "far-lower-arm": {"rotate": 20 * cr + 10 * air},
    }


def wave(u):
    raise_ = min(1.0, u / 0.15) if u < 0.85 else max(0.0, (1 - u) / 0.15)
    osc = math.sin(TAU * 3 * u) * raise_
    return {"near-upper-arm": {"rotate": 155 * raise_},
            "near-lower-arm": {"rotate": 25 * raise_ + 25 * osc},
            "head": {"rotate": 4 * raise_},
            "torso": {"rotate": 2 * raise_}}


anims = {
    "idle": sample(2.0, 24, idle),
    "walk": sample(1.0, 24, lambda u: gait(u, 24, 2, 4, 40, 18, 12, 3, -3, 1)),
    "run": sample(0.6, 24, lambda u: gait(u, 42, 8, 15, 85, 38, 75, 7, -12, 6, drop=22)),
    "jump": sample(1.2, 36, jump),
    "wave": sample(1.6, 32, wave),
}
for path in EXTRA:
    with open(path, encoding="utf-8") as f:
        anims.update({k: v for k, v in json.load(f).items() if not k.startswith("_")})
REST = {}
if WEAPON:
    import runpy
    _ka = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "katana-action.py"))
    _ll = np.array(parts["leg-lower"])[..., 3] > 128
    _act, _diag = _ka["build"]({
        "bones": bones, "slots": slots, "weapon": WEAPON, "sheath": SHEATH,
        "fist": (2.0, -90.0),   # fist centre (38, 100) vs forearm pivot (36, 10), image px -> y up
        # heel / toe / knee in shin space (shin pivot (30, 12) in the shin image, sole at its bottom row)
        "foot_points": [(-12.0, -(_ll.shape[0] - 4 - 12)), (60.0, -(_ll.shape[0] - 6 - 12)), (0.0, -10.0)],
    })
    anims.update(_act)
    print("katana_attack", _diag)
    REST = {("sword", "rotate"): {"value": SHEATH}, ("scabbard", "rotate"): {"value": SHEATH}}

# Key every channel any animation uses in every animation (rest value where unused):
# Spine's player and Godot's AnimationPlayer both leave un-keyed bones in the previous
# animation's pose when switching, e.g. wave after run kept the running legs.
used = {(b, ch) for an in anims.values() for b, tl in an["bones"].items() for ch in tl}
for an in anims.values():
    dur = max(f["time"] for tl in an["bones"].values() for k in tl.values() for f in k)
    for b, ch in sorted(used):
        tl = an["bones"].setdefault(b, {})
        if ch not in tl:
            rest = REST.get((b, ch)) or ({"value": 0} if ch == "rotate" else
                                         {"x": 1, "y": 1} if ch == "scale" else {"x": 0, "y": 0})
            tl[ch] = [{"time": 0, **rest}, {"time": dur, **rest}]
    # same for draw order: a key without offsets = setup order
    if any("drawOrder" in a for a in anims.values()):
        an.setdefault("drawOrder", [{"time": 0}])


# ---- skirt secondary motion (baked) ------------------------------------------
SKIRT_F0, SKIRT_ZETA = 3.0, 0.35          # spring: natural frequency (Hz), damping ratio
SKIRT_SLACK_FRONT, SKIRT_SLACK_BACK = 8.0, 5.0   # thigh angle the skirt absorbs before moving
# gains (deg of panel per deg of thigh beyond the slack; flare: deg per px/s^2 of downward hip
# acceleration). Defaults are hand-set; --skirt-calib replaces them with a fit to a measured clip.
# spread: outward opening (deg) per unit of activity = RMS of the two thighs' angular speed / 100 deg/s
# front_leg / back_leg: which thigh pushes that panel: "max" (whichever is further out), "near", "far"
SKIRT_GAINS = {"push_front": 0.75, "push_back": 0.6, "flare": 0.0025, "spread": 0.0, "f0": SKIRT_F0,
               "front_leg": "max", "back_leg": "max"}


def _track(tl, bone, ch, key):
    fr = tl.get(bone, {}).get(ch)
    if not fr:
        return lambda t: np.zeros_like(t)
    ts = np.array([f["time"] for f in fr])
    vs = np.array([f.get(key, 0) for f in fr], float)
    return lambda t: np.interp(t, ts, vs)


def skirt_sim(an, gains, loops=4, sim_hz=240):
    """Steady-state panel angles over one cycle of a looping animation: a damped spring per panel
    pulled toward a target set by the thighs (front panel by the most forward thigh, back panel by
    the most backward one), plus an outward flare from the hip's downward acceleration and a
    steady outward spread proportional to how fast the legs move (air / momentum)."""
    tl = an["bones"]
    dur = max(f["time"] for b in tl.values() for k in b.values() for f in k)
    n = int(round(dur * sim_hz))
    t = np.arange(n) / n * dur
    th = np.stack([_track(tl, "near-upper-leg", "rotate", "value")(t), _track(tl, "far-upper-leg", "rotate", "value")(t)])
    hip_y = _track(tl, "hip", "translate", "y")(t)
    dt = dur / n
    acc = (np.roll(hip_y, -1) - 2 * hip_y + np.roll(hip_y, 1)) / dt ** 2   # periodic 2nd derivative
    down = np.maximum(0.0, -acc)
    dth = (np.roll(th, -1, axis=1) - np.roll(th, 1, axis=1)) / (2 * dt)
    activity = np.sqrt(np.mean(dth ** 2, axis=0)) / 100.0   # instantaneous; the spring smooths it
    pick = {"near": lambda f: th[0], "far": lambda f: th[1], "max": lambda f: f(th, axis=0)}
    fwd = pick[gains.get("front_leg", "max")](np.max)
    bwd = pick[gains.get("back_leg", "max")](np.min)
    targets = {"skirt-front": gains["push_front"] * np.maximum(0, fwd - SKIRT_SLACK_FRONT),
               "skirt-back": -gains["push_back"] * np.maximum(0, -bwd - SKIRT_SLACK_BACK)}
    k = (2 * math.pi * gains.get("f0", SKIRT_F0)) ** 2
    c = 2 * SKIRT_ZETA * math.sqrt(k)
    out = {}
    for name, sign in (("skirt-front", 1.0), ("skirt-back", -1.0)):
        tgt = targets[name] + sign * (gains["flare"] * down + gains.get("spread", 0.0) * activity)
        x = v = 0.0
        hist = np.zeros(n)
        for _ in range(loops):
            for i in range(n):
                v += (k * (tgt[i] - x) - c * v) * dt
                x += v * dt
                hist[i] = x
        out[name] = hist
    return t, dur, out


def skirt_motion(an, gains, key_hz=30):
    t, dur, out = skirt_sim(an, gains)
    m = max(2, int(round(dur * key_hz)))
    times = np.arange(m + 1) / m * dur
    for name, hist in out.items():
        vals = np.interp(times % dur, t, hist)
        vals[-1] = vals[0]
        an["bones"][name] = {"rotate": [{"time": round(float(a), 4), "value": round(float(b), 3)} for a, b in zip(times, vals)]}
    return {nm: (round(float(h.min()), 1), round(float(h.max()), 1)) for nm, h in out.items()}


def skirt_calibrate(an, measured, fps):
    """Grid-search the gains so the simulated panels match measured hem angles (degrees vs the
    rest pose, per clip frame; None = not measured). Returns (gains, rmse per panel)."""
    fd = np.array([np.nan if v is None else v for v in measured["front_delta"]], float)
    bd = np.array([np.nan if v is None else v for v in measured["back_delta"]], float)
    tf = np.arange(len(fd)) / fps
    best = None
    for fleg in ("max", "near", "far"):
        for bleg in ("max", "near", "far"):
            for f0 in (2.0, 3.0):
                for fl in (0.0, 0.002):
                    for sp_ in np.linspace(0.0, 10.0, 6):
                        for pf in np.linspace(0.0, 1.0, 11):
                            for pb in np.linspace(0.0, 1.0, 11):
                                g = {"push_front": pf, "push_back": pb, "flare": fl, "spread": sp_, "f0": f0,
                                     "front_leg": fleg, "back_leg": bleg}
                                t, dur, out = skirt_sim(an, g, loops=3, sim_hz=96)
                                ef = np.interp(tf % dur, t, out["skirt-front"]) - fd
                                eb = np.interp(tf % dur, t, out["skirt-back"]) - bd
                                err = np.sqrt(np.nanmean(np.r_[ef, eb] ** 2))
                                if best is None or err < best[0]:
                                    best = (err, g, float(np.sqrt(np.nanmean(ef ** 2))), float(np.sqrt(np.nanmean(eb ** 2))))
    best[1].update({k_: float(v_) for k_, v_ in best[1].items() if not isinstance(v_, str)})
    return best[1], {"rmse_front_deg": round(best[2], 1), "rmse_back_deg": round(best[3], 1),
                     "measured_front": [float(np.nanmin(fd)), float(np.nanmax(fd))],
                     "measured_back": [float(np.nanmin(bd)), float(np.nanmax(bd))]}


if SKIRT:
    if _args.skirt_calib:
        with open(_args.skirt_calib, encoding="utf-8") as f:
            _meas = json.load(f)["summary"]
        SKIRT_GAINS, _fit = skirt_calibrate(anims[_args.calib_anim], _meas, _args.calib_fps)
        print("skirt calibrated on", _args.calib_anim, SKIRT_GAINS, _fit)
        with open(os.path.join(OUT, "skirt_calibration.json"), "w") as f:
            json.dump({"gains": SKIRT_GAINS, "fit": _fit}, f, indent=1)
    for _name, _an in anims.items():
        print("skirt", _name, skirt_motion(_an, SKIRT_GAINS))

skel = {
    "skeleton": {"hash": "kurumi-cutout", "spine": "4.2.0", "x": -200, "y": -10,
                 "width": 400, "height": GROUND + 200, "images": "./images/"},
    "bones": bones, "slots": slots,
    "skins": [{"name": "default", "attachments": atts}],
    "animations": anims,
}
with open(os.path.join(OUT, "kurumi.json"), "w") as f:
    json.dump(skel, f, indent=1)


# ---- preview renderer (same maths as Spine for rotate/translate, linear) -----
def interp(frames, t, keys):
    if t <= frames[0]["time"]:
        return [frames[0].get(k, 0) for k in keys]
    for a, b in zip(frames, frames[1:]):
        if a["time"] <= t <= b["time"]:
            w = (t - a["time"]) / (b["time"] - a["time"] or 1)
            return [a.get(k, 0) + (b.get(k, 0) - a.get(k, 0)) * w for k in keys]
    return [frames[-1].get(k, 0) for k in keys]


def pose(anim, t):
    tl = anims[anim]["bones"] if anim else {}
    W = {}
    for b in bones:
        r = tx = ty = 0.0
        if b["name"] in tl:
            d = tl[b["name"]]
            if "rotate" in d:
                (r,) = interp(d["rotate"], t, ["value"])
            if "translate" in d:
                tx, ty = interp(d["translate"], t, ["x", "y"])
        lx, ly = b["x"] + tx, b["y"] + ty
        if "parent" in b:
            px, py, pr = W[b["parent"]]
            c, s = math.cos(math.radians(pr)), math.sin(math.radians(pr))
            W[b["name"]] = (px + c * lx - s * ly, py + s * lx + c * ly, pr + r)
        else:
            W[b["name"]] = (lx, ly, r)
    return W


SKIN_PARTS = {"arm-upper", "arm-lower", "leg-upper", "leg-lower"}


def render_mesh(slot, im, W, ox, oy, size):
    """Skinned mesh: deform vertices by their bone weights, then warp each triangle (affine)
    into a separate layer (paste, so shared edges are not blended twice)."""
    order, grid, tris, vw = MESH_CACHE[slot]
    pts = []
    for entry in vw:
        X = Y = 0.0
        for b, bxl, byl, w in entry:
            bx, by, br = W[b]
            c, s_ = math.cos(math.radians(br)), math.sin(math.radians(br))
            X += w * (bx + c * bxl - s_ * byl)
            Y += w * (by + s_ * bxl + c * byl)
        pts.append((ox + X, oy - Y))
    src = [grid[k] for k in order]
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    for q in range(0, len(tris), 3):
        i0, i1, i2 = tris[q:q + 3]
        D = np.array([pts[i0], pts[i1], pts[i2]])
        S = np.array([src[i0], src[i1], src[i2]])
        x0, y0 = np.floor(D.min(0)).astype(int) - 1
        x1, y1 = np.ceil(D.max(0)).astype(int) + 1
        if x1 <= x0 or y1 <= y0:
            continue
        # affine (dest -> src) for PIL: [sx, sy] = M @ [dx, dy, 1]
        A = np.c_[D - (x0, y0), np.ones(3)]
        try:
            M = np.linalg.solve(A, S).T
        except np.linalg.LinAlgError:
            continue
        tile = im.transform((x1 - x0, y1 - y0), Image.AFFINE, M.flatten().tolist(), resample=Image.BICUBIC)
        mask = Image.new("L", tile.size, 0)
        ImageDraw.Draw(mask).polygon([tuple(p) for p in (D - (x0, y0))], fill=255, outline=255)
        layer.paste(tile, (int(x0), int(y0)), mask)
    return layer


def slot_order(anim, t):
    """Spine drawOrder timeline: the last key at or before t; listed slots move by their offset,
    the others keep their setup order in the remaining places."""
    keys = anims[anim].get("drawOrder") if anim else None
    cur = None
    for k in keys or []:
        if k["time"] <= t + 1e-9:
            cur = k
    if not cur or not cur.get("offsets"):
        return slots
    names = [s["name"] for s in slots]
    out, moved = [None] * len(slots), set()
    for o in cur["offsets"]:
        i = names.index(o["slot"])
        out[i + o["offset"]] = i
        moved.add(i)
    rest = iter(i for i in range(len(slots)) if i not in moved)
    return [slots[i if i is not None else next(rest)] for i in out]


def bone_scale_x(anim, bone, t):
    """Scale timelines are supported on the root (applied to the whole figure in render()) and on
    leaf bones (applied to their own attachment only), nothing in between."""
    sc = anims[anim]["bones"].get(bone, {}).get("scale") if anim else None
    return interp(sc, t, ["x"])[0] if sc else 1.0


def root_scale_x(anim, t):
    return bone_scale_x(anim, "root", t)


def render(anim, t, size=(560, 940), bg=(40, 44, 60, 255)):
    canvas = Image.new("RGBA", size, bg)
    d = ImageDraw.Draw(canvas)
    ox, oy = size[0] // 2 - 20, size[1] - 40
    d.line([(0, oy), (size[0], oy)], fill=(90, 96, 120, 255), width=2)
    # only the root may scale (turning round): draw the figure unscaled, then scale it about the root
    # in x. Exact for Spine/Godot because every bone inherits the root transform.
    sx = root_scale_x(anim, t)
    final = canvas
    if abs(sx - 1) > 1e-6:
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    W = pose(anim, t)
    for s in slot_order(anim, t):
        bx, by, br = W[s["bone"]]
        (name, a), = atts[s["name"]].items()
        im = parts[name]
        if a.get("type") == "mesh":
            canvas.alpha_composite(render_mesh(s["name"], im, W, ox, oy, size))
            continue
        if DEBUG_SKIN and name in SKIN_PARTS:
            arr = np.array(im)
            arr[..., :3] = (230, 0, 200)
            im = Image.fromarray(arr, "RGBA")
        if "color" in s:
            c = s["color"]
            m = np.array([int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)])
            arr = np.array(im).astype(np.float32)
            arr[..., :3] *= m
            im = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
        ax = a["x"]
        if s["bone"] != "root":
            bsx = bone_scale_x(anim, s["bone"], t)
            if abs(bsx - 1) > 1e-6:
                ax *= bsx
                im = im.resize((max(1, round(im.width * abs(bsx))), im.height), Image.LANCZOS)
                if bsx < 0:
                    im = im.transpose(Image.FLIP_LEFT_RIGHT)
        c_, s_ = math.cos(math.radians(br)), math.sin(math.radians(br))
        cx, cy = bx + c_ * ax - s_ * a["y"], by + s_ * ax + c_ * a["y"]
        rim = im.rotate(br, resample=Image.BICUBIC, expand=True)
        px, py = ox + cx - rim.width / 2, oy - cy - rim.height / 2
        canvas.alpha_composite(rim, (int(round(px)), int(round(py))))
    if canvas is not final:
        if abs(sx) > 0.02:   # output x' = ox + sx (x - ox)  ->  source x = x'/sx + ox (1 - 1/sx)
            fig = canvas.transform(size, Image.AFFINE, (1 / sx, 0, ox * (1 - 1 / sx), 0, 1, 0), resample=Image.BICUBIC)
            final.alpha_composite(fig)
    return final


if DEBUG_SKIN:
    print("debug-skin: previews only, the Spine JSON is unchanged")
render(None, 0).save(os.path.join(OUT, "setup_pose.png"))
for name, an in anims.items():
    dur = max(f["time"] for tl in an["bones"].values() for k in tl.values() for f in k)
    n = int(round(dur * 30))
    size = (1000, 1000) if name == "katana_attack" else (560, 940)   # leaping cut + long blade
    frames = [render(name, dur * i / n, size=size).convert("RGB") for i in range(n)]
    frames[0].save(os.path.join(OUT, f"{name}.gif"), save_all=True, append_images=frames[1:],
                   duration=int(1000 / 30), loop=0)
    # contact sheet of 6 frames for quick review
    tw = round(400 * size[0] / size[1])
    sheet = Image.new("RGB", (6 * tw, 400))
    for j in range(6):
        sheet.paste(frames[j * n // 6].resize((tw, 400)), (j * tw, 0))
    sheet.save(os.path.join(OUT, f"{name}_sheet.png"))
print("ok", len(bones), "bones", len(slots), "slots", list(anims))
