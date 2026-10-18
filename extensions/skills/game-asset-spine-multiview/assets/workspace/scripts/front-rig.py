"""正面分层 → Spine 4.2 骨骼（仿 ryza-ai-revive 正面立绘的做法）。

用法：python -I scripts/front-rig.py <layers_dir> <rig_dir> [--name kurumi_front]
输入 front-layers.py 的输出（layers.json + 各层 PNG）。输出 <rig_dir>/<name>.json 与 images/，之后：
  spine-pack.py <rig_dir> --name <name>   → atlas / preview.html
  node scripts/spine-verify.mjs <rig_dir> <name>
  node scripts/spine-render.mjs <job.json> <out>   （可驱动 aim_* 控制骨骼演示视线）

参考模型的机制（spine-inspect.mjs 拆出来的，见 reports/front-rig-ryza-2026-10-09.md）在这里的对应：
- 视差转头：控制骨骼 aim_head / aim_eye / aim_body 挂在根骨骼下、静止位置 (0,0)；跟随骨骼用「局部 + 相对」的
  变换约束按不同比例吃它的位移（五官 0.6–0.75、刘海 0.55、侧发 0.12、后发 −0.22、脸中心 0.4 而脸轮廓少），
  游戏里按光标 / 视线直接改 aim_* 的 x、y（与 ryza 的 avatar.js 相同）。
- 网格：大层（脸、头发、身体、腿、手臂）按透明度自动生成网格（轮廓 + 内部网格点 + Delaunay），按位置算多骨骼权重。
- 物理：发梢、刘海、裙摆用 Spine 4.2 物理约束（运行时模拟，不烘焙）。
- 表情 / 眨眼 / 口型：同一插槽多个附件切换；虹膜用裁剪附件限制在眼白内。
- 手势：挥手换一张举手的手臂图（ryza 的手臂也是按手势换图）。
骨骼位置全部来自 DWPose 关键点和各层包围盒，没有按角色写死的像素常数。
"""
import argparse
import json
import math
import os
import shutil

import cv2
import numpy as np
from PIL import Image
from scipy.spatial import Delaunay

FPS = 30


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


class Rig:
    def __init__(self, meta, ldir, k=1.0, y0=0.0):
        self.meta, self.ldir = meta, ldir
        self.k, self.y0 = k, y0  # 像素 → Spine 世界单位的缩放、整体竖直偏移（导入 ryza 时对齐它的尺度）
        kp = meta["kp"]
        legs = meta["layers"]["legs"]["bbox"]
        self.ground = legs[1] + legs[3]
        self.cx = (kp[8][0] + kp[11][0]) / 2
        self.bones, self.idx = [], {}
        self.world = {}  # name -> (x, y, rot_deg) in Spine 坐标（y 向上）

    def S(self, p):
        return (float((p[0] - self.cx) * self.k), float((self.ground - p[1]) * self.k + self.y0))

    def bone(self, name, parent, p_px=None, rot=0.0, length=0.0, world=None):
        wx, wy = world if world is not None else self.S(p_px)
        if parent:
            px, py, pr = self.world[parent]
            c, s = math.cos(math.radians(-pr)), math.sin(math.radians(-pr))
            dx, dy = wx - px, wy - py
            lx, ly = c * dx - s * dy, s * dx + c * dy
            wrot = pr + rot
        else:
            lx, ly, wrot = wx, wy, rot
        b = {"name": name, "x": round(lx, 2), "y": round(ly, 2)}
        if parent:
            b["parent"] = parent
        if rot:
            b["rotation"] = round(rot, 2)
        if length:
            b["length"] = round(length, 2)
        self.idx[name] = len(self.bones)
        self.bones.append(b)
        self.world[name] = (wx, wy, wrot)
        return name

    def bone_toward(self, name, parent, a_px, b_px, length=None):
        """骨骼从 a 指向 b（世界旋转 = 方向角），返回局部旋转。"""
        ax, ay = self.S(a_px)
        bx, by = self.S(b_px)
        ang = math.degrees(math.atan2(by - ay, bx - ax))
        pr = self.world[parent][2] if parent else 0
        return self.bone(name, parent, a_px, rot=ang - pr, length=length or math.hypot(bx - ax, by - ay))

    def to_local(self, bone, wx, wy):
        bx, by, br = self.world[bone]
        c, s = math.cos(math.radians(-br)), math.sin(math.radians(-br))
        dx, dy = wx - bx, wy - by
        return c * dx - s * dy, s * dx + c * dy


def tail_path(alpha, x0, y0, near, n, fracs=None):
    """部件的中轴：蒙版内从离 near 最近的点出发，走到测地距离最远的点（scikit-image MCP_Geometric 最短路径），
    沿路径等距取 n + 1 个点，或按 fracs（0–1 的路径长度比例）取点（原图像素坐标）。尾巴、手臂用。"""
    from skimage.graph import MCP_Geometric
    m = alpha > 127
    ys, xs = np.nonzero(m)
    i0 = int(np.argmin((xs + x0 - near[0]) ** 2 + (ys + y0 - near[1]) ** 2))
    cost = np.where(m, 1.0, np.inf)
    mcp = MCP_Geometric(cost)
    dist, _ = mcp.find_costs([(ys[i0], xs[i0])])
    dist = np.where(np.isfinite(dist), dist, -1)
    end = np.unravel_index(int(np.argmax(dist)), dist.shape)
    path = np.array(mcp.traceback(end), float)[:, ::-1]  # (x, y)
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(path, axis=0).T))]
    fr = fracs if fracs is not None else [k / n for k in range(n + 1)]
    pts = [path[int(np.searchsorted(seg, seg[-1] * f_).clip(0, len(path) - 1))] for f_ in fr]
    return [(float(p[0] + x0), float(p[1] + y0)) for p in pts]


def build_mesh(alpha, spacing):
    """透明度 → 网格：外轮廓（简化后按 spacing 重采样）+ 内部规则点，Delaunay 后去掉落在透明处的三角形。"""
    m = (alpha > 25).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    # 外轮廓取「任何非零透明度膨胀 2px」的边：网格必须完整盖住半透明的抗锯齿边，否则多边形边缘直接切出锯齿
    mo = cv2.dilate((alpha > 0).astype(np.uint8), np.ones((5, 5), np.uint8))
    # 内部的洞（前发中间脸的位置）的边也要取点：只取外轮廓时，洞上方那条细刘海带上的三角形都跨过洞口，
    # 会被下面的判定整片删掉，渲染时露出底下的脸（2026-10-09 2K 实测发夹旁一块皮肤色）
    cs, _ = cv2.findContours(mo, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    cs = [c for c in cs if cv2.contourArea(c) > 30]
    cs.sort(key=cv2.contourArea, reverse=True)
    pts, hull_n = [], 0
    for k, c in enumerate(cs):
        ap = cv2.approxPolyDP(c, 1.2, True).reshape(-1, 2).astype(float)
        seg = []
        for i in range(len(ap)):
            a, b = ap[i], ap[(i + 1) % len(ap)]
            n = max(1, int(math.ceil(np.linalg.norm(b - a) / spacing)))
            seg += [a + (b - a) * j / n for j in range(n)]
        pts += seg
        if k == 0:
            hull_n = len(seg)
    dist = cv2.distanceTransform(m, cv2.DIST_L2, 3)
    h, w = m.shape
    for y in np.arange(spacing / 2, h, spacing):
        for x in np.arange(spacing / 2, w, spacing):
            if dist[int(y), int(x)] > spacing * 0.45:
                pts.append(np.array([x, y]))
    pts = np.array(pts)
    pts[:, 0] = np.clip(pts[:, 0], 0, w)
    pts[:, 1] = np.clip(pts[:, 1], 0, h)
    tri = Delaunay(pts)
    md = cv2.dilate(mo, np.ones((3, 3), np.uint8))

    def inside(p):
        x, y = int(min(max(p[0], 0), w - 1)), int(min(max(p[1], 0), h - 1))
        return md[y, x] > 0

    # 三角形只要盖到任何一个非零透明度像素就保留（多盖的透明处不显示）；
    # 旧判定要求重心和三条边中点都在不透明处，细长部分会被删掉
    keep = []
    for t in tri.simplices:
        a, b, c = pts[t]
        if all(inside(q) for q in ((a + b + c) / 3, (a + b) / 2, (b + c) / 2, (a + c) / 2)):
            keep.append(t)
            continue
        q = np.round(pts[t]).astype(np.int32)
        x0, y0 = max(q[:, 0].min() - 1, 0), max(q[:, 1].min() - 1, 0)
        x1, y1 = min(q[:, 0].max() + 2, w), min(q[:, 1].max() + 2, h)
        if x1 <= x0 or y1 <= y0:
            continue
        tm = np.zeros((y1 - y0, x1 - x0), np.uint8)
        cv2.fillConvexPoly(tm, q - [x0, y0], 1)
        if (tm & (mo[y0:y1, x0:x1] > 0)).any():
            keep.append(t)
    keep = np.array(keep)
    used = np.unique(keep)
    remap = -np.ones(len(pts), int)
    # 保持轮廓点在前（hull）
    order = [i for i in range(hull_n) if i in set(used)] + [i for i in used if i >= hull_n]
    remap[order] = np.arange(len(order))
    return pts[order], remap[keep], sum(1 for i in range(hull_n) if i in set(used))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("layers_dir")
    ap.add_argument("rig_dir")
    ap.add_argument("--name", default="kurumi_front")
    ap.add_argument("--ryza", action="store_true",
                    help="按 ryza-ai-revive 站姿模型的尺度输出：人物高缩放到 3658、head 骨骼放在 y=763、视线比例按 app 的 aim 量程（约 300）标定")
    ap.add_argument("--scale", type=float, default=None)
    ap.add_argument("--head-y", type=float, default=None)
    ap.add_argument("--aim-ref", type=float, default=None, help="aim 控制骨骼「看到最边上」时的位移（本工具演示 110，ryza app 约 300）")
    ap.add_argument("--back-gestures", default="behind", help="画在身体后面的手势（逗号分隔）")
    a = ap.parse_args()
    meta = json.load(open(os.path.join(a.layers_dir, "layers.json")))
    L = meta["layers"]
    kp, face = meta["kp"], meta["face"]
    face_w = meta["face_w"]
    RES = meta["size"][0] / 832.0
    # ryza 站姿 0001_99 实测（spine-core）：总高 3812、head 骨骼 y=763；本角色高 = 腿层底 − 头顶
    # 人物像素高（腿层底 − 前发顶）→ ryza 尺度：目标高 3658 单位（ryza 站姿实测 3812，含靴子与发饰）
    _lb, _hb = L["legs"]["bbox"], L["hair_front"]["bbox"]
    char_h = (_lb[1] + _lb[3]) - _hb[1]
    SC = a.scale if a.scale is not None else (3658.0 / char_h if a.ryza else 1.0)
    aim_ref = a.aim_ref if a.aim_ref is not None else (300.0 if a.ryza else 110.0)
    y0 = 0.0
    if a.ryza or a.head_y is not None:
        legs_bb = L["legs"]["bbox"]
        ground = legs_bb[1] + legs_bb[3]
        y0 = (a.head_y if a.head_y is not None else 763.0) - (ground - face[8][1]) * SC
    R = Rig(meta, a.layers_dir, SC, y0)
    PX = SC                    # 动画里以像素写的位移 × PX
    AIMS = aim_ref / 110.0    # 动画里以「演示 aim 单位」写的视线位移 × AIMS
    back_gestures = set(x for x in a.back_gestures.split(",") if x)

    def center(name):
        x, y, w, h = L[name]["bbox"]
        return (x + w / 2, y + h / 2)

    def lerp(p, q, t):
        return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)

    nose = face[30]
    hip = lerp(kp[8], kp[11], 0.5)
    neck = kp[1]
    eye_y = (center("eyewhite_R")[1] + center("eyewhite_L")[1]) / 2

    # ---------------- 骨骼 ----------------
    R.bone("root", None, world=(0.0, 0.0))
    for c in ("aim_head", "aim_eye", "aim_body"):  # 控制骨骼：静止 (0,0)，由代码 / 动画平移
        R.bone(c, "root", world=(0.0, 0.0))
    R.bone("hip", "root", hip)
    R.bone("waist", "hip", lerp(hip, neck, 0.33))
    R.bone("chest", "waist", lerp(hip, neck, 0.72))
    R.bone("neck", "chest", neck)
    R.bone("head", "neck", face[8], length=face_w * 0.5)  # 下巴处为头的转轴
    # ---- 头部球面形变格子（视线转头）----
    # 头部范围铺 NX×NY 根格子骨骼，每根按它在头部椭球面上的深度 z 跟随 aim_head（z=1 脸中间动最多，轮廓 z≈0 不动）：
    # 球体转小角度 θ 时表面点的横向位移 ≈ R·cosφ·θ = z·Rθ，所以「位移 ∝ 深度」就是球面转动的一阶近似——
    # 转向的一侧被压窄、另一侧拉开，五官不会整块滑出脸。脸、前发、眼白 / 睫毛等都是蒙皮网格，按双线性权重挂在格子上。
    # 2026-10-09 之前五官是按固定比例整块平移（只有脸皮有很弱的两骨权重），用户指出「没做网格形变、眼睛快出脸了」。
    NX, NY = 7, 7
    hbx = [L[n]["bbox"] for n in ("hair_front", "face")]
    lx0, lx1 = min(q[0] for q in hbx), max(q[0] + q[2] for q in hbx)
    ly0, ly1 = min(q[1] for q in hbx), max(q[1] + q[3] for q in hbx)
    LX = np.linspace(lx0 - 0.03 * (lx1 - lx0), lx1 + 0.03 * (lx1 - lx0), NX)
    LY = np.linspace(ly0 - 0.03 * (ly1 - ly0), ly1 + 0.03 * (ly1 - ly0), NY)
    head_c = (nose[0], eye_y + 0.1 * face_w)
    head_rx = 0.5 * (lx1 - lx0)
    head_ry = 1.05 * max(face[8][1] - head_c[1], head_c[1] - ly0)

    def depth(p):
        u, v = (p[0] - head_c[0]) / head_rx, (p[1] - head_c[1]) / head_ry
        return float(np.sqrt(max(0.0, 1.0 - u * u - v * v)))

    for j, yy in enumerate(LY):
        for i, xx in enumerate(LX):
            R.bone(f"hl_{i}_{j}", "head", (float(xx), float(yy)))

    def lat_w(p):
        """原图像素坐标 → 格子骨骼的双线性权重。"""
        fx = float(np.interp(p[0], LX, np.arange(NX)))
        fy = float(np.interp(p[1], LY, np.arange(NY)))
        i0, j0 = min(int(fx), NX - 2), min(int(fy), NY - 2)
        tx, ty = fx - i0, fy - j0
        return {f"hl_{i0}_{j0}": (1 - tx) * (1 - ty), f"hl_{i0 + 1}_{j0}": tx * (1 - ty),
                f"hl_{i0}_{j0 + 1}": (1 - tx) * ty, f"hl_{i0 + 1}_{j0 + 1}": tx * ty}

    R.bone("f_face", "head", nose)
    R.bone("f_eye_R", "head", center("eyewhite_R"))
    R.bone("f_eye_L", "head", center("eyewhite_L"))
    R.bone("iris_R", "f_eye_R", center("iris_R"))
    R.bone("iris_L", "f_eye_L", center("iris_L"))
    R.bone("f_nose", "head", center("nose") if "nose" in L else nose)
    R.bone("f_mouth", "head", center("mouth_smile"))
    R.bone("f_bangs", "head", (nose[0], eye_y - 0.3 * face_w))
    R.bone("f_hairside", "head", (nose[0], eye_y))
    R.bone("f_hairback", "head", (nose[0], eye_y))
    hb = L["hair_front"]["bbox"]
    bang_tip = (nose[0], eye_y + 0.05 * face_w)
    R.bone_toward("bang_tip", "f_bangs", (nose[0], eye_y - 0.3 * face_w), bang_tip)
    tips = {}
    for side, fx in (("R", 0.12), ("L", 0.88)):
        top = (hb[0] + hb[2] * fx, eye_y)
        bot = (hb[0] + hb[2] * fx, hb[1] + hb[3] * 0.92)
        tips[side] = (top, bot)
        R.bone_toward(f"hair_tip_{side}", "f_hairside", top, bot)
        bb = L["hair_back"]["bbox"]
        R.bone_toward(f"back_tip_{side}", "f_hairback", (bb[0] + bb[2] * fx, eye_y), (bb[0] + bb[2] * fx, bb[1] + bb[3]))
    # 手臂（DWPose：2/3/4 右肩肘腕 = 画面左；5/6/7 左）。前臂、手不继承缩放（noScale）：
    # 手势里用上臂 / 前臂的 scaleX 表现透视缩短，子骨骼只跟位置、不被拉扁
    arm_pts = {}
    G = meta.get("gestures", {})
    for side in ("R", "L"):
        rest_chain = None
        for g in G.values():
            rest_chain = g["rest_chains"][side]
            break
        if rest_chain is None and meta.get("arm_chain") == "layer":
            # 关节从手臂层自己取（seethrough-to-layers.py 标的）：袖子顶端 → 最远点（指尖）的中轴，
            # 肘、腕按上臂 : 前臂 : 手 ≈ 30 : 25 : 19 放在 40%、74%。DWPose 在深色袖子 + 深色长发上会把肘、腕标到头发上
            # （2026-10-09 deepseek-chan 实测，手部点也一样），只要层是完整的手臂就不依赖它
            al = np.array(Image.open(os.path.join(a.layers_dir, f"arm_{side}.png")))[..., 3]
            ax, ay = L[f"arm_{side}"]["bbox"][:2]
            ys_, xs_ = np.nonzero(al > 127)
            top = (float(xs_[np.argmin(ys_)] + ax), float(ys_.min() + ay))
            rest_chain = [list(q) for q in tail_path(al, ax, ay, top, 3, fracs=[0.0, 0.40, 0.74, 1.0])]
        if rest_chain is None:
            s_, e_, w_ = (kp[2], kp[3], kp[4]) if side == "R" else (kp[5], kp[6], kp[7])
            rest_chain = [s_[:2], e_[:2], w_[:2], (w_[0] + (w_[0] - e_[0]) * 0.45, w_[1] + (w_[1] - e_[1]) * 0.45)]
        arm_pts[side] = rest_chain
        S_, E_, W_, T_ = rest_chain
        R.bone_toward(f"arm_{side}", "chest", S_, E_)
        R.bone_toward(f"fore_{side}", f"arm_{side}", E_, W_)
        R.bone_toward(f"hand_{side}", f"fore_{side}", W_, T_)
        for b in (f"fore_{side}", f"hand_{side}"):
            R.bones[R.idx[b]]["inherit"] = "noScale"
    # 每个手势自己一套手臂骨骼（ga_/gf_/gh_<手势>_<侧>），初始姿势就是该手势的姿势。
    # 照 ryza：它的每种手臂图都挂在独立骨骼上（arm_R_A / arm_R_B …），换手势只换图、骨骼几乎不动。
    # 之前共用 arm_* 骨骼，app 在两段动作之间按 0.6s 插值骨骼角度 → 直手臂被整根转到举起，像飞出去（2026-10-09 用户反馈）。
    for gname, g in G.items():
        for side in g["sides"]:
            S_, E_, W_, T_ = g["chains"][side]
            R.bone_toward(f"ga_{gname}_{side}", "chest", S_, E_)
            R.bone_toward(f"gf_{gname}_{side}", f"ga_{gname}_{side}", E_, W_)
            R.bone_toward(f"gh_{gname}_{side}", f"gf_{gname}_{side}", W_, T_)

    def ang(p, q):
        a_, b_ = R.S(p), R.S(q)
        return math.degrees(math.atan2(b_[1] - a_[1], b_[0] - a_[0])), math.hypot(b_[0] - a_[0], b_[1] - a_[1])

    def wrap(d):
        return (d + 180) % 360 - 180

    def gesture_pose(side, chain):
        """手势姿势相对静止姿势的骨骼增量（局部旋转差、scaleX、肩位移），以及该姿势下三根骨骼的世界变换（用来绑定手势图）。"""
        r = arm_pts[side]
        a0, la0 = ang(r[0], r[1]); f0, lf0 = ang(r[1], r[2]); h0, _ = ang(r[2], r[3])
        a1, la1 = ang(chain[0], chain[1]); f1, lf1 = ang(chain[1], chain[2]); h1, _ = ang(chain[2], chain[3])
        sx0, sy0 = R.S(r[0]); sx1, sy1 = R.S(chain[0])
        d = {"arm_t": (sx1 - sx0, sy1 - sy0), "arm_r": wrap(a1 - a0), "arm_s": la1 / max(la0, 1e-6),
             "fore_r": wrap((f1 - a1) - (f0 - a0)), "fore_s": lf1 / max(lf0, 1e-6), "hand_r": wrap((h1 - f1) - (h0 - f0))}
        # 该姿势下的世界变换（与 Spine noScale 继承一致：位置走父骨骼完整矩阵，旋转只累加）
        e1 = R.S(chain[1]); w1 = R.S(chain[2])
        world = {f"arm_{side}": (sx1, sy1, a1, d["arm_s"]), f"fore_{side}": (e1[0], e1[1], f1, d["fore_s"]),
                 f"hand_{side}": (w1[0], w1[1], h1, 1.0)}
        return d, world

    # 裙摆：腰带两侧 / 中间指向裙摆
    bodyb = L["body"]["bbox"]
    belt_y = lerp(hip, neck, 0.33)[1]
    hem_y = bodyb[1] + bodyb[3]
    skirt_x = {"R": hip[0] - 0.3 * bodyb[2], "C": hip[0], "L": hip[0] + 0.3 * bodyb[2]}
    for k, x in skirt_x.items():
        R.bone_toward(f"skirt_{k}", "waist", (x, belt_y), (x + (x - hip[0]) * 0.25, hem_y))
    # 尾巴（See-through 的 tail 层）：沿中轴分 TAIL_N 节，挂在胯上，每节加物理
    TAIL_N = 4
    tail_pts = None
    if "tail" in L:
        tx, ty = L["tail"]["bbox"][:2]
        tail_pts = tail_path(np.array(Image.open(os.path.join(a.layers_dir, "tail.png")))[..., 3], tx, ty, hip, TAIL_N)
        for k in range(TAIL_N):
            R.bone_toward(f"tail_{k}", "hip" if k == 0 else f"tail_{k - 1}", tail_pts[k], tail_pts[k + 1])

    # ---------------- 附件 ----------------
    os.makedirs(os.path.join(a.rig_dir, "images"), exist_ok=True)
    skin, slots = {}, []

    def img(name):
        shutil.copy(os.path.join(a.layers_dir, f"{name}.png"), os.path.join(a.rig_dir, "images", f"{name}.png"))
        return np.array(Image.open(os.path.join(a.layers_dir, f"{name}.png")))

    def region(slot, name, bone):
        im = img(name)
        x, y, w, h = L[name]["bbox"]
        lx, ly = R.to_local(bone, *R.S((x + w / 2, y + h / 2)))
        rot = -R.world[bone][2]
        skin.setdefault(slot, {})[name] = {"x": round(lx, 2), "y": round(ly, 2), "rotation": round(rot, 2),
                                           "scaleX": round(SC, 4), "scaleY": round(SC, 4),
                                           "width": im.shape[1], "height": im.shape[0]}

    def to_local_pose(bname, wx, wy, pose):
        if not pose or bname not in pose:
            return R.to_local(bname, wx, wy)
        bx, by, br, bs = pose[bname]
        c, s_ = math.cos(math.radians(-br)), math.sin(math.radians(-br))
        dx, dy = wx - bx, wy - by
        return (c * dx - s_ * dy) / bs, s_ * dx + c * dy

    def mesh(slot, name, weight_fn, spacing, pose=None):
        """pose：{骨骼: (世界 x, y, 旋转, scaleX)}，给手势图用——按手势姿势绑定，骨骼摆到该姿势时图正好落回原位。"""
        im = img(name)
        x0, y0, w, h = L[name]["bbox"]
        pts, tris, hull = build_mesh(im[..., 3], spacing * RES)  # 间距按 832 宽时定，换分辨率等比放大
        verts, nb = [], []
        for p in pts:
            px = (x0 + p[0], y0 + p[1])
            ws = {k: v for k, v in weight_fn(px).items() if v > 0.01}
            ws = dict(sorted(ws.items(), key=lambda kv: -kv[1])[:4])
            tot = sum(ws.values())
            verts.append(len(ws))
            for bname, wt in ws.items():
                lx, ly = to_local_pose(bname, *R.S(px), pose)
                verts += [R.idx[bname], round(lx, 2), round(ly, 2), round(wt / tot, 4)]
            nb.append(len(ws))
        uvs = []
        for p in pts:
            uvs += [round(p[0] / w, 5), round(p[1] / h, 5)]
        skin.setdefault(slot, {})[name] = {"type": "mesh", "uvs": uvs, "triangles": tris.reshape(-1).tolist(),
                                           "vertices": verts, "hull": int(hull), "width": w, "height": h}
        return len(pts), len(tris)

    def grid_mesh(slot, name, weight_fn, n=4):
        """小部件（眼白、睫毛、嘴…）：整张图铺 n×n 网格，按权重函数蒙皮，能随格子一起形变。"""
        im = img(name)
        x0, y0, w, h = L[name]["bbox"]
        pts = [(w * i / n, h * j / n) for j in range(n + 1) for i in range(n + 1)]
        tris = []
        for j in range(n):
            for i in range(n):
                q = j * (n + 1) + i
                tris += [q, q + 1, q + n + 1, q + 1, q + n + 2, q + n + 1]
        verts, uvs = [], []
        for px_, py_ in pts:
            pw = (x0 + px_, y0 + py_)
            ws = {k: v for k, v in weight_fn(pw).items() if v > 0.001}
            tot = sum(ws.values())
            verts.append(len(ws))
            for bname, wt in ws.items():
                lx, ly = R.to_local(bname, *R.S(pw))
                verts += [R.idx[bname], round(lx, 2), round(ly, 2), round(wt / tot, 4)]
            uvs += [round(px_ / w, 5), round(py_ / h, 5)]
        hull = list(range(0, n + 1)) + [j * (n + 1) + n for j in range(1, n + 1)]
        skin.setdefault(slot, {})[name] = {"type": "mesh", "uvs": uvs, "triangles": tris, "vertices": verts,
                                           "hull": 4 * n, "width": int(im.shape[1]), "height": int(im.shape[0])}

    stats = {}
    # 权重函数（输入：原图像素坐标）
    def w_face(p):
        return lat_w(p)

    def w_hair_front(p):
        # 格子（转头形变）为主；刘海下缘混入 bang_tip、两侧发梢混入 hair_tip_*（物理）
        inside = 1 - smooth((abs(p[0] - nose[0]) - 0.15 * face_w) / (0.4 * face_w))
        bang = inside * (1 - smooth((p[1] - (eye_y - 0.05 * face_w)) / (0.1 * face_w)))
        side = "R" if p[0] < nose[0] else "L"
        (tx, ty), (bx, by) = tips[side]
        t = float(smooth((p[1] - ty) / max(by - ty, 1))) * (1 - bang)
        tb = float(smooth((p[1] - (eye_y - 0.3 * face_w)) / (0.25 * face_w))) * bang * 0.6
        ws = {k: v * (1 - t - tb) for k, v in lat_w(p).items()}
        ws["bang_tip"] = tb
        ws[f"hair_tip_{side}"] = t
        return ws

    def w_hair_back(p):
        side = "R" if p[0] < nose[0] else "L"
        t = float(smooth((p[1] - eye_y) / (0.6 * face_w)))
        return {"f_hairback": 1 - t, f"back_tip_{side}": t}

    def w_body(p):
        y = p[1]
        ws = {}
        neck_w = float(1 - smooth((y - (neck[1] - 0.05 * face_w)) / (0.15 * face_w)))
        ws["neck"] = neck_w
        chest_w = float(1 - smooth((y - (belt_y - 0.15 * face_w)) / (0.3 * face_w))) * (1 - neck_w)
        ws["chest"] = chest_w
        rest = 1 - neck_w - chest_w
        sk = float(smooth((y - belt_y) / max(hem_y - belt_y, 1))) ** 1.2
        ws["waist"] = rest * (1 - sk)
        # 裙摆按 x 分给三根裙骨
        xs = np.array(list(skirt_x.values()))
        g = np.exp(-((p[0] - xs) / (0.22 * bodyb[2])) ** 2)
        g /= g.sum()
        for (k, _), gg in zip(skirt_x.items(), g):
            ws[f"skirt_{k}"] = rest * sk * float(gg)
        return ws

    def w_legs(p):
        knee_y = (kp[9][1] + kp[12][1]) / 2
        t = float(smooth((p[1] - hip[1]) / max(knee_y - hip[1], 1)))
        return {"hip": 1 - t, "root": t}

    def chain_weights(names, P, anchor=None, anchor_k=0.35):
        """手臂链权重。anchor：肩头一圈混入的身体骨骼——沿上臂方向离肩关节 0 → anchor_k × 上臂长，
        anchor 权重 1 → 0。袖山是缝在衣身上的：手臂转动时袖子靠肩的部分留在原处、被拉伸，
        不整块转出去（2026-10-09 用户指出：蹦的时候袖子转开，上衣肩上那截衣服露成方块）。"""
        P = [np.array(q[:2], float) for q in P]
        segs = list(zip(P[:-1], P[1:]))
        lens = [np.linalg.norm(b - a) for a, b in segs]
        cum = np.concatenate([[0], np.cumsum(lens)])
        if anchor:
            base = chain_core(names, P, segs, lens, cum)
            d1 = (P[1] - P[0]) / max(lens[0], 1e-6)

            def fn_a(p):
                s = float(np.dot(np.array(p, float) - P[0], d1))
                wa = float(1 - smooth(s / (anchor_k * lens[0])))
                ws = {k: v * (1 - wa) for k, v in base(p).items()}
                ws[anchor] = wa
                return ws
            return fn_a
        return chain_core(names, P, segs, lens, cum)

    def chain_core(names, P, segs, lens, cum):
        def fn(p):
            p = np.array(p, float)
            best, u = 1e9, 0
            for i, (a_, b_) in enumerate(segs):
                d = b_ - a_
                t = np.clip(np.dot(p - a_, d) / max(np.dot(d, d), 1e-6), 0, 1)
                dist = np.linalg.norm(a_ + d * t - p)
                if dist < best - 1e-6:
                    best, u = dist, cum[i] + t * lens[i]
            band = 0.08 * cum[-1]
            w1 = 1 - smooth((u - cum[1] + band) / (2 * band))
            w3 = smooth((u - cum[2] + band) / (2 * band))
            return {names[0]: float(w1), names[1]: float(1 - w1 - w3), names[2]: float(w3)}
        return fn

    # 绘制顺序（后 → 前）与插槽
    def slot(name, bone, att=None, color=None):
        s = {"name": name, "bone": bone}
        if att:
            s["attachment"] = att
        if color:
            s["color"] = color
        slots.append(s)

    slot("hair_back", "f_hairback", "hair_back")
    stats["hair_back"] = mesh("hair_back", "hair_back", w_hair_back, 14)
    if tail_pts:  # 尾巴画在后发之后、腿和身体之前
        segs_t = [(np.array(tail_pts[k]), np.array(tail_pts[k + 1])) for k in range(TAIL_N)]

        def w_tail(p):
            p = np.array(p, float)
            best, kb, tb = 1e9, 0, 0.0
            for k, (a_, b_) in enumerate(segs_t):
                d = b_ - a_
                t = float(np.clip(np.dot(p - a_, d) / max(np.dot(d, d), 1e-6), 0, 1))
                dist = np.linalg.norm(a_ + d * t - p)
                if dist < best:
                    best, kb, tb = dist, k, t
            # 节与节之间在各自 30% 范围内线性过渡，第一节根部混入 hip（接在身上）
            ws = {f"tail_{kb}": 1.0}
            if tb > 0.7 and kb + 1 < TAIL_N:
                f_ = (tb - 0.7) / 0.6
                ws = {f"tail_{kb}": 1 - f_, f"tail_{kb + 1}": f_}
            elif tb < 0.3:
                f_ = (0.3 - tb) / 0.6
                ws = {f"tail_{kb}": 1 - f_, ("hip" if kb == 0 else f"tail_{kb - 1}"): f_}
            return ws
        slot("tail", "hip", "tail")
        stats["tail"] = mesh("tail", "tail", w_tail, 12)
    slot("legs", "hip", "legs")
    stats["legs"] = mesh("legs", "legs", w_legs, 22)
    # 手臂在身体后面（See-through 层按深度判的，见 seethrough-to-layers.py）：袖子内侧被衣身挡住，手臂插槽放在 body 前
    arms_behind = bool(meta.get("arms_behind_body"))

    def arm_slots():
        for side in ("R", "L"):
            slot(f"arm_{side}", f"arm_{side}", f"arm_{side}")
            stats[f"arm_{side}"] = mesh(f"arm_{side}", f"arm_{side}", chain_weights([f"arm_{side}", f"fore_{side}", f"hand_{side}"], arm_pts[side], anchor="chest"), 14)
    if arms_behind:
        arm_slots()
    slot("body", "chest", "body")
    stats["body"] = mesh("body", "body", w_body, 16)
    if "ears" in L:  # 耳朵单独一层、不随闭眼换脸（见 seethrough-to-layers.py）
        slot("ears", "head", "ears")
        stats["ears"] = mesh("ears", "ears", w_face, 12)
    slot("face", "head", "face")
    stats["face"] = mesh("face", "face", w_face, 12)
    has_face_closed = "face_closed" in L  # 闭眼 / 笑眼时换的脸（见 seethrough-to-layers.py）
    if has_face_closed:
        stats["face_closed"] = mesh("face", "face_closed", w_face, 12)

    def face_keys(an, seq):
        if has_face_closed:
            keys_att(an, "face", seq)
    if "blush_base" in L:  # See-through 层（seethrough-to-layers.py）没有腮红 / 闭眼 / 张嘴 / 手势，缺的就跳过
        slot("blush", "f_face", "blush_base")
        grid_mesh("blush", "blush_base", lat_w)
        if "blush" in L:
            grid_mesh("blush", "blush", lat_w)
    if "nose" in L:
        slot("nose", "f_nose", "nose")
        grid_mesh("nose", "nose", lambda p: {"f_nose": 1.0}, 1)
    for side in ("R", "L"):
        slot(f"eyewhite_{side}", f"f_eye_{side}", f"eyewhite_{side}")
        grid_mesh(f"eyewhite_{side}", f"eyewhite_{side}", lat_w)
        slot(f"clip_{side}", f"f_eye_{side}", f"clip_{side}")
        hull = L[f"eyewhite_{side}"]["hull"]
        v = []
        for q in hull:  # 裁剪多边形同样挂格子，跟眼白一起形变
            ws = lat_w(q)
            v.append(len(ws))
            for bname, wt in ws.items():
                lx, ly = R.to_local(bname, *R.S(q))
                v += [R.idx[bname], round(lx, 2), round(ly, 2), round(wt, 4)]
        skin.setdefault(f"clip_{side}", {})[f"clip_{side}"] = {"type": "clipping", "end": f"iris_{side}",
                                                               "vertexCount": len(hull), "vertices": v}
        slot(f"iris_{side}", f"iris_{side}", f"iris_{side}")
        grid_mesh(f"iris_{side}", f"iris_{side}", lambda p, sd=side: {f"iris_{sd}": 1.0}, 1)
        slot(f"lash_{side}", f"f_eye_{side}", f"lash_{side}")
        for n in (f"lash_{side}", f"eye_closed_{side}", f"eye_happy_{side}"):
            if n in L:
                grid_mesh(f"lash_{side}", n, lat_w)
    for side in ("R", "L"):  # 眉（See-through 补出了被刘海挡住的眉）：画在脸上、前发下面，跟格子形变
        if f"brow_{side}" in L:
            slot(f"brow_{side}", "head", f"brow_{side}")
            grid_mesh(f"brow_{side}", f"brow_{side}", lat_w)
    slot("mouth", "f_mouth", "mouth_smile")
    for n in ("mouth_smile", "mouth_ah", "mouth_happy"):
        if n in L:
            grid_mesh("mouth", n, lambda p: {"f_mouth": 1.0}, 1)
    # 手势图：背在身后的放身体后面，其余在最前（手可以挡住脸和头发）
    gposes = {}
    for gname, g in G.items():
        for side in g["sides"]:
            gposes[(gname, side)] = gesture_pose(side, g["chains"][side])
    if not arms_behind:
        arm_slots()

    def headwear_slot():  # 头饰（seethrough-to-layers.py --headwear 单独出的层）跟头部格子形变
        if "headwear" in L:
            slot("headwear", "head", "headwear")
            stats["headwear"] = mesh("headwear", "headwear", w_face, 12)
    hw_front = bool(meta.get("headwear_front_of_hair"))
    if not hw_front:
        headwear_slot()
    slot("hair_front", "f_hairside", "hair_front")
    stats["hair_front"] = mesh("hair_front", "hair_front", w_hair_front, 12)
    if hw_front:
        headwear_slot()
    for side in ("R", "L"):
        slot(f"garm_{side}", f"arm_{side}")
    for (gname, side), (d, world) in gposes.items():
        sl = f"garm_{side}_back" if gname in back_gestures else f"garm_{side}"
        if gname in back_gestures and not any(x["name"] == sl for x in slots):
            # 身体后面那层插在 body 之前
            bi = next(i for i, x in enumerate(slots) if x["name"] == "body")
            slots.insert(bi, {"name": sl, "bone": f"arm_{side}"})
        nm = f"g_{gname}_{side}"
        gb = [f"ga_{gname}_{side}", f"gf_{gname}_{side}", f"gh_{gname}_{side}"]
        stats[nm] = mesh(sl, nm, chain_weights(gb, G[gname]["chains"][side]), 14)

    # 点击判定框（app 按 projectConfig.hitPartNames 认 BB_* 插槽）
    def bbox_att(slot_name, bone, names, pad=0.0):
        xs, ys = [], []
        for n in names:
            x, y, w, h = L[n]["bbox"]
            xs += [x - pad, x + w + pad]; ys += [y - pad, y + h + pad]
        x0, x1, y0_, y1 = min(xs), max(xs), min(ys), max(ys)
        v = []
        for q in ((x0, y0_), (x1, y0_), (x1, y1), (x0, y1)):
            lx, ly = R.to_local(bone, *R.S(q))
            v += [round(lx, 2), round(ly, 2)]
        slot(slot_name, bone, slot_name)
        skin.setdefault(slot_name, {})[slot_name] = {"type": "boundingbox", "vertexCount": 4, "vertices": v}
    bbox_att("BB_head", "head", ["face", "hair_front"])
    bbox_att("BB_body", "chest", ["body"])
    bbox_att("BB_arm_R", f"arm_R", ["arm_R"])
    bbox_att("BB_arm_L", f"arm_L", ["arm_L"])

    # ---------------- 约束 ----------------
    def tc(name, target, bone, mx, my=None, order=0):
        c = {"name": name, "order": order, "bones": [bone], "target": target, "local": True, "relative": True,
             "mixRotate": 0, "mixX": mx, "mixScaleX": 0, "mixShearY": 0}
        if my is not None:
            c["mixY"] = my
        return c

    # 深度 z = 1 的点在 aim = aim_ref 时移 LAT_K × 脸宽（ryza 实测指针跟随最大时眼睛约移 17% 耳间宽；
    # 这里取 13%，眼睛（z≈0.85）约 11%，配合格子形变不会出脸）
    LAT_K = 0.13
    MK = SC / AIMS
    EYE_REF = 1.6
    LAT_A = LAT_K * face_w * SC / aim_ref
    transform = []
    for j, yy in enumerate(LY):
        for i, xx in enumerate(LX):
            z = depth((xx, yy))
            if z > 0:
                transform.append(tc(f"aim_hl_{i}_{j}", "aim_head", f"hl_{i}_{j}", round(LAT_A * z, 5), round(0.8 * LAT_A * z, 5)))
    feat = {"f_eye_R": center("eyewhite_R"), "f_eye_L": center("eyewhite_L"), "f_mouth": center("mouth_smile"),
            "f_nose": center("nose") if "nose" in L else nose, "f_bangs": (nose[0], eye_y - 0.3 * face_w),
            "f_hairside": (nose[0], eye_y)}
    for bn, pos in feat.items():
        z = depth(pos) + (0.25 if bn == "f_nose" else 0.0)  # 鼻子比脸面再凸出一点
        transform.append(tc(f"aim_head_{bn}", "aim_head", bn, round(LAT_A * z, 5), round(0.8 * LAT_A * z, 5)))
    transform.append(tc("aim_head_f_hairback", "aim_head", "f_hairback", round(-0.26 * LAT_A, 5), round(-0.2 * LAT_A, 5)))
    transform += [tc(f"aim_eye_{s}", "aim_eye", f"iris_{s}", round(0.045 * MK / EYE_REF, 4), round(0.035 * MK / EYE_REF, 4), order=10 + i) for i, s in enumerate("RL")]
    transform += [tc("aim_body_chest", "aim_body", "chest", round(0.08 * MK, 4), round(0.04 * MK, 4), order=12),
                  tc("aim_body_neck", "aim_body", "neck", round(0.06 * MK, 4), round(0.03 * MK, 4), order=13),
                  tc("aim_body_hip", "aim_body", "hip", round(-0.03 * MK, 4), 0, order=14)]
    physics = []
    o = 20
    # 参数参照 ryza 的物理约束（inertia 0.5、strength 40–100、damping 0.75–0.85、x/y 0.6）；
    # 刘海骨骼短，旋转很敏感（实测 18px 长、rotate 1 时 hop 中来回转 ±180°），所以只给少量旋转、加大刚度
    for b, prm in ([("bang_tip", dict(rotate=0.3, x=0.4, y=0.4, inertia=0.5, strength=140, damping=0.9)),
                   ("hair_tip_R", dict(rotate=1, x=0.6, y=0.6, inertia=0.5, strength=60, damping=0.85)),
                   ("hair_tip_L", dict(rotate=1, x=0.6, y=0.6, inertia=0.5, strength=60, damping=0.85)),
                   ("back_tip_R", dict(rotate=1, x=0.6, y=0.6, inertia=0.5, strength=50, damping=0.85)),
                   ("back_tip_L", dict(rotate=1, x=0.6, y=0.6, inertia=0.5, strength=50, damping=0.85)),
                   ("skirt_R", dict(rotate=0.7, x=0.6, y=0.6, inertia=0.6, strength=70, damping=0.8)),
                   ("skirt_C", dict(rotate=0.5, x=0.6, y=0.6, inertia=0.6, strength=70, damping=0.8)),
                   ("skirt_L", dict(rotate=0.7, x=0.6, y=0.6, inertia=0.6, strength=70, damping=0.8))]
                  + ([(f"tail_{k}", dict(rotate=1, x=0.3, y=0.3, inertia=0.5, strength=60 - 10 * k, damping=0.85))
                      for k in range(TAIL_N)] if tail_pts else [])):
        physics.append({"name": f"phys_{b}", "order": o, "bone": b, "limit": 5000, "fps": 60, "mass": 1, **prm})
        o += 1

    # ---------------- 动画 ----------------
    # 名字沿用 ryza-ai-revive 的约定，app 按名字找（见 reports/front-rig-ryza-2026-10-09.md §9）：
    #   motion_A_001_idle 待机；facial_eye_001_idle 闭眼 / 002 睁眼 / 003 笑眼；facial_mouth_001 微笑 / 002 啊 / 003 大笑，
    #   facial_mouth_002_scrub_02 口型（app 按音量拖 trackTime）；facial_add_blush_on/off；
    #   motion_touch_A_001_active 被点；motion_oneshot_D_001 点头 / 003 摇头 / 009 歪头 / 010 蹦；
    #   手势 motion_add_{F 左臂 | G 右臂}_{nnn}_{in_up | active | out_up}，000 = 静止手臂
    anims = {}

    def sample(dur, fn):
        n = max(1, int(round(dur * FPS)))
        ts = [i / FPS for i in range(n + 1)]
        return ts, [fn((t / dur) if dur else 0, t) for t in ts]

    def keys_bone(an, bone, prop, dur, fn, scale_xy=1.0):
        ts, vs = sample(dur, fn) if dur else ([0.0], [fn(0, 0)])
        tl = anims.setdefault(an, {}).setdefault("bones", {}).setdefault(bone, {}).setdefault(prop, [])
        for t, v in zip(ts, vs):
            kf = {"time": round(t, 4)}
            if prop == "rotate":
                kf["value"] = round(float(v), 3)
            elif prop == "translate":
                kf["x"], kf["y"] = round(float(v[0]) * scale_xy, 3), round(float(v[1]) * scale_xy, 3)
            else:
                kf["x"], kf["y"] = round(float(v[0]), 4), round(float(v[1]), 4)
            tl.append(kf)

    def keys_att(an, slot_name, seq):
        anims.setdefault(an, {}).setdefault("slots", {}).setdefault(slot_name, {})["attachment"] = \
            [{"time": round(t, 4), "name": n} for t, n in seq]

    def keys_rgba(an, slot_name, seq):
        anims.setdefault(an, {}).setdefault("slots", {}).setdefault(slot_name, {})["rgba"] = \
            [{"time": round(t, 4), "color": c} for t, c in seq]

    def bump(u, a_, b_):
        return math.sin(math.pi * np.clip((u - a_) / (b_ - a_), 0, 1))

    def body(an, bone, dur, fn):  # 身体骨骼位移：像素 × PX
        keys_bone(an, bone, "translate", dur, fn, PX)

    def aim(an, bone, dur, fn):   # 视线控制骨骼：演示 aim 单位 × AIMS
        keys_bone(an, bone, "translate", dur, fn, AIMS)

    TAU = 2 * math.pi
    gslots = sorted({x["name"] for x in slots if x["name"].startswith("garm_")})

    def arms_rest(an):
        """把两只手臂的附件 / 透明度写回静止状态：手势轨道清空后由待机把它们恢复。"""
        for sd in "RL":
            keys_att(an, f"arm_{sd}", [(0, f"arm_{sd}")])
            keys_rgba(an, f"arm_{sd}", [(0, "ffffffff")])
        for gs in gslots:
            keys_att(an, gs, [(0, None)])
            keys_rgba(an, gs, [(0, "ffffffff")])

    # 待机：呼吸、重心、头微摆、手臂随呼吸
    IDLE = "motion_A_001_idle"
    keys_bone(IDLE, "chest", "scale", 4, lambda u, t: (1, 1 + 0.012 * math.sin(TAU * u * 2)))
    body(IDLE, "chest", 4, lambda u, t: (0, 1.2 * math.sin(TAU * u * 2)))
    body(IDLE, "hip", 4, lambda u, t: (3 * math.sin(TAU * u), 0))
    keys_bone(IDLE, "head", "rotate", 4, lambda u, t: 1.2 * math.sin(TAU * u + 0.8))
    for sd, sg in (("R", 1), ("L", -1)):
        keys_bone(IDLE, f"arm_{sd}", "rotate", 4, lambda u, t, sg=sg: sg * 1.2 * math.sin(TAU * u * 2 + 0.6))
        keys_bone(IDLE, f"fore_{sd}", "rotate", 4, lambda u, t, sg=sg: sg * 1.0 * math.sin(TAU * u * 2 + 1.0))
    arms_rest(IDLE)
    if tail_pts:  # 尾巴慢摆（节间相位差，物理再叠一层惯性）
        for k in range(TAIL_N):
            keys_bone(IDLE, f"tail_{k}", "rotate", 4, lambda u, t, k=k: (3 + 2 * k) * math.sin(TAU * u - 0.7 * k))
    # ryza 的 app 每帧在动画之后往 aim_* 的 x/y、roll 骨骼（头 / 颈 / 胸）的 rotation 上「加」视线偏移，
    # 依赖待机动画每帧把这些骨骼重新打帧归位；不打帧就会逐帧累加（实测 aim_head.x 几秒内到 −54908，人飞出画面）
    for bn in ("aim_head", "aim_eye", "aim_body"):
        keys_bone(IDLE, bn, "translate", 0, lambda u, t: (0, 0))
    for bn in ("neck", "chest"):
        keys_bone(IDLE, bn, "rotate", 0, lambda u, t: 0)
    # 视线环视（演示用；app 里视线由代码驱动 aim_*）
    aim("look_around", "aim_head", 4, lambda u, t: (110 * math.cos(TAU * u), 60 * math.sin(TAU * u)))
    aim("look_around", "aim_eye", 4, lambda u, t: (120 * math.cos(TAU * u - 0.4), 80 * math.sin(TAU * u - 0.4)))
    aim("look_around", "aim_body", 4, lambda u, t: (60 * math.cos(TAU * u - 0.6), 0))
    # 单次动作（态度）：点头 / 摇头 / 歪头 / 蹦
    NOD, SHAKE, TILT, HOP = "motion_oneshot_D_001_active", "motion_oneshot_D_003_active", "motion_oneshot_D_009_active", "motion_oneshot_D_010_active"
    aim(NOD, "aim_head", 1.2, lambda u, t: (0, -70 * bump(u, 0, 0.45) - 35 * bump(u, 0.45, 0.8)))
    aim(NOD, "aim_body", 1.2, lambda u, t: (0, -20 * math.sin(math.pi * u)))
    keys_bone(NOD, "head", "rotate", 1.2, lambda u, t: 2 * bump(u, 0, 0.45))
    aim(SHAKE, "aim_head", 1.3, lambda u, t: (95 * math.sin(TAU * u * 2) * bump(u, 0, 1), -10 * bump(u, 0, 1)))
    keys_bone(SHAKE, "head", "rotate", 1.3, lambda u, t: -2.5 * math.sin(TAU * u * 2) * bump(u, 0, 1))
    keys_bone(TILT, "head", "rotate", 1.6, lambda u, t: 9 * bump(u, 0, 1))
    aim(TILT, "aim_head", 1.6, lambda u, t: (50 * bump(u, 0, 1), 10 * bump(u, 0, 1)))
    keys_bone(TILT, "neck", "rotate", 1.6, lambda u, t: 2.5 * bump(u, 0, 1))
    body(HOP, "root", 1.0, lambda u, t: (0, 40 * bump(u, 0.15, 0.65)))
    body(HOP, "hip", 1.0, lambda u, t: (0, -8 * bump(u, 0, 0.15) - 10 * bump(u, 0.65, 0.85)))
    for sd, sg in (("R", -1), ("L", 1)):
        keys_bone(HOP, f"arm_{sd}", "rotate", 1.0, lambda u, t, sg=sg: sg * 14 * bump(u, 0.1, 0.8))
    # 被点：头后缩、身体后仰再回弹、闭眼张嘴
    TOUCH = "motion_touch_A_001_active"
    aim(TOUCH, "aim_head", 1.2, lambda u, t: (0, 45 * bump(u, 0, 0.55) - 12 * bump(u, 0.55, 0.9)))
    body(TOUCH, "hip", 1.2, lambda u, t: (0, 8 * bump(u, 0, 0.35)))
    keys_bone(TOUCH, "chest", "rotate", 1.2, lambda u, t: 3 * bump(u, 0, 0.5) - 1.5 * bump(u, 0.5, 0.85))
    keys_bone(TOUCH, "head", "rotate", 1.2, lambda u, t: -4 * bump(u, 0.05, 0.6))
    has_closed = all(f"eye_closed_{sd}" in L for sd in "RL")
    has_ah = "mouth_ah" in L
    if has_closed:
        face_keys(TOUCH, [(0, "face_closed"), (0.25, "face")])
    for sd in "RL":
        if has_closed:
            keys_att(TOUCH, f"lash_{sd}", [(0, f"eye_closed_{sd}"), (0.25, f"lash_{sd}")])
            keys_att(TOUCH, f"eyewhite_{sd}", [(0, None), (0.25, f"eyewhite_{sd}")])
            keys_att(TOUCH, f"iris_{sd}", [(0, None), (0.25, f"iris_{sd}")])
    if has_ah:
        keys_att(TOUCH, "mouth", [(0, "mouth_ah"), (0.9, "mouth_smile")])
    # 表情：眼 / 嘴 / 腮红各自一条，app 分轨道叠
    for sd in "RL":
        for an, lash, show in (("facial_eye_001_idle", f"eye_closed_{sd}", False), ("facial_eye_002_idle", f"lash_{sd}", True),
                               ("facial_eye_003_idle", f"eye_happy_{sd}", False)):
            if lash not in L:
                continue
            face_keys(an, [(0, "face" if show else "face_closed")])
            keys_att(an, f"lash_{sd}", [(0, lash)])
            keys_att(an, f"eyewhite_{sd}", [(0, f"eyewhite_{sd}" if show else None)])
            keys_att(an, f"iris_{sd}", [(0, f"iris_{sd}" if show else None)])
            keys_bone(an, f"f_eye_{sd}", "scale", 0, lambda u, t: (1, 1))
    for an, m in (("facial_mouth_001_idle", "mouth_smile"), ("facial_mouth_002_idle", "mouth_ah"), ("facial_mouth_003_idle", "mouth_happy")):
        if m not in L:
            continue
        keys_att(an, "mouth", [(0, m)])
        keys_bone(an, "f_mouth", "scale", 0, lambda u, t: (1, 1))
    # 口型：0 = 闭（微笑），之后「啊」按开口度从 0.35 张到 1
    LIP = "facial_mouth_002_scrub_02"
    if has_ah:
        keys_att(LIP, "mouth", [(0, "mouth_smile"), (0.15, "mouth_ah")])
        keys_bone(LIP, "f_mouth", "scale", 1.0, lambda u, t: (1, 1 if u < 0.15 else 0.35 + 0.65 * (u - 0.15) / 0.85))
    if "blush" in L:
        keys_att("facial_add_blush_on", "blush", [(0, "blush")])
        keys_att("facial_add_blush_off", "blush", [(0, "blush_base")])
    # 演示用的眨眼循环与说话
    for sd in "RL":
        if not has_closed:  # 没有闭眼图就不做眨眼（眼部网格挂在头部格子上，缩眼骨骼不起作用）
            continue
        if sd == "R":
            face_keys("blink", [(0, "face"), (2.70, "face_closed"), (2.84, "face")])
        keys_att("blink", f"lash_{sd}", [(0, f"lash_{sd}"), (2.70, f"eye_closed_{sd}"), (2.84, f"lash_{sd}")])
        keys_att("blink", f"eyewhite_{sd}", [(0, f"eyewhite_{sd}"), (2.70, None), (2.84, f"eyewhite_{sd}")])
        keys_att("blink", f"iris_{sd}", [(0, f"iris_{sd}"), (2.70, None), (2.84, f"iris_{sd}")])
        # 只换层、不缩眼骨骼：眼白 / 睫毛网格挂在头部格子上不跟 f_eye 缩，只有虹膜（f_eye 的子骨骼）被压扁，
        # 闭眼前后几帧虹膜上下露出一圈眼白（2026-10-09 用户指出「眨眼闭眼的时候是不是图层穿模了」）
        keys_bone("blink", f"f_eye_{sd}", "scale", 3.0, lambda u, t: (1, 1))  # 时长保持 3s 一循环
    seq = [(0, "mouth_smile")]
    rng = np.random.default_rng(3)
    t = 0.1
    while t < 2.0 and has_ah:
        seq.append((round(t, 3), "mouth_ah"))
        t += float(rng.uniform(0.12, 0.22))
        seq.append((round(t, 3), "mouth_smile"))
        t += float(rng.uniform(0.06, 0.14))
    keys_att("talk", "mouth", seq)
    keys_bone("talk", "f_mouth", "scale", 2.0, lambda u, t: (1, 0.75 + 0.25 * abs(math.sin(TAU * u * 5))))

    # 手势：每只手 in（换图 + 手势骨骼从略偏静止的位置缓动到位）/ active（保持 + 微动，循环）/ out（反向）。
    # 换图在第 0 帧、不做交叉淡化：app 的 AnimationState 默认 mixAttachmentThreshold=0，新片段的附件在混合开始时就生效，
    # 淡化只会多出两只半透明手臂叠在一起的帧（2026-10-09 实测）。ryza 的 in_up 也只在第 0 帧换图。
    T_IN, ARRIVE = 0.3, 0.15   # 到位动作占手势与静止角度差的 15%，单段最多 15°
    letter = {"L": "F", "R": "G"}  # ryza：F = 角色左臂，G = 右臂
    order = sorted(G.keys(), key=lambda n: (n != "wave", n))
    gesture_index = {}

    def g_keys(an, gname, sd, d, dur, off_fn, wiggle=None):
        """手势骨骼：off_fn(u) ∈ [0,1] 为偏向静止的程度（0 = 正好是手势姿势）。"""
        def cap(x):
            return max(-15.0, min(15.0, x))
        parts = {"arm": (f"ga_{gname}_{sd}", -cap(ARRIVE * d["arm_r"])),
                 "fore": (f"gf_{gname}_{sd}", -cap(ARRIVE * d["fore_r"])),
                 "hand": (f"gh_{gname}_{sd}", -cap(ARRIVE * d["hand_r"]))}
        for part, (bn, off) in parts.items():
            keys_bone(an, bn, "rotate", dur,
                      lambda u, t, off=off, part=part: off * off_fn(u) + (wiggle(u, part) if wiggle else 0))

    def att_keys(an, sd, gslot, gatt):
        keys_att(an, f"arm_{sd}", [(0, None)])
        keys_rgba(an, f"arm_{sd}", [(0, "ffffffff")])
        keys_att(an, gslot, [(0, gatt)])
        keys_rgba(an, gslot, [(0, "ffffffff")])
        for other in gslots:  # 同一只手的其余手势插槽保持空
            if other != gslot and other.startswith(f"garm_{sd}"):
                keys_att(an, other, [(0, None)])

    # 000 = 静止手臂（app 的「默认手臂」组）
    zero = {"arm_t": (0, 0), "arm_r": 0, "arm_s": 1, "fore_r": 0, "fore_s": 1, "hand_r": 0}
    for sd in "RL":
        base = f"motion_add_{letter[sd]}_000_active"
        body(base, f"arm_{sd}", 2.0, lambda u, t: (0, 0))
        for bn in (f"arm_{sd}", f"fore_{sd}", f"hand_{sd}"):
            keys_bone(base, bn, "rotate", 2.0, lambda u, t: 0)
            keys_bone(base, bn, "scale", 2.0, lambda u, t: (1, 1))
        for gs in gslots:
            if gs.startswith(f"garm_{sd}"):
                keys_att(base, gs, [(0, None)])
        keys_att(base, f"arm_{sd}", [(0, f"arm_{sd}")])
        keys_rgba(base, f"arm_{sd}", [(0, "ffffffff")])
    for i, gname in enumerate(order, start=1):
        gesture_index[gname] = i
        for sd in G[gname]["sides"]:
            d, _ = gposes[(gname, sd)]
            gslot = f"garm_{sd}_back" if gname in back_gestures else f"garm_{sd}"
            gatt = f"g_{gname}_{sd}"
            base = f"motion_add_{letter[sd]}_{i:03d}"
            # in：缓出（先快后慢）到位
            g_keys(f"{base}_in_up", gname, sd, d, T_IN, lambda u: (1 - u) ** 2)
            att_keys(f"{base}_in_up", sd, gslot, gatt)
            if gname == "wave":
                def wig(u, part):
                    return {"fore": 14 * math.sin(TAU * u * 3), "hand": 6 * math.sin(TAU * u * 3 - 0.8)}.get(part, 0)
            else:
                def wig(u, part, ph=i):
                    return {"arm": 1.0 * math.sin(TAU * u + ph), "fore": 1.5 * math.sin(TAU * u + ph + 0.7)}.get(part, 0)
            g_keys(f"{base}_active", gname, sd, d, 2.0, lambda u: 0, wiggle=wig)
            att_keys(f"{base}_active", sd, gslot, gatt)
            # out：缓入（先慢后快）往回收，下一段（静止手臂 / 下一个手势）开始时换图
            g_keys(f"{base}_out_up", gname, sd, d, T_IN, lambda u: u ** 2)
            att_keys(f"{base}_out_up", sd, gslot, gatt)
    meta_out = {"gestures": {g: {"index": gesture_index[g], "sides": G[g]["sides"],
                                 "letters": [letter[sd] for sd in G[g]["sides"]]} for g in order},
                "scale": SC, "y0": y0, "aim_ref": aim_ref}
    json.dump(meta_out, open(os.path.join(a.rig_dir, f"{a.name}.rigmeta.json"), "w"), ensure_ascii=False, indent=1)

    # Spine 按 order = 0..约束总数−1 逐个找约束排进更新队列，order 超出总数的约束永远不会执行 → 统一连续编号
    for i, c in enumerate(transform + physics):
        c["order"] = i
    sk = {"skeleton": {"hash": "front-rig", "spine": "4.2.43", "x": -R.cx * SC, "y": y0, "width": meta["size"][0] * SC,
                       "height": meta["size"][1] * SC, "images": "./images/"},
          "bones": R.bones, "slots": slots, "transform": transform, "physics": physics,
          "skins": [{"name": "default", "attachments": skin}], "animations": anims}
    with open(os.path.join(a.rig_dir, f"{a.name}.json"), "w") as f:
        json.dump(sk, f, ensure_ascii=False)
    print(f"bones={len(R.bones)} slots={len(slots)} transform={len(transform)} physics={len(physics)} animations={len(anims)}")
    for k, (nv, nt) in stats.items():
        print(f"  mesh {k}: {nv} 顶点 / {nt} 三角形")


if __name__ == "__main__":
    main()
