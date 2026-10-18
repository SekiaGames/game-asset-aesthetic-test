"""正 / 侧 / 背三个视角的游戏用 Spine 4.2 骨骼（饥荒式多方向，src/dst-demo/ 用）。

用法：python -I scripts/dir-rig.py <layers_dir> <rig_dir> \
          --view front|side|back [--name kurumi_side] [--ref <正面 layers.json>]
      之后 spine-pack.py <rig_dir> --name <name>；三套写进一个 manifest.json 给演示页（格式见 src/dst-demo/main.js）。

输入是 seethrough-to-layers.py 的层目录（侧面 / 背面用 poses = - 跑的）。与 front-rig.py 的区别：
- 不依赖 DWPose：髋 = 腿层顶（See-through 把裙下的腿补到了髋，正面实测腿层顶 y=1193 与 DWPose 髋点相同），
  膝 / 踝按髋到地面的比例取（--ref 给正面 layers.json 时用它的 DWPose 比例，否则默认 0.386 / 0.83，即正面实测值），
  手臂链沿手臂层中轴（同 front-rig.py 的 arm_chain: layer）。
- 腿分左右：正 / 背面两腿之间有空隙，逐行找两腿之间的透明缝取中线分开；两腿在裙下并在一起的几行用最近一行缝的位置
  （这一段被裙子盖住）。侧面两腿在轮廓里重叠，--leg-mode dup：同一张腿图用两次，远侧那条压暗、画在身体后面。
  侧面只有一只手臂层时远侧手臂同样处理。
- 动作：idle / walk / run 三套视角同名、同周期、同相位（角色右腿在 u = 0 开始迈 / 抬），演示页切视角时把动作时间带过去，步子不断。
  侧面：髋 / 膝转角 + 由两条腿的正向运动学算出的髋高（低的那只脚保持在地面上，起伏自然来）；
  正 / 背面：抬起的那条腿沿骨骼方向缩短（膝向前弯时的透视缩短）、重心移向支撑腿、手臂前后摆用长度缩放表现。
- 物理（Spine 4.2 物理约束，运行时模拟）：发梢、裙摆，参数同 front-rig.py。
- 不做：表情、视线转头、手势（这些在 front-rig.py 里；这里是游戏里跑来跑去用的小尺寸角色）。正面有闭眼层时待机里眨一次眼。
"""
import argparse
import importlib.util
import json
import math
import os
import shutil

import numpy as np
from PIL import Image

_spec = importlib.util.spec_from_file_location("front_rig", os.path.join(os.path.dirname(os.path.abspath(__file__)), "front-rig.py"))
FR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FR)
smooth, build_mesh, tail_path = FR.smooth, FR.build_mesh, FR.tail_path

FPS = 30
WALK_T, RUN_T, IDLE_T = 0.9, 0.6, 3.0
TAU = 2 * math.pi
HEAD_PARTS = ["ears", "face", "nose", "eyewhite_R", "iris_R", "lash_R", "eyewhite_L", "iris_L", "lash_L",
              "brow_R", "brow_L", "mouth_smile"]


def split_legs(alpha):
    """两腿之间的透明缝逐行取中线 → (左腿 alpha, 右腿 alpha)（画面左右）。"""
    m = alpha > 20
    h, w = m.shape
    mids = np.full(h, np.nan)
    for y in range(h):
        xs = np.nonzero(m[y])[0]
        if len(xs) < 2:
            continue
        g = np.nonzero(np.diff(xs) > 3)[0]
        if len(g) == 0:
            continue
        c = xs.mean()
        k = g[np.argmin(np.abs((xs[g] + xs[g + 1]) / 2 - c))]
        mids[y] = (xs[k] + xs[k + 1]) / 2
    ok = ~np.isnan(mids)
    if ok.sum() < h * 0.2:
        raise SystemExit("腿层里找不到两腿之间的缝（侧面请用 --leg-mode dup）")
    ys = np.arange(h)
    vy = ys[ok]
    near = vy[np.abs(ys[:, None] - vy[None, :]).argmin(1)]  # 无缝的行取最近一行有缝的位置
    mid = np.where(ok, mids, mids[near])
    from scipy.ndimage import median_filter
    mid = median_filter(mid, 9, mode="nearest")
    xx = np.arange(w)[None, :]
    left = np.where(xx < mid[:, None], alpha, 0).astype(np.uint8)
    right = np.where(xx >= mid[:, None], alpha, 0).astype(np.uint8)
    return left, right, ok.mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("layers_dir")
    ap.add_argument("rig_dir")
    ap.add_argument("--view", required=True, choices=["front", "side", "back"])
    ap.add_argument("--name", default=None)
    ap.add_argument("--ref", default=None, help="正面 layers.json（带 DWPose kp）：膝 / 踝高度比例取它的")
    ap.add_argument("--leg-mode", default=None, choices=["split", "dup"], help="默认正 / 背面 split、侧面 dup")
    ap.add_argument("--far-shade", type=float, default=0.94, help="侧面远侧手脚压暗系数（0.88 时两腿都弯着显得发棕）")
    ap.add_argument("--side-arms", default="1.0",
                    help="侧面手臂摆幅系数（相对动捕循环平均角缩放）：一个数对所有动作，或按动作写「walk=0.6,run=0.85」。"
                         "2026-10-10 用户：走路「手摆幅也过大」、跑步「可以稍大一点点」")
    ap.add_argument("--straighten", type=float, default=0.0,
                    help="侧面支撑期（这只脚离地低于最高点 25%）膝盖弯曲减少的比例（0–1）：CMU 走路普遍偏蹲（膝弯中位 33–46°），"
                         "动画常做得更挺拔；髋高由正向运动学自动抬起，脚仍踩地")
    ap.add_argument("--motion", default="", help="动作名=mocap-views.py 的 json，逗号分隔（如 walk=a.json,run=b.json）："
                                                   "这些动作改由 3D 动捕投影生成，替换程序写的同名动作")
    ap.add_argument("--damp-legs", type=float, default=None,
                    help="正 / 背面腿的减幅（默认同 --damp）。手臂全幅会甩到胸前，腿可以大一些（2026-10-10 用户：「腿的幅度有点小」）")
    ap.add_argument("--run-pose", default=None,
                    help="正 / 背面跑步关键姿势的层目录（seethrough-to-layers.py 对 config/run-pose-prompts.json 出的图）：画的是抬右膝、"
                         "左臂前摆；另一侧水平镜像。跑步按动捕相位在「抬右膝 / 过渡 / 抬左膝」之间换手、腿、衣身的图（剪纸骨骼画不出朝镜头弯的关节）")
    ap.add_argument("--run-pass", default=None,
                    help="跑步「过渡」关键姿势的层目录（双脚收在身下、右脚着地、两臂屈肘）；有它时一个循环换四张图：抬右膝 → 过渡 → 抬左膝 → 过渡（镜像）")
    ap.add_argument("--run-fist", default=None,
                    help="侧面：握拳版手臂的层目录（侧面图同画布只把手改成握拳再拆层）。跑步时手臂换成握拳，走路 / 待机仍是手掌"
                         "（2026-10-10 用户：侧面跑步是手掌、正 / 背面是握拳，对不上）")
    ap.add_argument("--run-threshold", type=float, default=0.6, help="脚踝离地超过各自最高点的这个比例才算「抬膝」帧")
    ap.add_argument("--leg-short", type=float, default=0.5,
                    help="正 / 背面腿的透视缩短保留多少（0–1，默认 0.5）：正面看跑步抬膝主要表现为腿缩短、脚抬高，"
                         "全量时直腿图被压扁像短腿，太少又抬不起脚")
    ap.add_argument("--damp", type=float, default=1.0,
                    help="正 / 背面动捕减幅（0–1）：摆动、关节弯曲、躯干倾斜、左右平移、透视缩短都乘这个系数，节奏和不对称仍来自动捕。"
                         "剪纸骨骼表现不了朝镜头弯曲的关节（正面看抬膝、屈肘前摆），全量时像僵腿滑步、手捂肚子（2026-10-10 用户反馈）")
    a = ap.parse_args()
    name = a.name or f"kurumi_{a.view}"
    leg_mode = a.leg_mode or ("dup" if a.view == "side" else "split")
    meta = json.load(open(os.path.join(a.layers_dir, "layers.json"), encoding="utf-8"))
    L = meta["layers"]
    W, H = meta["size"]
    os.makedirs(os.path.join(a.rig_dir, "images"), exist_ok=True)
    img_dir = os.path.join(a.rig_dir, "images")

    def load(n):
        return np.array(Image.open(os.path.join(a.layers_dir, f"{n}.png")).convert("RGBA"))

    lx, ly, lw, lh = L["legs"]["bbox"]
    ground = ly + lh
    hip_y = ly + 0.02 * lh
    # 膝 / 踝：髋 → 地面的比例
    kf, af = 0.386, 0.83
    refm = json.load(open(a.ref, encoding="utf-8")) if a.ref else (meta if meta.get("kp") else None)
    if refm and refm.get("kp"):
        kp = refm["kp"]
        rl = refm["layers"]["legs"]["bbox"]
        rg, rh = rl[1] + rl[3], rl[1] + 0.02 * rl[3]
        kf = ((kp[9][1] + kp[12][1]) / 2 - rh) / (rg - rh)
        af = ((kp[10][1] + kp[13][1]) / 2 - rh) / (rg - rh)
    knee_y = hip_y + kf * (ground - hip_y)
    ankle_y = hip_y + af * (ground - hip_y)

    # ---------- 腿：拆成两条 ----------
    legs_im = load("legs")
    legs = {}  # 角色侧 R / L → (图名, rgba, x0, y0)
    if leg_mode == "split":
        la, lb, cover = split_legs(legs_im[..., 3])
        # 正面：画面左 = 角色右；背面：画面左 = 角色左
        scr = {"left": la, "right": lb}
        side_of = {"left": "R", "right": "L"} if a.view == "front" else {"left": "L", "right": "R"}
        for k, al in scr.items():
            im = legs_im.copy()
            im[..., 3] = al
            ys, xs = np.nonzero(al > 8)
            x0, y0 = int(xs.min()), int(ys.min())
            crop = im[y0:ys.max() + 1, x0:xs.max() + 1]
            nm = f"leg_{side_of[k]}"
            Image.fromarray(crop).save(os.path.join(img_dir, f"{nm}.png"))
            legs[side_of[k]] = (nm, crop, lx + x0, ly + y0)
        print(f"腿：两腿之间有缝的行占 {cover:.0%}")
    else:
        Image.fromarray(legs_im).save(os.path.join(img_dir, "leg.png"))
        legs["R"] = ("leg", legs_im, lx, ly)  # 侧面朝右：近侧 = 角色右
        legs["L"] = ("leg", legs_im, lx, ly)

    def row_center(rgba, x0, y0, y, band=6):
        al = rgba[..., 3]
        r0, r1 = int(max(0, y - y0 - band)), int(min(al.shape[0], y - y0 + band + 1))
        cols = np.nonzero((al[r0:r1] > 127).any(0))[0]
        if len(cols) == 0:
            raise ValueError(f"y={y} 处没有像素")
        return x0 + (cols.min() + cols.max()) / 2

    leg_pts = {}
    for s, (nm, im, x0, y0) in legs.items():
        leg_pts[s] = [(row_center(im, x0, y0, hip_y + 0.04 * (ground - hip_y)), hip_y),
                      (row_center(im, x0, y0, knee_y), knee_y), (row_center(im, x0, y0, ankle_y), ankle_y)]
    cx = float(np.mean([leg_pts[s][0][0] for s in legs]))

    # ---------- 骨骼 ----------
    R = object.__new__(FR.Rig)
    R.meta, R.ldir, R.k, R.y0, R.ground, R.cx = meta, a.layers_dir, 1.0, 0.0, ground, cx
    R.bones, R.idx, R.world = [], {}, {}
    bx, by, bw, bh = L["body"]["bbox"]
    body_im = load("body")
    neck_y = by + 0.12 * bh
    head_y = by + 0.05 * bh
    hem_y = by + bh

    def lerp(p, q, t):
        return p + (q - p) * t
    belt_y = lerp(hip_y, neck_y, 0.33)
    R.bone("root", None, world=(0.0, 0.0))
    R.bone("hip", "root", (cx, hip_y))
    R.bone("waist", "hip", (row_center(body_im, bx, by, belt_y), belt_y))
    chest_y = lerp(hip_y, neck_y, 0.72)
    R.bone("chest", "waist", (row_center(body_im, bx, by, chest_y), chest_y))
    R.bone("neck", "chest", (row_center(body_im, bx, by, neck_y), neck_y))
    head_parts = [n for n in ["hair_back", "hair_front", "face", "headwear"] if n in L]
    hx0 = min(L[n]["bbox"][0] for n in head_parts)
    hx1 = max(L[n]["bbox"][0] + L[n]["bbox"][2] for n in head_parts)
    hy0 = min(L[n]["bbox"][1] for n in head_parts)
    head_cx = (hx0 + hx1) / 2
    R.bone("head", "neck", (row_center(body_im, bx, by, head_y + 0.02 * bh), head_y))
    for s in legs:
        P = leg_pts[s]
        R.bone_toward(f"thigh_{s}", "hip", P[0], P[1])
        R.bone_toward(f"shin_{s}", f"thigh_{s}", P[1], P[2])
        R.bones[R.idx[f"shin_{s}"]]["inherit"] = "noScale"  # 大腿沿长度缩放（透视缩短）时小腿不被拉歪
    # 手臂
    arms = {}  # 角色侧 → (图名, rgba, x0, y0, 链)
    # 面积太小的手臂层不算（侧面只看得到一只手，See-through 另一侧常给出 1×1 的空层）
    arm_layers = [n for n in ("arm_R", "arm_L") if n in L and L[n]["area"] > 0.002 * W * H]
    votes = meta.get("arm_front_votes") or {}
    if a.view == "side":
        # 侧面：衣身前面那只是近侧（= 角色右，侧面朝右），另一只（若有）是远侧
        arm_layers.sort(key=lambda n: -votes.get(n, 0.5))
        near = arm_layers[0]
        far = arm_layers[1] if len(arm_layers) > 1 else near
        roles = {"R": near, "L": far}
    elif a.view == "front":
        roles = {"R": "arm_R", "L": "arm_L"}  # See-through -r = 画面左 = 正面时角色右
    else:
        roles = {"L": "arm_R", "R": "arm_L"}  # 背面：画面左是角色左
    if a.view != "side" and len(arm_layers) < 2:
        raise SystemExit(f"正 / 背面需要两只手臂层，现在只有 {arm_layers}")
    for s, ln in roles.items():
        im = load(ln)
        x0, y0 = L[ln]["bbox"][:2]
        ys_, xs_ = np.nonzero(im[..., 3] > 127)
        top = (float(xs_[np.argmin(ys_)] + x0), float(ys_.min() + y0))
        chain = tail_path(im[..., 3], x0, y0, top, 3, fracs=[0.0, 0.40, 0.74, 1.0])
        arms[s] = (ln, im, x0, y0, chain)
        S_, E_, W_, T_ = chain
        R.bone_toward(f"arm_{s}", "chest", S_, E_)
        R.bone_toward(f"fore_{s}", f"arm_{s}", E_, W_)
        R.bone_toward(f"hand_{s}", f"fore_{s}", W_, T_)
        for b in (f"fore_{s}", f"hand_{s}"):
            R.bones[R.idx[b]]["inherit"] = "noScale"
    # 裙摆骨骼
    if a.view == "side":
        rows = np.nonzero((body_im[int(hem_y - by - 12):int(hem_y - by - 4), :, 3] > 127).any(0))[0]
        skirt_x = {"B": bx + rows.min() + 0.15 * (rows.max() - rows.min()), "F": bx + rows.max() - 0.15 * (rows.max() - rows.min())}
    else:
        skirt_x = {"R": cx - 0.3 * bw, "C": cx, "L": cx + 0.3 * bw}
    for k, x in skirt_x.items():
        R.bone_toward(f"skirt_{k}", "waist", (lerp(cx, x, 0.5), belt_y), (x, hem_y))
    # 发梢（物理）
    tips = {}
    for hl in ("hair_front", "hair_back"):
        if hl not in L:
            continue
        x0, y0, w0, h0 = L[hl]["bbox"]
        for s, fx in (("a", 0.15), ("b", 0.85)):
            top = (x0 + w0 * fx, y0 + 0.45 * h0)
            bot = (x0 + w0 * fx, y0 + 0.95 * h0)
            R.bone_toward(f"{hl}_tip_{s}", "head", top, bot)
            tips[(hl, s)] = (top, bot)

    # ---------- 附件 ----------
    skin, slots, stats = {}, [], {}

    def copy_img(n):
        dst = os.path.join(img_dir, f"{n}.png")
        if not os.path.isfile(dst):
            shutil.copy(os.path.join(a.layers_dir, f"{n}.png"), dst)

    def slot(sn, bone, att, color=None):
        s = {"name": sn, "bone": bone, "attachment": att}
        if color:
            s["color"] = color
        slots.append(s)

    def region(sn, n, bone):
        copy_img(n)
        x, y, w, h = L[n]["bbox"]
        lx_, ly_ = R.to_local(bone, *R.S((x + w / 2, y + h / 2)))
        skin.setdefault(sn, {})[n] = {"x": round(lx_, 2), "y": round(ly_, 2), "rotation": round(-R.world[bone][2], 2),
                                      "width": w, "height": h}

    def mesh(sn, att, im, x0, y0, weight_fn, spacing):
        pts, tris, hull = build_mesh(im[..., 3], spacing * W / 832.0)
        h, w = im.shape[:2]
        verts, uvs = [], []
        for p in pts:
            px = (x0 + p[0], y0 + p[1])
            ws = {k: v for k, v in weight_fn(px).items() if v > 0.01}
            ws = dict(sorted(ws.items(), key=lambda kv: -kv[1])[:4])
            tot = sum(ws.values())
            verts.append(len(ws))
            for bn, wt in ws.items():
                lx_, ly_ = R.to_local(bn, *R.S(px))
                verts += [R.idx[bn], round(lx_, 2), round(ly_, 2), round(wt / tot, 4)]
            uvs += [round(p[0] / w, 5), round(p[1] / h, 5)]
        skin.setdefault(sn, {})[att] = {"type": "mesh", "uvs": uvs, "triangles": tris.reshape(-1).tolist(),
                                        "vertices": verts, "hull": int(hull), "width": w, "height": h}
        stats[sn] = (len(pts), len(tris))

    def seg_param(p, P):
        """点 p 投到折线 P 上的弧长参数（像素）与各段累计长度。"""
        P = [np.array(q, float) for q in P]
        cum, best, u = [0.0], 1e18, 0.0
        for i in range(len(P) - 1):
            d = P[i + 1] - P[i]
            ln = float(np.linalg.norm(d))
            t = float(np.clip(np.dot(np.array(p) - P[i], d) / max(ln * ln, 1e-6), 0, 1))
            dist = float(np.linalg.norm(P[i] + d * t - p))
            if dist < best:
                best, u = dist, cum[-1] + t * ln
            cum.append(cum[-1] + ln)
        return u, cum

    def chain_w(names, P, anchor, anchor_k):
        """沿链分给各骨骼，关节两侧 ±8% 链长过渡；链根 anchor_k × 第一段长以内混入 anchor（接在身上）。"""
        def fn(p):
            u, cum = seg_param(p, P)
            band = 0.08 * cum[-1]
            ws = {}
            for i, n in enumerate(names):
                lo = 1.0 if i == 0 else smooth((u - cum[i] + band) / (2 * band))
                hi = 1.0 if i == len(names) - 1 else 1 - smooth((u - cum[i + 1] + band) / (2 * band))
                ws[n] = float(lo * hi)
            tot = sum(ws.values()) or 1.0
            ws = {k: v / tot for k, v in ws.items()}
            wa = float(1 - smooth(u / (anchor_k * (cum[1] - cum[0]))))
            ws = {k: v * (1 - wa) for k, v in ws.items()}
            ws[anchor] = ws.get(anchor, 0) + wa
            return ws
        return fn

    def w_body(p):
        y = p[1]
        ws = {}
        nw = float(1 - smooth((y - (neck_y - 0.03 * bh)) / (0.08 * bh)))
        ws["neck"] = nw
        cw = float(1 - smooth((y - (belt_y - 0.05 * bh)) / (0.1 * bh))) * (1 - nw)
        ws["chest"] = cw
        rest = 1 - nw - cw
        sk = float(smooth((y - belt_y) / max(hem_y - belt_y, 1))) ** 1.2
        ws["waist"] = rest * (1 - sk)
        xs = np.array(list(skirt_x.values()))
        g = np.exp(-((p[0] - xs) / (0.25 * bw)) ** 2) + 1e-9
        g /= g.sum()
        for k, gg in zip(skirt_x, g):
            ws[f"skirt_{k}"] = rest * sk * float(gg)
        return ws

    def w_hair(hl):
        def fn(p):
            (ta, ba), (tb, bb) = tips[(hl, "a")], tips[(hl, "b")]
            s = "a" if abs(p[0] - ta[0]) < abs(p[0] - tb[0]) else "b"
            top, bot = tips[(hl, s)]
            t = float(smooth((p[1] - top[1]) / max(bot[1] - top[1], 1)))
            return {"head": 1 - t, f"{hl}_tip_{s}": t}
        return fn

    shade = "%02x%02x%02xff" % ((int(255 * a.far_shade),) * 3)

    def leg_slot(s, color=None):
        nm, im, x0, y0 = legs[s]
        P = leg_pts[s]
        slot(f"leg_{s}", f"thigh_{s}", nm, color)
        mesh(f"leg_{s}", nm, im, x0, y0, chain_w([f"thigh_{s}", f"shin_{s}"], P, "hip", 0.25), 22)

    def arm_slot(s, color=None):
        ln, im, x0, y0, chain = arms[s]
        copy_img(ln)
        slot(f"arm_{s}", f"arm_{s}", ln, color)
        mesh(f"arm_{s}", ln, im, x0, y0, chain_w([f"arm_{s}", f"fore_{s}", f"hand_{s}"], chain, "chest", 0.35), 14)

    def hair_slot(hl):
        if hl in L:
            copy_img(hl)
            slot(hl, "head", hl)
            mesh(hl, hl, load(hl), *L[hl]["bbox"][:2], w_hair(hl), 12)

    def head_slots():
        for n in HEAD_PARTS:
            if n in L:
                slot(n, "head", n)
                region(n, n, "head")
        if "face_closed" in L:
            region("face", "face_closed", "head")
        for s in "RL":
            if f"eye_closed_{s}" in L and f"lash_{s}" in L:
                region(f"lash_{s}", f"eye_closed_{s}", "head")
        if "headwear" in L:
            slot("headwear", "head", "headwear")
            region("headwear", "headwear", "head")

    def body_slot():
        copy_img("body")
        slot("body", "chest", "body")
        mesh("body", "body", body_im, bx, by, w_body, 16)

    def arms_by_vote(front):
        out = []
        for s, (ln, *_r) in arms.items():
            if (votes.get(ln, 0.0) >= 0.5) == front:
                out.append(s)
        return out

    if a.view == "front":
        hair_slot("hair_back")
        leg_slot("R"); leg_slot("L")
        for s in arms_by_vote(False):
            arm_slot(s)
        body_slot()
        for s in arms_by_vote(True):
            arm_slot(s)
        head_slots()
        hair_slot("hair_front")
    elif a.view == "back":
        # 背面：See-through 按远近分前后发——背面图里的「前发」是离镜头最近、带高光的后脑头发，「后发」是下面一层衬底
        # （2026-10-10 实测），所以顺序和正面一样；没有脸部层
        hair_slot("hair_back")
        leg_slot("R"); leg_slot("L")
        for s in arms_by_vote(False):
            arm_slot(s)
        body_slot()
        for s in arms_by_vote(True):
            arm_slot(s)
        head_slots()
        hair_slot("hair_front")
    else:
        # 侧面（朝右）：远侧（角色左）的手、脚压暗放最后面
        arm_slot("L", shade)
        leg_slot("L", shade)
        hair_slot("hair_back")
        leg_slot("R")
        body_slot()
        head_slots()
        hair_slot("hair_front")
        arm_slot("R")

    # ---------- 跑步关键姿势（换图）----------
    # A = 抬右膝（--run-pose 原图），B = A 的镜像（抬左膝）；PA = 过渡（--run-pass 原图，右脚着地），PB = PA 的镜像。
    # 镜像以角色髋部中线 cx 为轴，画面左右对调，层名 R / L 对调。手臂按各自那张图的深度投票放在衣身前 / 后
    pose = None
    if a.run_pose and a.view != "side":
        names_slot = [x["name"] for x in slots]
        li = min(names_slot.index(n) for n in names_slot if n.startswith("leg_"))
        bi = names_slot.index("body")
        for at, sn in sorted([(li, "pose_legs"), (bi, "pose_arm_R_b"), (bi, "pose_arm_L_b"),
                              (bi + 1, "pose_arm_R_f"), (bi + 1, "pose_arm_L_f")], key=lambda t: -t[0]):
            slots.insert(at, {"name": sn, "bone": "hip" if sn == "pose_legs" else "chest"})

        def put_region(sn, att, im, bbox, bone):
            Image.fromarray(im).save(os.path.join(img_dir, f"{att}.png"))
            x, y, w, h = bbox
            lx_, ly_ = R.to_local(bone, *R.S((x + w / 2, y + h / 2)))
            skin.setdefault(sn, {})[att] = {"x": round(lx_, 2), "y": round(ly_, 2), "rotation": round(-R.world[bone][2], 2),
                                            "width": w, "height": h}
        # 腿比裙子近的部分（seethrough-to-layers.py 的 legs_over，正面抬膝时的大腿）画在衣身前、前侧手臂后
        slots.insert([x["name"] for x in slots].index("body") + 1, {"name": "pose_legs_over", "bone": "hip"})
        pose = {"legs": {}, "body": {}, "arm": {}, "legs_over": {}}
        sources = [("A", a.run_pose, False), ("B", a.run_pose, True)]
        if a.run_pass:
            sources += [("PA", a.run_pass, False), ("PB", a.run_pass, True)]
        for key, d_, mirror in sources:
            PM = json.load(open(os.path.join(d_, "layers.json"), encoding="utf-8"))
            PL, pv = PM["layers"], PM.get("arm_front_votes") or {}

            def get(n):
                im = np.array(Image.open(os.path.join(d_, f"{n}.png")).convert("RGBA"))
                x, y, w, h = PL[n]["bbox"]
                if mirror:
                    return im[:, ::-1].copy(), [int(round(2 * cx - (x + w))), y, w, h]
                return im, [x, y, w, h]
            put_region("pose_legs", f"run_legs_{key}", *get("legs"), "hip")
            pose["legs"][key] = f"run_legs_{key}"
            if "legs_over" in PL:
                put_region("pose_legs_over", f"run_legsover_{key}", *get("legs_over"), "hip")
                pose["legs_over"][key] = f"run_legsover_{key}"
            if "body" in PL:
                bim, bbb = get("body")
                al_ = bim[..., 3][bim[..., 3] > 8]
                semi = float((al_ < 200).mean()) if al_.size else 1.0
                if semi > 0.08:
                    # See-through 偶尔把衣身拆成半透明（2026-10-10 过渡姿势正面 15%，其余 2–3%），裙子会透出大腿：沿用原衣身
                    print(f"警告：{key} 的衣身层 {semi:.0%} 像素半透明，不换衣身")
                else:
                    put_region("body", f"run_body_{key}", bim, bbb, "chest")
                    pose["body"][key] = f"run_body_{key}"
            for ln in ("arm_R", "arm_L"):
                if ln not in PL or PL[ln]["area"] < 0.002 * W * H:
                    continue
                tgt = ln if not mirror else ("arm_L" if ln == "arm_R" else "arm_R")
                sn = f"pose_{tgt}_{'f' if pv.get(ln, 0.0) >= 0.5 else 'b'}"
                put_region(sn, f"run_{tgt}_{key}", *get(ln), "chest")
                pose["arm"].setdefault(key, []).append((sn, f"run_{tgt}_{key}"))
        print("跑步关键姿势：", {k: v for k, v in pose["arm"].items()})

    # ---------- 物理 ----------
    physics = []
    for (hl, s) in tips:
        physics.append({"name": f"phys_{hl}_{s}", "bone": f"{hl}_tip_{s}", "rotate": 1, "x": 0.6, "y": 0.6,
                        "inertia": 0.5, "strength": 55, "damping": 0.85})
    for k in skirt_x:
        # 侧面裙摆的 x（对移动冲量的惯性）降到 0.25：0.6 时跑起来前摆被整段往后拖
        physics.append({"name": f"phys_skirt_{k}", "bone": f"skirt_{k}", "rotate": 0.6 if k != "C" else 0.5,
                        "x": 0.25 if a.view == "side" else 0.6,
                        "y": 0.6, "inertia": 0.6, "strength": 70, "damping": 0.8})
    for i, c in enumerate(physics):
        c.update({"order": i, "limit": 5000, "fps": 60, "mass": 1})

    # ---------- 动作 ----------
    anims = {}

    def keys(an, bone, prop, dur, fn):
        n = max(1, int(round(dur * FPS)))
        tl = anims.setdefault(an, {}).setdefault("bones", {}).setdefault(bone, {}).setdefault(prop, [])
        for i in range(n + 1):
            t = i / FPS
            v = fn(t / dur if dur else 0.0, t)
            k = {"time": round(t, 4)}
            if prop == "rotate":
                k["value"] = round(float(v), 3)
            else:
                k["x"], k["y"] = round(float(v[0]), 4), round(float(v[1]), 4)
            tl.append(k)

    Hc = ground - hy0  # 角色高（像素）
    l1 = {s: math.dist(leg_pts[s][0], leg_pts[s][1]) for s in legs}
    l2 = {s: math.dist(leg_pts[s][1], leg_pts[s][2]) for s in legs}
    phase = {"R": 0.0, "L": 0.5}
    # 正面画面左是角色右（x < 0），背面相反：支撑腿一侧的屏幕方向
    scr_sign = {"R": -1, "L": 1} if a.view == "front" else {"R": 1, "L": -1}

    def idle():
        an = "idle"
        keys(an, "chest", "translate", IDLE_T, lambda u, t: (0, 0.0025 * Hc * math.sin(TAU * u)))
        keys(an, "chest", "scale", IDLE_T, lambda u, t: (1, 1 + 0.008 * math.sin(TAU * u)))
        keys(an, "head", "rotate", IDLE_T, lambda u, t: 1.0 * math.sin(TAU * u + 0.8))
        keys(an, "hip", "translate", IDLE_T, lambda u, t: (0.002 * Hc * math.sin(TAU * u * 0.5), 0))
        for s in arms:
            sg = scr_sign.get(s, 1) if a.view != "side" else 1
            keys(an, f"arm_{s}", "rotate", IDLE_T, lambda u, t, sg=sg: sg * 1.2 * math.sin(TAU * u + 0.6))
        for s in legs:  # 走 / 跑会改腿的旋转和缩放，待机要写回来（动作混合时才不会残留）
            for b in (f"thigh_{s}", f"shin_{s}"):
                keys(an, b, "rotate", 0, lambda u, t: 0)
                keys(an, b, "scale", 0, lambda u, t: (1, 1))
        keys(an, "hip", "rotate", 0, lambda u, t: 0)
        keys(an, "chest", "rotate", 0, lambda u, t: 0)
        for s in arms:
            keys(an, f"fore_{s}", "rotate", 0, lambda u, t: 0)
            keys(an, f"arm_{s}", "scale", 0, lambda u, t: (1, 1))
        # 眨眼（只有正面的闭眼层）
        blink = [s for s in "RL" if f"eye_closed_{s}" in L and f"lash_{s}" in L]
        if blink:
            slt = anims[an].setdefault("slots", {})
            for s in blink:
                slt[f"lash_{s}"] = {"attachment": [{"time": 0, "name": f"lash_{s}"}, {"time": 2.2, "name": f"eye_closed_{s}"},
                                                   {"time": 2.33, "name": f"lash_{s}"}]}
                for part in (f"eyewhite_{s}", f"iris_{s}"):
                    if part in L:
                        slt[part] = {"attachment": [{"time": 0, "name": part}, {"time": 2.2, "name": None}, {"time": 2.33, "name": part}]}
            if "face_closed" in L:
                slt["face"] = {"attachment": [{"time": 0, "name": "face"}, {"time": 2.2, "name": "face_closed"}, {"time": 2.33, "name": "face"}]}

    def gait(an, T, run):
        if a.view == "side":
            A_th, A_kn, A_arm = (38, 75, 34) if run else (22, 32, 18)
            lean = -7 if run else -1.5

            def th(s, u):
                return A_th * math.sin(TAU * (u + phase[s]))

            def kn(s, u):
                c = math.cos(TAU * (u + phase[s]))
                return -A_kn * max(0.0, c) ** 1.3 - (12 if run else 4)

            def hip_dy(u):
                # 正向运动学：两只脚里低的那只踩在地上（骨骼静止时腿是竖直的近似）
                best = -1e9
                for s in legs:
                    a1, a2 = math.radians(th(s, u)), math.radians(th(s, u) + kn(s, u))
                    best = max(best, l1[s] * math.cos(a1) + l2[s] * math.cos(a2))
                rest = max(l1[s] + l2[s] for s in legs)
                return best - rest + (0.012 * Hc * max(0, math.sin(TAU * 2 * u)) if run else 0)
            for s in legs:
                keys(an, f"thigh_{s}", "rotate", T, lambda u, t, s=s: th(s, u))
                keys(an, f"shin_{s}", "rotate", T, lambda u, t, s=s: kn(s, u))
                keys(an, f"thigh_{s}", "scale", 0, lambda u, t: (1, 1))
                keys(an, f"shin_{s}", "scale", 0, lambda u, t: (1, 1))
            keys(an, "hip", "translate", T, lambda u, t: (0, hip_dy(u)))
            keys(an, "hip", "rotate", 0, lambda u, t: 0)
            keys(an, "chest", "rotate", T, lambda u, t: lean + 1.2 * math.sin(TAU * 2 * u))
            keys(an, "head", "rotate", T, lambda u, t: -0.6 * lean)
            for s in arms:
                # 手臂与同侧腿反相；前摆为正（朝右 = 逆时针）
                keys(an, f"arm_{s}", "rotate", T, lambda u, t, s=s: -A_arm * math.sin(TAU * (u + phase[s])))
                keys(an, f"fore_{s}", "rotate", T, lambda u, t, s=s:
                     (55 if run else 6) + (14 if run else 10) * max(0.0, -math.sin(TAU * (u + phase[s]))))
                keys(an, f"arm_{s}", "scale", 0, lambda u, t: (1, 1))
        else:
            # 正 / 背面：抬腿 = 沿骨骼方向缩短（scaleX 是骨骼长度方向）
            a1, a2 = (0.06, 0.30) if run else (0.025, 0.13)
            sway = (0.006 if run else 0.009) * Hc
            for s in legs:
                lift = lambda u, s=s: max(0.0, math.sin(TAU * (u + phase[s])))
                out = scr_sign[s]
                keys(an, f"thigh_{s}", "scale", T, lambda u, t, s=s, lift=lift: (1 - a1 * lift(u), 1))
                keys(an, f"shin_{s}", "scale", T, lambda u, t, lift=lift: (1 - a2 * lift(u), 1))
                # 外展：骨骼朝下（−90°），画面左腿外展 = 顺时针（负）
                keys(an, f"thigh_{s}", "rotate", T, lambda u, t, lift=lift, out=out: out * (2.5 if run else 1.5) * lift(u))
                keys(an, f"shin_{s}", "rotate", 0, lambda u, t: 0)
            # 重心移向支撑腿：R 抬起（u∈0–0.5）时支撑腿是 L
            keys(an, "hip", "translate", T, lambda u, t: (scr_sign["L"] * sway * math.sin(TAU * u), 0))
            keys(an, "hip", "rotate", T, lambda u, t: (1.5 if run else 1.0) * scr_sign["L"] * -math.sin(TAU * u))
            keys(an, "chest", "translate", T, lambda u, t: (0, (0.01 if run else 0.004) * Hc * abs(math.sin(TAU * u))))
            keys(an, "chest", "rotate", T, lambda u, t: (1.2 if run else 0.8) * scr_sign["L"] * math.sin(TAU * u))
            keys(an, "head", "rotate", T, lambda u, t: -0.5 * scr_sign["L"] * math.sin(TAU * u))
            for s in arms:
                other = "L" if s == "R" else "R"
                sw = lambda u, other=other: math.sin(TAU * (u + phase[other]))  # 与同侧腿反相
                out = scr_sign[s]
                k = 0.12 if run else 0.06
                keys(an, f"arm_{s}", "scale", T, lambda u, t, sw=sw: (1 - k * abs(sw(u)), 1))
                keys(an, f"arm_{s}", "rotate", T, lambda u, t, sw=sw, out=out: out * ((6 if run else 2.5) * abs(sw(u)) + (8 if run else 0)))
                keys(an, f"fore_{s}", "rotate", T, lambda u, t, sw=sw, out=out: -out * ((30 if run else 4) + (10 if run else 5) * max(0.0, sw(u))))

    def wrap_ang(x):
        return (np.asarray(x) + 180) % 360 - 180

    def motion(an, path):
        """3D 动捕投影（mocap-views.py）→ 本视角的骨骼动画。
        转角：美术静止姿势的世界角 +（投影角 − 投影角的循环平均），保住原画的站姿轮廓、带上动捕的摆动；
        缩放：投影长度 / 循环内最大投影长度（透视缩短，沿骨骼方向 = scaleX）；
        髋：水平按投影位移，竖直由两条腿的正向运动学定（低的那只脚踩地，腾空时按动捕里的离地高度抬起）。"""
        M = json.load(open(path, encoding="utf-8"))
        J = {n: i for i, n in enumerate(M["joints"])}
        V = np.array(M["views"][a.view])  # (帧, 关节, 2) 米
        F = len(V)
        fps_m = M["fps"]
        leg3d = np.mean([M["len3d"][f"thigh_{s}"] + M["len3d"][f"shin_{s}"] for s in "LR"])
        ppm = np.mean([l1[s] + l2[s] for s in legs]) / leg3d

        def seg(j0, j1):
            d = V[:, J[j1]] - V[:, J[j0]]
            ln = np.linalg.norm(d, axis=1)
            # 投影很短（骨骼几乎正对镜头，如正面看跑步时的前臂）时 2D 方向不可信、会乱跳：
            # 方向按 (1 − 投影长度 / 最大长度) 往「投影最长那一帧」的方向靠（2026-10-10 正面跑步实测手臂甩成水平）
            k = ln / max(ln.max(), 1e-6)
            ref = d[int(np.argmax(ln))] / max(ln.max(), 1e-6)
            de = d / np.maximum(ln, 1e-6)[:, None] * k[:, None] + ref[None] * (1 - k)[:, None] ** 2
            ang = np.degrees(np.unwrap(np.arctan2(de[:, 1], de[:, 0])))
            return ang, ln
        segs = M["segs"]
        absang, kk = {}, {}
        for b, (j0, j1) in segs.items():
            ang, ln = seg(j0, j1)
            absang[b] = ang
            kk[b] = np.clip(ln / M["len3d"][b], 0.4, 1.05)  # 投影长度 / 3D 真实长度
        # 骨盆倾斜（正 / 背面看得到两侧髋关节）
        # 肢体用绝对角（2D 骨骼世界角 = 投影角）：跑步时前臂在正面投影里转动超过 200°，
        # 「减循环平均角」的相对映射会把整条手臂转到外侧（2026-10-10 实测）
        if a.view != "side":
            lr = ("hip_R", "hip_L") if a.view == "front" else ("hip_L", "hip_R")
            pang, _ = seg(*lr)
            pelvis = (pang + 180) % 360 - 180
        else:
            pelvis = np.zeros(F)
        spine = absang["spine"] - 90 - pelvis * 0
        # 头相对脊柱：扣掉循环平均，只留点头的起伏。素体静止时头骨和「髋 → 颈」不平行，侧面走路平均差 18.9°、跑步 26.6°，
        # 直接用会让原画的头一直往后仰（2026-10-10 用户指出「左右走的时候头抬的角度偏高」）；正 / 背面只有 ±2°
        hs = absang["head"] - absang["spine"]
        headr = hs - hs.mean()
        if a.view != "side":
            headr = headr - (spine - spine.mean())  # 正 / 背面头基本保持竖直（3D 参照里跑步时头不随上身左右晃）
        wr = {b: R.world[b][2] for b in R.world}
        T = F / fps_m
        times = [i / fps_m for i in range(F + 1)]
        tl = anims.setdefault(an, {}).setdefault("bones", {})

        def put(bone, prop, vals):
            arr = tl.setdefault(bone, {}).setdefault(prop, [])
            for i, t in enumerate(times):
                v = vals[i % F]
                k = {"time": round(t, 4)}
                if prop == "rotate":
                    k["value"] = round(float(v), 3)
                else:
                    k["x"], k["y"] = round(float(v[0]), 4), round(float(v[1]), 4)
                arr.append(k)
        g = a.damp if a.view != "side" else 1.0
        gl = (a.damp_legs if a.damp_legs is not None else a.damp) if a.view != "side" else 1.0
        pelvis = pelvis * g
        spine = spine * g
        hipd = pelvis
        put("hip", "rotate", hipd)
        # waist 挂在 hip 下：局部角 = 脊柱世界角 − 骨盆倾斜（以前没减，骨盆被算两次，正面跑步头和上身左右歪得厉害）
        put("waist", "rotate", spine - hipd)
        put("chest", "rotate", np.zeros(F))
        put("head", "rotate", headr)
        chest_w = spine  # chest 的世界角增量
        # 正 / 背面：手臂、腿整条链先旋一个偏移 =「原画静止角 − 动捕循环平均角」，保留原画的站姿（手臂外展、站距），
        # 摆动和弯曲仍来自动捕；腿的透视缩短只取一半——2D 剪纸没有膝盖遮挡和明暗，缩到 40% 看着像腿变短的畸形
        # （2026-10-10 用户指出正 / 背面跑步「像畸形种」）。侧面原样
        front_like = a.view != "side"

        def circ_mean(x):
            r = np.radians(x)
            return float(np.degrees(np.arctan2(np.sin(r).mean(), np.cos(r).mean())))
        off = {}
        for s in list(legs) + list(arms):
            for root_b, chain in ((f"thigh_{s}", (f"thigh_{s}", f"shin_{s}")), (f"arm_{s}", (f"arm_{s}", f"fore_{s}", f"hand_{s}"))):
                if root_b in absang and root_b in wr:
                    o = ((wr[root_b] - circ_mean(absang[root_b]) + 180) % 360 - 180) if front_like else 0.0
                    for b in chain:
                        off[b] = o
        if front_like:
            for s in legs:
                for b in (f"thigh_{s}", f"shin_{s}"):
                    kk[b] = 1 - a.leg_short * gl * (1 - kk[b])
            for s in arms:
                for b in (f"arm_{s}", f"fore_{s}", f"hand_{s}"):
                    kk[b] = 1 - g * (1 - kk[b])

        def wrap(x):
            return (x + 180) % 360 - 180

        def target(b, par):
            """目标世界角。g < 1（正 / 背面减幅）时：链根 = 原画静止角 + g ×（投影角 − 循环平均）；
            子骨骼 = 父的目标角 + 静止时的相对角 + g × 投影里的关节弯曲。g = 1 时就是 投影角 + 站姿偏移。"""
            gg = gl if b.startswith(("thigh_", "shin_")) else g
            if gg >= 0.999 and g >= 0.999:
                return absang[b] + off.get(b, 0.0)
            if par is None:
                return wr[b] + gg * wrap(absang[b] - circ_mean(absang[b]))
            return wa[par] + (wr[b] - wr[par]) + gg * wrap(absang[b] - absang[par])
        if a.view == "side":
            sa = a.side_arms
            if "=" in sa:
                sa = dict(x.split("=") for x in sa.split(",")).get(an, "1.0")
            sa = float(sa)
            if sa != 1.0:
                # 上臂：相对循环平均角缩放；前臂、手的弯曲按同一系数向「静止时的相对角」靠
                for s_ in arms:
                    ra = absang[f"arm_{s_}"]
                    m_ = circ_mean(ra)
                    new_root = m_ + sa * wrap(ra - m_)
                    for b_, p_ in ((f"fore_{s_}", f"arm_{s_}"), (f"hand_{s_}", f"fore_{s_}")):
                        bend = wrap(absang[b_] - absang[p_])
                        absang[b_] = absang[p_] + (wr[b_] - wr[p_]) + sa * (bend - (wr[b_] - wr[p_]))
                    # 子骨骼依赖父骨骼的新角，按链从根往下重算
                    d0 = new_root - ra
                    absang[f"arm_{s_}"] = new_root
                    absang[f"fore_{s_}"] = absang[f"fore_{s_}"] + d0
                    absang[f"hand_{s_}"] = absang[f"hand_{s_}"] + d0
            if a.straighten > 0:
                for s_ in legs:
                    ah_ = V[:, J[f"ankle_{s_}"], 1]
                    stance = np.clip(1 - (ah_ - ah_.min()) / max(np.ptp(ah_) * 0.25, 1e-6), 0, 1)  # 1 = 着地
                    bend = wrap(absang[f"shin_{s_}"] - absang[f"thigh_{s_}"])
                    absang[f"shin_{s_}"] = absang[f"thigh_{s_}"] + bend * (1 - a.straighten * stance)
        wa = {}
        for s in legs:
            for b, par in ((f"thigh_{s}", None), (f"shin_{s}", f"thigh_{s}")):
                world = target(b, par)  # 目标世界角
                wa[b] = world
                if par is None:
                    loc = world - wr[b] - hipd
                else:
                    loc = world - wa[par] - (wr[b] - wr[par])
                put(b, "rotate", loc)
                put(b, "scale", [(k_, 1) for k_ in kk[b]])
        for s in arms:
            for b, par in ((f"arm_{s}", None), (f"fore_{s}", f"arm_{s}"), (f"hand_{s}", f"fore_{s}")):
                world = target(b, par)
                wa[b] = world
                loc = world - wr[b] - chest_w if par is None else world - wa[par] - (wr[b] - wr[par])
                put(b, "rotate", loc)
                put(b, "scale", [(k_, 1) for k_ in kk[b]])
        # 侧面裙摆跟腿：前摆跟往前迈得最远的大腿转，后摆跟往后的那条，物理叠在上面。
        # 只有物理时大腿前迈 38°、前摆反被移动冲量往后拖，腿从裙子前面穿出去（2026-10-10 用户指出）。思路同 vrm-dress.py 的裙子跟随大腿
        if a.view == "side" and "skirt_F" in R.idx:
            dev = np.stack([wrap_ang(wa[f"thigh_{s_}"] - wr[f"thigh_{s_}"]) for s_ in legs])  # 正 = 往前（朝右）
            fwd, back = dev.max(0), dev.min(0)
            # 大腿超过 12° 才推（裙子本身有松量），走路基本不动、跑步照常撩起；以前走路每步前摆都往前甩
            put("skirt_F", "rotate", [0.85 * max(0.0, v - 12) - 0.1 * hipd[i] for i, v in enumerate(fwd)])
            put("skirt_B", "rotate", [0.6 * min(0.0, v + 12) for v in back])
        # 髋位移：水平 = 投影位移；竖直 = 正向运动学让低的那只脚落在「地面 + 动捕离地高度」
        hx = V[:, J["hips"], 0]
        ank_h = np.minimum(V[:, J["ankle_L"], 1], V[:, J["ankle_R"], 1])
        lift = (ank_h - ank_h.min()) * ppm
        hip0 = R.world["hip"]
        rest_ank = min(R.world[f"shin_{s}"][1] - l2[s] for s in legs)  # 静止时踝的高度（腿近似竖直）
        dys = []
        for i in range(F):
            low = 1e9
            for s in legs:
                a1, a2 = math.radians(wa[f"thigh_{s}"][i]), math.radians(wa[f"shin_{s}"][i])
                y = l1[s] * kk[f"thigh_{s}"][i] * math.sin(a1) + l2[s] * kk[f"shin_{s}"][i] * math.sin(a2)
                low = min(low, y)
            dys.append(rest_ank + lift[i] - (hip0[1] + low))
        dys = np.array(dys)
        put("hip", "translate", [((hx[i] - hx.mean()) * ppm * g, dys[i]) for i in range(F)])
        put("chest", "translate", [(0, 0)] * F)
        # 绘制顺序：正 / 背面按深度逐帧排手臂（手腕比躯干近 → 画到衣身前面）和两条腿（近的在前）
        if a.view != "side" and "depth" in M:
            D = np.array(M["depth"][a.view])
            torso = (D[:, J["hips"]] + D[:, J["neck"]]) / 2
            setup = [x["name"] for x in slots]
            movable = [n for n in setup if n.startswith(("arm_", "leg_"))]
            base = [n for n in setup if n not in movable]
            bi = base.index("body")
            prev, dkeys = None, []
            for i in range(F):
                front_arms = [f"arm_{s}" for s in arms if D[i, J[f"wrist_{s}"]] > torso[i] + 0.03]
                back_arms = [f"arm_{s}" for s in arms if f"arm_{s}" not in front_arms]
                legs_o = sorted([f"leg_{s}" for s in legs], key=lambda n: D[i, J["knee_" + n[-1]]])
                order = base[:bi] + legs_o + back_arms + [base[bi]] + front_arms + base[bi + 1:]
                if order != prev:
                    offs = [{"slot": n, "offset": order.index(n) - setup.index(n)} for n in setup
                            if n in movable and order.index(n) != setup.index(n)]
                    dkeys.append({"time": round(i / fps_m, 4), "offsets": offs} if offs else {"time": round(i / fps_m, 4)})
                    prev = order
            anims[an]["drawOrder"] = dkeys
        if pose and an == "run":
            # 相位：正面投影里两只脚踝的离地高度；抬得更高且超过各自最高点 45% 的帧换姿势图
            ah = {s_: V[:, J[f"ankle_{s_}"], 1] - V[:, J[f"ankle_{s_}"], 1].min() for s_ in "RL"}
            ph = []
            th = a.run_threshold
            for i in range(F):
                r_, l_ = ah["R"][i] / max(ah["R"].max(), 1e-6), ah["L"][i] / max(ah["L"].max(), 1e-6)
                ph.append("A" if r_ > th and r_ >= l_ else "B" if l_ > th and l_ > r_ else "")
            if "PA" in pose["legs"]:
                # 过渡帧：紧跟在 A（抬右膝）之后的是右脚着地 → PA；紧跟在 B 之后的 → PB（循环，往前找最近的抬膝帧）
                filled = list(ph)
                for i in range(F):
                    if not ph[i]:
                        j = i
                        while not ph[j % F]:
                            j -= 1
                        filled[i] = "PA" if ph[j % F] == "A" else "PB"
                ph = filled
            sl = anims[an].setdefault("slots", {})
            limb = [f"leg_{s_}" for s_ in legs] + [f"arm_{s_}" for s_ in arms]
            pslots = ["pose_legs", "pose_legs_over", "pose_arm_R_b", "pose_arm_L_b", "pose_arm_R_f", "pose_arm_L_f"]
            att_of = {x["name"]: x.get("attachment") for x in slots}
            seqs = {n: [] for n in limb + pslots + ["body"]}
            prev = None
            for i, k in enumerate(ph + [ph[0]]):
                t = round(i / fps_m, 4)
                if k == prev:
                    continue
                prev = k
                for n in limb:
                    seqs[n].append({"time": t, "name": None if k else att_of[n]})
                arm_map = dict(pose["arm"].get(k, [])) if k else {}
                for n in pslots:
                    nm = (pose["legs"].get(k) if n == "pose_legs" else pose["legs_over"].get(k) if n == "pose_legs_over"
                          else arm_map.get(n)) if k else None
                    seqs[n].append({"time": t, "name": nm})
                seqs["body"].append({"time": t, "name": pose["body"].get(k, "body") if k else "body"})
            for n, seq in seqs.items():
                sl.setdefault(n, {})["attachment"] = seq
            # 换图帧和直腿帧用同一种髋高：按动捕髋部高度的起伏（直腿正向运动学在换图帧没有意义，混用会在换图那一帧跳）
            hy = V[:, J["hips"], 1]
            bob = (hy - hy.max()) * ppm * 0.8
            tl["hip"]["translate"] = []
            put("hip", "translate", [((hx[i] - hx.mean()) * ppm * g, bob[i]) for i in range(F)])
            motion_pose = " ".join(x or "." for x in ph)
            print(f"跑步换图相位（A 抬右膝 / B 抬左膝 / PA PB 过渡 / . 原图）：{motion_pose}")
        return {"frames": F, "duration": T, "ppm": float(ppm), "speed_px_s": float(M["speed_mps"] * ppm),
                "clip": M["clip"]}

    idle()
    gait("walk", WALK_T, False)
    gait("run", RUN_T, True)
    motion_info = {}
    for spec in [x for x in a.motion.split(",") if x]:
        an, path = spec.split("=", 1)
        anims.pop(an, None)
        motion_info[an] = motion(an, path)
    # 侧面跑步换握拳手臂：握拳图里面积最大的手臂层（近侧），按原手臂的骨骼链和权重做网格，近侧、远侧两个插槽都放
    if a.run_fist and a.view == "side":
        FM = json.load(open(os.path.join(a.run_fist, "layers.json"), encoding="utf-8"))
        cand = [n for n in ("arm_R", "arm_L") if n in FM["layers"]]
        fn_ = max(cand, key=lambda n: FM["layers"][n]["area"])
        fim = np.array(Image.open(os.path.join(a.run_fist, f"{fn_}.png")).convert("RGBA"))
        fx0, fy0 = FM["layers"][fn_]["bbox"][:2]
        Image.fromarray(fim).save(os.path.join(img_dir, "arm_fist.png"))
        for s_, (ln, im_, x0_, y0_, chain_) in arms.items():
            mesh(f"arm_{s_}", "arm_fist", fim, fx0, fy0,
                 chain_w([f"arm_{s_}", f"fore_{s_}", f"hand_{s_}"], chain_, "chest", 0.35), 14)
        for an in anims:
            sl_ = anims[an].setdefault("slots", {})
            for s_, (ln, *_r) in arms.items():
                sl_.setdefault(f"arm_{s_}", {})["attachment"] = [{"time": 0, "name": "arm_fist" if an == "run" else ln}]
        print(f"侧面跑步握拳：用 {a.run_fist} 的 {fn_}")

    sk = {"skeleton": {"hash": f"dir-rig-{a.view}", "spine": "4.2.43", "x": -cx, "y": 0.0, "width": W, "height": H,
                       "images": "./images/"},
          "bones": R.bones, "slots": slots, "physics": physics,
          "skins": [{"name": "default", "attachments": skin}], "animations": anims}
    json.dump(sk, open(os.path.join(a.rig_dir, f"{name}.json"), "w"), ensure_ascii=False)
    info = {"view": a.view, "height": Hc, "ground": ground, "cx": cx, "hip_y": hip_y, "knee_y": knee_y, "ankle_y": ankle_y,
            "knee_frac": kf, "ankle_frac": af, "leg_mode": leg_mode, "arms": {s: v[0] for s, v in arms.items()},
            "slots": [s["name"] for s in slots], "motion": motion_info}
    json.dump(info, open(os.path.join(a.rig_dir, f"{name}.rigmeta.json"), "w"), ensure_ascii=False, indent=1)
    print(f"{name}: bones={len(R.bones)} slots={len(slots)} physics={len(physics)} 角色高 {Hc:.0f}px")
    for k, (nv, nt) in stats.items():
        print(f"  mesh {k}: {nv} 顶点 / {nt} 三角形")


if __name__ == "__main__":
    main()
