"""方块风角色穿模检查：按部件名分类，检查「不该相交」的几类方块对（静止姿势）。

算法：每个方块算出世界坐标下的有向包围盒（骨骼旋转逐级相乘 + 方块自身旋转），
两两用分离轴定理（SAT，15 根轴）判相交；两边各内缩 tol，只报真正插进去的。
自写胶水；SAT 是 OBB 相交的标准做法（Gottschalk 1996 / Ericson《Real-Time Collision Detection》4.4）。

规则（名字前缀，见 RULES）：
- 手臂 / 袖子 不能插进 裙子、衣摆、双马尾、身体；
- 裙子底下的身体（胯、大腿、腰）不能顶出裙面（裙面上沿 0.5 是贴腰收口，不算）；
- 领带不能埋进胸口 / 胸部；
- 耳机戴在头发外面，不能插进头发。
只证明这些关系，不是全模型零交叠（发束之间、配件嵌进头发是有意的）。

用法：python scripts/blocky-clip-check.py output/blocky/miku-ysm/spec.json
"""
import json
import math
import sys

import numpy as np

RULES = [
    ("arm vs skirt/hem", ("arm_", "upper_arm", "forearm", "hand", "dsleeve", "cuff", "sleeve_"),
     ("skirt_", "shirt_hem")),
    ("arm vs twintail", ("arm_", "upper_arm", "forearm", "hand", "dsleeve", "cuff", "sleeve_"), ("twintail",)),
    ("arm vs torso", ("arm_", "forearm", "hand", "dsleeve", "cuff"), ("chest", "underchest", "waist", "hips", "bust")),
    ("body pokes through skirt", ("hips", "thigh", "leg_", "waist", "boot_top"), ("skirt_",), 0.5),
    ("twintail vs body", ("twintail",), ("chest", "underchest", "waist", "hips", "skirt_", "shirt_hem", "thigh")),
    ("tie sunk into chest", ("tie",), ("chest", "underchest", "waist", "bust")),
    ("headset vs hair", ("headset",), ("hair_", "side_lock", "bang", "twintail")),
]


def rot(rx, ry, rz):
    ax, ay, az = (math.radians(v) for v in (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def pivot(origin, rotation):
    T = np.eye(4)
    R = rot(*rotation)
    o = np.array(origin, float)
    T[:3, :3] = R
    T[:3, 3] = o - R @ o
    return T


def obbs(spec, tol):
    groups = {g["name"]: g for g in spec["groups"]}
    cache = {}

    def gtf(n):
        if n not in cache:
            g = groups[n]
            T = pivot(g["origin"], g.get("rotation", [0, 0, 0]))
            cache[n] = gtf(g["parent"]) @ T if g.get("parent") else T
        return cache[n]

    out = {}
    for c in spec["cubes"]:
        T = gtf(c["group"])
        if c.get("rotation"):
            T = T @ pivot(c["origin"], c["rotation"])
        fr, to = np.array(c["from"], float), np.array(c["to"], float)
        half = np.maximum((to - fr) / 2 - tol, 0)
        ctr = T[:3, :3] @ ((fr + to) / 2) + T[:3, 3]
        out[c["name"]] = (ctr, T[:3, :3], half)
    return out


def sat(a, b):
    (ca, Ra, ha), (cb, Rb, hb) = a, b
    if ha.min() <= 0 and hb.min() <= 0:
        return False
    axes = [Ra[:, i] for i in range(3)] + [Rb[:, i] for i in range(3)]
    axes += [np.cross(Ra[:, i], Rb[:, j]) for i in range(3) for j in range(3)]
    t = cb - ca
    for L in axes:
        n = np.linalg.norm(L)
        if n < 1e-8:
            continue
        L = L / n
        ra = sum(ha[i] * abs(Ra[:, i] @ L) for i in range(3))
        rb = sum(hb[i] * abs(Rb[:, i] @ L) for i in range(3))
        if abs(t @ L) > ra + rb:
            return False
    return True


def trim_top(o, t):
    """裙面上沿本来就收口贴着腰：只看上沿 t 以下的部分（局部 +Y 是板的上沿方向）。"""
    c, R, h = o
    t = min(t, h[1])
    return (c - R[:, 1] * t / 2, R, h - np.array([0, t / 2, 0]))


def check(spec, tol=0.03):
    B = obbs(spec, tol)
    hits = {}
    for rule in RULES:
        label, A, Bp = rule[:3]
        trim = rule[3] if len(rule) > 3 else 0
        na = [n for n in B if n.startswith(A) and "ribbon" not in n]   # 腰带是系在裙腰外的衣物，不算身体
        nb = [n for n in B if n.startswith(Bp)]
        bad = [(x, y) for x in na for y in nb if x != y and sat(B[x], trim_top(B[y], trim) if trim else B[y])]
        hits[label] = bad
    return hits


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    hits = check(spec)
    total = 0
    for label, bad in hits.items():
        total += len(bad)
        print(f"{label}: {len(bad)}" + (f"  e.g. {bad[:6]}" if bad else ""))
    print("TOTAL", total)
    sys.exit(1 if total else 0)
