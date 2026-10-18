"""3D 动作（mocap-to-vrm.py 重定向到 VRM 的 .blend）→ 正 / 侧 / 背三个正交视角的 2D 关节轨迹（一个循环），给 dir-rig.py --motion。

用法（Blender 5.2，无界面）：
    blender -b <clip.blend> --python scripts/mocap-views.py -- <out.json> [--min-period 15]

为什么：三个视角的 2D 骨骼如果各自手写动作，节拍可以对齐，但步幅、起伏、手臂摆幅在切视角那一下不保证对得上；
同一段 3D 动作按三台相机投影，三套 2D 动作就是同一个动作的三个投影，切视角时姿势在几何上对应（2026-10-10 用户提出）。
步骤：
1. 关节世界坐标（VRM 骨骼：髋中心、左右髋 / 膝 / 踝 / 脚尖、肩 / 肘 / 腕 / 手尖、颈、头、头顶）。
2. 角色坐标系：前方 f = 整段髋部水平位移方向，上 z，右 r = f × z。
3. 找循环：相对髋部的姿势在 [min-period, 帧数) 范围里找 pose(a) ≈ pose(a + P) 误差最小的 (a, P)（同误差偏好短周期 = 一个步态周期）。
4. 原地化：髋部沿 f 的位移去掉线性趋势（匀速前进），保留起伏；首尾残差按 t/P 线性摊掉，循环无缝。
4b. 左右对称化（默认）：每帧与半周期后的左右镜像帧取平均。
5. 投影：正面 x = −r·p（角色右手在画面左）、侧面 x = f·p（朝画面右，看到的是角色右侧）、背面 x = r·p；y = z；
   另存沿视线朝镜头的深度（正面 f·p、侧面 r·p、背面 −f·p），dir-rig.py 按它逐帧定手臂 / 腿的前后绘制顺序。
输出米制坐标 + 每段骨骼的 3D 长度（投影长度 / 3D 长度 = 透视缩短）。
"""
import argparse
import json
import math
import sys

import bpy
import numpy as np

JOINTS = {  # 名字: (VRM 骨骼, head / tail)
    "hips": ("J_Bip_C_Hips", "head"),
    "hip_L": ("J_Bip_L_UpperLeg", "head"), "knee_L": ("J_Bip_L_LowerLeg", "head"), "ankle_L": ("J_Bip_L_Foot", "head"),
    "toe_L": ("J_Bip_L_Foot", "tail"),
    "hip_R": ("J_Bip_R_UpperLeg", "head"), "knee_R": ("J_Bip_R_LowerLeg", "head"), "ankle_R": ("J_Bip_R_Foot", "head"),
    "toe_R": ("J_Bip_R_Foot", "tail"),
    "shoulder_L": ("J_Bip_L_UpperArm", "head"), "elbow_L": ("J_Bip_L_LowerArm", "head"), "wrist_L": ("J_Bip_L_Hand", "head"),
    "tip_L": ("J_Bip_L_Hand", "tail"),
    "shoulder_R": ("J_Bip_R_UpperArm", "head"), "elbow_R": ("J_Bip_R_LowerArm", "head"), "wrist_R": ("J_Bip_R_Hand", "head"),
    "tip_R": ("J_Bip_R_Hand", "tail"),
    "neck": ("J_Bip_C_Neck", "head"), "head": ("J_Bip_C_Head", "head"), "head_top": ("J_Bip_C_Head", "tail"),
}
SEGS = {  # dir-rig 骨骼: (起点关节, 终点关节)
    "thigh_L": ("hip_L", "knee_L"), "shin_L": ("knee_L", "ankle_L"),
    "thigh_R": ("hip_R", "knee_R"), "shin_R": ("knee_R", "ankle_R"),
    "arm_L": ("shoulder_L", "elbow_L"), "fore_L": ("elbow_L", "wrist_L"), "hand_L": ("wrist_L", "tip_L"),
    "arm_R": ("shoulder_R", "elbow_R"), "fore_R": ("elbow_R", "wrist_R"), "hand_R": ("wrist_R", "tip_R"),
    "spine": ("hips", "neck"), "neck": ("neck", "head"), "head": ("head", "head_top"),
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("--min-period", type=int, default=15)
    p.add_argument("--no-symmetric", action="store_true",
                   help="不做左右对称化（默认做：每帧与半周期后的左右镜像帧取平均，走 / 跑这类循环动作按游戏惯例严格对称）")
    a = p.parse_args(argv)
    sc = bpy.context.scene
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE" and "J_Bip_C_Hips" in o.data.bones and o.visible_get())
    act = arm.animation_data.action
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    names = list(JOINTS)
    P = []
    for f in range(f0, f1 + 1):
        sc.frame_set(f)
        row = []
        for n in names:
            b, end = JOINTS[n]
            pb = arm.pose.bones[b]
            v = arm.matrix_world @ (pb.head if end == "head" else pb.tail)
            row.append((v.x, v.y, v.z))
        P.append(row)
    P = np.array(P)  # (帧, 关节, 3)
    n = len(P)
    hips = P[:, 0]
    d = hips[-1, :2] - hips[0, :2]
    fwd = np.array([d[0], d[1], 0.0]) / max(np.linalg.norm(d), 1e-6)
    up = np.array([0, 0, 1.0])
    rgt = np.cross(fwd, up)
    # 角色坐标：(前, 右, 上)，原点 = 第一帧髋部的水平位置、地面 z
    rel = P - np.array([hips[0, 0], hips[0, 1], 0.0])
    C = np.stack([rel @ fwd, rel @ rgt, rel[..., 2]], -1)
    # 找循环：相对髋部的姿势
    pose = C - C[:, :1]
    best = None
    for per in range(a.min_period, n):
        for s in range(0, n - per):
            e = float(np.mean(np.linalg.norm(pose[s] - pose[s + per], axis=-1)))
            score = e + 0.0004 * per  # 同误差偏好短周期
            if best is None or score < best[0]:
                best = (score, s, per, e)
    _, s, per, err = best
    cyc = C[s:s + per + 1].copy()
    # 原地化：髋部前向位移去线性趋势；整段平移使首帧髋部前向 = 0
    t = np.linspace(0, 1, per + 1)[:, None]
    travel = cyc[-1, 0, 0] - cyc[0, 0, 0]
    cyc[..., 0] -= cyc[0, 0, 0] + travel * t
    # 首尾残差线性摊掉（循环无缝）
    res = cyc[-1] - cyc[0]
    cyc -= res[None] * t[..., None]
    cyc = cyc[:-1]
    # 左右对称化：pose(t) 与 mirror(pose(t + P/2)) 取平均。镜像 = 右方向坐标取反 + 左右关节互换。
    # 真人动捕有个人习惯：CMU 09_01 每帧与半周期镜像平均差 4.3cm（走 02_01 为 3.3cm），左手腕常摆到中线、右手腕偏外，
    # 正面看左右不一样（2026-10-10 用户指出「跑步不应该是对称的吗」）。游戏里的循环动作一般都这样对称化
    sym_err = None
    if not a.no_symmetric:
        F = len(cyc)
        swap = [names.index(n[:-1] + ("R" if n.endswith("L") else "L")) if n[-2:] in ("_L", "_R") else i
                for i, n in enumerate(names)]
        mir = cyc[:, swap].copy()
        mir[..., 1] *= -1  # 右方向坐标取反（髋部的右方向坐标也取反，围绕前进轴镜像）
        h = F / 2
        idx = np.arange(F) + h
        i0 = np.floor(idx).astype(int) % F
        i1 = (i0 + 1) % F
        w = (idx - np.floor(idx))[:, None, None]
        mir_shift = mir[i0] * (1 - w) + mir[i1] * w
        sym_err = float(np.mean(np.linalg.norm((cyc - cyc[:, :1]) - (mir_shift - mir_shift[:, :1]), axis=-1)))
        cyc = 0.5 * (cyc + mir_shift)
    # 地面：循环里最低的踝 / 脚尖高度
    ground = float(min(cyc[:, names.index(k), 2].min() for k in ("toe_L", "toe_R", "ankle_L", "ankle_R")))
    views, depth = {}, {}
    # x：画面水平；dep：沿视线朝镜头的距离（越大越近，用来定手臂在身体前 / 后）
    for v, xf, df in (("front", lambda q: -q[..., 1], lambda q: q[..., 0]),
                      ("side", lambda q: q[..., 0], lambda q: q[..., 1]),
                      ("back", lambda q: q[..., 1], lambda q: -q[..., 0])):
        xy = np.stack([xf(cyc), cyc[..., 2] - ground], -1)
        views[v] = np.round(xy, 5).tolist()
        depth[v] = np.round(df(cyc), 5).tolist()
    len3d = {}
    for sg, (j0, j1) in SEGS.items():
        len3d[sg] = float(np.median(np.linalg.norm(cyc[:, names.index(j1)] - cyc[:, names.index(j0)], axis=-1)))
    fps = sc.render.fps / sc.render.fps_base
    out = {"clip": act.name, "fps": fps, "frames": per, "start": f0 + s, "loop_err_m": err, "symmetrized": sym_err is not None,
           "asym_before_m": sym_err,
           "travel_m": float(travel), "speed_mps": float(travel * fps / per), "ground_z": ground,
           "joints": names, "segs": SEGS, "len3d": len3d, "views": views, "depth": depth,
           "model_height_m": float(cyc[:, names.index("head_top"), 2].max() - ground)}
    json.dump(out, open(a.out, "w"), indent=0)
    print(f"MOTION {act.name}: 循环 {per} 帧（从第 {f0 + s} 帧），首尾姿势误差 {err * 100:.1f}cm，"
          f"每周期前进 {travel:.2f}m，速度 {travel * fps / per:.2f}m/s"
          + (f"，对称化前左右镜像平均差 {sym_err * 100:.1f}cm" if sym_err is not None else ""))


if __name__ == "__main__":
    main()
