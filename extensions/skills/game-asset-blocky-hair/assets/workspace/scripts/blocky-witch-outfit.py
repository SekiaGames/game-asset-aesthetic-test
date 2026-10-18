"""Reusable witch / mage costume parts for blocky-template.py.

Each part is switched on by a character config key, and every size is taken from the cubes
the body preset already built (head, arm, leg, waist), so the parts follow jenny/ysm/chibi.

  witch_hat:  {"mat", "in", "band", "tip_back", "height", "gem", "gem_rim"}  cone + bent tip + brim, built
              as slab rings (Kit.ring, the same construction as the A-line skirt) so the silhouette has no steps
  off_shoulder: {"mat", "trim"}  bare shoulders; a cuff and a flap hanging outward on each upper arm
  bracers:    {"mat", "trim", "gem"}  forearm guards with trim bands and an outer gem
  choker:     {"mat", "gem"}  thin band round the neck with a front gem
  belt:       {"mat"}  band round the waist at the skirt top
  skirt_open_front: degrees  skirt panels within +-deg of the front are removed (leotard shows)
  skirt_jag:  [extra lengths]  lower skirt panels get these extra lengths in turn (pointed hem)
  boot_gems:  {"gem", "rim", "band"}  gem on the outer side of each boot and a trim band
  staff:      {"shaft", "metal", "hand": "Right"|"Left"}  staff held across the fist (MC hand item), spiral head forward

Self-written; construction rules from extensions/skills/mcbemodelingmasterAI (docs/03-shape-rules):
slanted parts join corner to corner, rings overlap instead of stepping.
"""
import math

import numpy as np


def _cube(k, name):
    return next(c for c in k.cubes if c["name"] == name)


def _find(k, *names):
    for n in names:
        for c in k.cubes:
            if c["name"] == n:
                return c
    return None


def witch_hat(k, C, P):
    H = C.get("witch_hat")
    if not H:
        return
    hs, hy0 = P["head"], P["head_y"]
    h, d = hs / 2, P.get("head_d", hs) / 2
    hy1 = hy0 + hs
    sh = P.get("hair_shell", 0.95)
    base_y = hy1 - 0.9 * hs / 8                    # hat sits low on the hair dome, above the brows
    rx, rz = h + sh + 0.55, d + sh + 0.55          # outside the hair dome
    cz = 0.15
    height = H.get("height", 1.15) * hs            # cone height (reference: about one head)
    back = H.get("tip_back", 0.45) * hs
    k.group("Hat", "Head", (0, base_y, cz))
    mat, inner = H["mat"], H.get("in", H["mat"])
    # cone: stacked short rings along a centreline tilted back towards the tip. Each ring only tapers
    # a little, so its panels (width from the mean circumference) still close the gaps; one ring for the
    # whole cone leaves slits at the base and splayed sticks at the tip.
    levels = H.get("levels", 7)
    def at(t):
        # straight (tilted) cone: every panel column stays on one line, so ring joints show no ridge
        return (cz + back * t, rx * (1 - t) + 0.12, rz * (1 - t) + 0.12, base_y + height * t)
    for i in range(levels):
        t0, t1 = i / levels, (i + 1) / levels
        zb, ax, az, yb = at(t0)
        zt, bx, bz, yt = at(t1)
        n = H.get("panels", 16)                      # same count + phase every ring: panels line up into columns
        k.ring(f"hat_cone{i}", lambda p: "Hat", ((0, zt), bx, bz, yt), ((0, zb), ax, az, yb), n, 0.32,
               lambda j, p: mat, overlap=1.35, faces_of=lambda j, p: {"south": inner})
    # band: a thin ring just outside the cone, partway up
    if H.get("band"):
        zc, ax, az, y_b = at(0.2)
        k.ring("hat_band", lambda p: "Hat", ((0, zc + 0.08), ax + 0.3, az + 0.3, y_b + 0.45),
               ((0, zc), ax * 1.05 + 0.34, az * 1.05 + 0.34, y_b - 0.35), 18, 0.12, lambda i, p: H["band"], overlap=1.3)
    # brim: a flat ring flaring out and slightly down; the outer edge is the trim colour (material hband)
    b_in = ((0, cz), rx - 0.25, rz - 0.25, base_y + 0.15)
    b_out = ((0, cz - 0.2), rx + 2.6 * hs / 8, rz + 2.4 * hs / 8, base_y - 0.55 * hs / 8)
    k.ring("hat_brim", lambda p: "Hat", b_in, b_out, 18, 0.3, lambda i, p: H.get("brim", mat), overlap=1.3,
           faces_of=lambda i, p: {"south": inner, "down": inner})
    if H.get("gem"):
        # gem on the front of the cone above the brim, a little to the character's right
        s = hs / 8
        t0 = 0.1
        zc, ax, az, gy = at(t0)
        zc2, _, az2, gy2 = at(t0 + 0.05)
        zf = zc - az
        tilt = math.degrees(math.atan2((zc2 - az2) - zf, gy2 - gy))
        gx = 0.3 * ax
        k.box("hat_gem_rim", "Hat", [gx - 0.95 * s, gy - 0.95 * s, zf - 0.45], [gx + 0.95 * s, gy + 0.95 * s, zf + 0.2],
              H.get("gem_rim", H.get("band", mat)), rotation=[tilt, 0, 0], origin=[gx, gy, zf])
        k.box("hat_gem", "Hat", [gx - 0.6 * s, gy - 0.6 * s, zf - 0.7], [gx + 0.6 * s, gy + 0.6 * s, zf - 0.3],
              H["gem"], rotation=[tilt, 0, 0], origin=[gx, gy, zf])


def off_shoulder(k, C, P):
    O = C.get("off_shoulder")
    if not O:
        return
    for c in k.cubes:
        if c["name"] == "shoulders":
            c["mat"] = "skin"
    for side, s in (("Right", 1), ("Left", -1)):
        arm = _find(k, f"arm_{side[0]}", f"upper_arm_{side[0]}")
        a, b = arm["from"], arm["to"]
        L = b[1] - a[1]
        y0, y1 = b[1] - 0.42 * L, b[1] - 0.24 * L
        e = 0.22
        k.box(f"shoulder_cuff_{side[0]}", arm["group"], [a[0] - e, y0, a[2] - e], [b[0] + e, y1, b[2] + e], O["mat"])
        # flap: plate hanging from the cuff top, flaring outward (like the illustration's epaulettes)
        xo = b[0] if s > 0 else a[0]
        top = [xo + s * 0.1, y1, (a[2] + b[2]) / 2]
        bot = [xo + s * 1.6 * (b[0] - a[0]) / 2, y0 - 0.12 * L, (a[2] + b[2]) / 2]
        k.slab(f"shoulder_flap_{side[0]}", arm["group"], top, bot, (b[2] - a[2]) + 1.4, 0.3, O.get("flap", O["mat"]),
               outward=[s, 0], faces={"south": O.get("in", O["mat"])})


def bracers(k, C, P):
    Bc = C.get("bracers")
    if not Bc:
        return
    for side, s in (("Right", 1), ("Left", -1)):
        arm = _find(k, f"forearm_{side[0]}", f"arm_{side[0]}")
        a, b = arm["from"], arm["to"]
        L = b[1] - a[1]
        # one-piece arm (jenny): wrist to mid forearm; two-piece arm (ysm): most of the forearm
        f0, f1 = (0.09, 0.48) if arm["name"].startswith("arm_") else (0.05, 0.85)
        lo, hi = a[1] + f0 * L, a[1] + f1 * L
        e = 0.22
        k.box(f"bracer_{side[0]}", arm["group"], [a[0] - e, lo, a[2] - e], [b[0] + e, hi, b[2] + e], Bc["mat"])
        for yy in (lo, hi - 0.35):
            k.box(f"bracer_trim_{side[0]}", arm["group"], [a[0] - e - 0.08, yy, a[2] - e - 0.08],
                  [b[0] + e + 0.08, yy + 0.35, b[2] + e + 0.08], Bc["trim"])
        if Bc.get("gem"):
            xo = (b[0] + e) if s > 0 else (a[0] - e)
            cy, cz = (lo + hi) / 2, (a[2] + b[2]) / 2
            x0, x1 = sorted([xo - s * 0.05, xo + s * 0.35])
            k.box(f"bracer_gem_{side[0]}", arm["group"], [x0, cy - 0.6, cz - 0.6], [x1, cy + 0.6, cz + 0.6], Bc["gem"])


def choker(k, C, P):
    Ch = C.get("choker")
    if not Ch:
        return
    n = _cube(k, "neck")
    a, b = n["from"], n["to"]
    y = a[1] + 0.55 * (b[1] - a[1])
    k.box("choker", n["group"], [a[0] - 0.12, y - 0.25, a[2] - 0.12], [b[0] + 0.12, y + 0.25, b[2] + 0.12], Ch["mat"])
    if Ch.get("gem"):
        k.box("choker_gem", n["group"], [-0.3, y - 0.65, a[2] - 0.3], [0.3, y + 0.15, a[2] - 0.1], Ch["gem"])


def belt(k, C, B, rings):
    Bt = C.get("belt")
    if not Bt:
        return
    w = _cube(k, "waist")
    y = rings[0][3]
    a, b = w["from"], w["to"]
    k.box("belt", w["group"], [a[0] - 0.12, y - 0.1, a[2] - 0.12], [b[0] + 0.12, y + 0.65, b[2] + 0.12], Bt["mat"])
    # front point of the belt (V towards the hips)
    k.slab("belt_point", w["group"], [0, y + 0.1, a[2] - 0.14], [0, y - 0.9, a[2] - 0.14], 1.2, 0.12, Bt["mat"],
           outward=[0, -1])


def skirt_shape(k, C):
    """Open front (cut panels near phi=0) and pointed hem (alternate panel lengths)."""
    S = C.get("skirt", {})
    open_deg = C.get("skirt_open_front")
    jag = C.get("skirt_jag")
    if not open_deg and not jag:
        return
    low = [c for c in k.cubes if c["name"].startswith(("skirt_low", "skirt_up"))]
    for c in low:
        if not c.get("rotation"):
            continue
        yaw = c["rotation"][1]                         # outward yaw: 0 = front
        phi = (-yaw) % 360
        if open_deg and min(phi, 360 - phi) < open_deg:
            k.cubes.remove(c)
    if jag:
        i = 0
        for c in k.cubes:
            if c["name"].startswith("skirt_low"):
                c["from"][1] -= jag[i % len(jag)]
                i += 1


def boot_gems(k, C, P):
    G = C.get("boot_gems")
    if not G:
        return
    for side, s in (("Right", 1), ("Left", -1)):
        top = _find(k, f"boot_top_{side[0]}")
        if not top:
            continue
        a, b = top["from"], top["to"]
        xo = b[0] if s > 0 else a[0]
        cy, cz = a[1] + 0.3 * (b[1] - a[1]), (a[2] + b[2]) / 2
        x0, x1 = sorted([xo - s * 0.05, xo + s * 0.3])
        k.box(f"boot_gem_rim_{side[0]}", top["group"], [x0, cy - 0.85, cz - 0.85], [x1, cy + 0.85, cz + 0.85], G["rim"])
        x0, x1 = sorted([xo + s * 0.2, xo + s * 0.45])
        k.box(f"boot_gem_{side[0]}", top["group"], [x0, cy - 0.55, cz - 0.55], [x1, cy + 0.55, cz + 0.55], G["gem"])
        if G.get("band"):
            y = a[1] + 0.62 * (b[1] - a[1])
            k.box(f"boot_band_{side[0]}", top["group"], [a[0] - 0.08, y, a[2] - 0.08], [b[0] + 0.08, y + 0.4, b[2] + 0.08],
                  G["band"])


def staff_along(k, St, group, grip, axis, up, sc, back=5.0, front=14.0):
    """Staff through `grip` along `axis` (grip -> head), spiral head in the plane of `axis` and `up`.
    back/front: shaft length behind / in front of the grip (in head/8 units)."""
    g = np.asarray(grip, float)
    a = np.asarray(axis, float); a /= np.linalg.norm(a)
    b = np.asarray(up, float); b = b - (b @ a) * a; b /= np.linalg.norm(b)
    n = np.cross(a, b)                               # spiral plane normal
    p = lambda s, h=0.0: (g + a * s * sc + b * h * sc).tolist()
    k.group("Staff", group, tuple(g))
    k.beam("staff_shaft", "Staff", p(-back), p(front), 0.6, 0.6, St["shaft"], facing=tuple(b))
    for s in (-back + 1.0, -0.9, 1.0, front - 1.6):    # rings either side of the fist and near both ends
        k.beam("staff_ring", "Staff", p(s), p(s + 0.3), 0.84, 0.84, St.get("ring", St["metal"]), facing=tuple(b))
    k.beam("staff_cap", "Staff", p(-back - 0.7), p(-back), 0.84, 0.84, St["metal"], facing=tuple(b))
    k.beam("staff_collar", "Staff", p(front), p(front + 0.9), 1.1, 1.1, St["metal"], facing=tuple(b))
    # head: spiral of short beams round a centre ahead of the collar
    c0 = g + a * (front + 2.4) * sc
    pts = []
    for i in range(15):
        t = i / 14
        ang = math.radians(180 - 600 * t)
        r = (1.75 - 1.45 * t) * sc
        pts.append(c0 + (a * math.cos(ang) + b * math.sin(ang)) * r)
    pts[0] = g + a * (front + 0.7) * sc
    for i in range(len(pts) - 1):
        k.beam("staff_curl", "Staff", pts[i].tolist(), pts[i + 1].tolist(), 0.75 * sc, 0.75 * sc, St["metal"],
               facing=tuple(n), ext=0.18)


def staff(k, C, P):
    """Held like a Minecraft hand item: through the fist, across the forearm, head pointing forward."""
    St = C.get("staff")
    if not St:
        return
    side = St.get("hand", "Right")
    arm = _find(k, f"hand_{side[0]}", f"arm_{side[0]}")
    a, b = arm["from"], arm["to"]
    grip = [(a[0] + b[0]) / 2, a[1] + 0.9, (a[2] + b[2]) / 2]
    staff_along(k, St, arm["group"], grip, (0, 0, -1), (0, 1, 0), P["head"] / 8)


def add_parts(k, C, B, P, rings):
    witch_hat(k, C, P)
    off_shoulder(k, C, P)
    bracers(k, C, P)
    choker(k, C, P)
    belt(k, C, B, rings)
    skirt_shape(k, C)
    boot_gems(k, C, P)
    staff(k, C, P)
