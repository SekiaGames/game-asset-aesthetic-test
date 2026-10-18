"""方块风角色部件生成器（共用库）。被各角色脚本 import，产出 blocky-build.py 能读的 spec。

自写。手法参考 GPT 建的 DS 鲸鱼娘 bbmodel（data/blocky-ref/，493 块、几乎全部带旋转）：
- 裙子 = 一圈斜板（panel ring），板宽按周长均分再放大重叠；
- 头发 = 绕头一圈的发束（每束上下两段：上段外扩、下段内收，波波头的弧度），刘海单独一排；
- 眼睛 = 贴在脸前的零厚度薄片分层（眼白 / 虹膜 / 瞳孔 / 高光 / 睫毛）；
- 叠层部件用很小的 inflate 防 z-fighting。

坐标：Blockbench 模型单位；X+ = 角色右手侧，-Z = 正面，Y 向上。
旋转：Blockbench 方块旋转为 three.js Euler 'ZYX'（矩阵 Rz·Ry·Rx，先绕 X 再 Y 再 Z），单位度。
"""
import math

import numpy as np


def rot_matrix(rx, ry, rz):
    ax, ay, az = (math.radians(v) for v in (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def r3(v):
    return [round(float(t), 4) for t in v]


class Kit:
    def __init__(self):
        self.groups, self.cubes = [], []
        self._names = {}

    # ---------- 基础 ----------
    def name(self, base):
        n = self._names.get(base, 0)
        self._names[base] = n + 1
        return base if n == 0 else f"{base}_{n}"

    def group(self, name, parent=None, origin=(0, 0, 0), rotation=None):
        g = {"name": name, "origin": r3(origin)}
        if parent:
            g["parent"] = parent
        if rotation and any(rotation):
            g["rotation"] = r3(rotation)
        self.groups.append(g)
        return name

    def box(self, name, group, fr, to, mat, origin=None, rotation=None, faces=None, hide=None, inflate=0.0):
        """轴对齐方块（可带旋转）。inflate 只在建 spec 时把 from/to 外扩，避免依赖格式支持。"""
        fr = [fr[i] - inflate for i in range(3)]
        to = [to[i] + inflate for i in range(3)]
        c = {"name": self.name(name), "group": group, "from": r3(fr), "to": r3(to), "mat": mat}
        if rotation is not None and any(abs(v) > 1e-6 for v in rotation):
            c["rotation"] = r3(rotation)
            c["origin"] = r3(origin if origin is not None else [(fr[i] + to[i]) / 2 for i in range(3)])
        if faces:
            c["faces"] = faces
        if hide:
            c["hide"] = hide
        self.cubes.append(c)
        return c

    def centered(self, name, group, center, size, mat, **kw):
        fr = [center[i] - size[i] / 2 for i in range(3)]
        to = [center[i] + size[i] / 2 for i in range(3)]
        return self.box(name, group, fr, to, mat, **kw)

    def plane(self, name, group, x0, y0, x1, y1, z, mat, rotation=None, origin=None):
        """贴在 z 处、朝 -Z 的零厚度薄片（眼睛、嘴、腮红）。只保留 north 面。"""
        return self.box(name, group, [x0, y0, z], [x1, y1, z], mat, rotation=rotation, origin=origin,
                        hide=["south", "east", "west", "up", "down"])

    # ---------- 斜板：从 top 点挂到 bottom 点的一块板 ----------
    def slab(self, name, group, top, bottom, width, thick, mat, outward=None, faces=None, inflate=0.0):
        """板的上边中点在 top，下边中点在 bottom；板面朝外（局部 -Z → outward 水平方向）。
        outward：水平朝外方向（x, z）；不给时用 top→bottom 的水平分量。返回 cube。"""
        top, bottom = np.array(top, float), np.array(bottom, float)
        d = bottom - top
        L = float(np.linalg.norm(d))
        h = np.array([d[0], d[2]])
        if outward is None:
            outward = h if np.linalg.norm(h) > 1e-4 else np.array([0.0, -1.0])
        outward = np.array(outward, float)
        outward /= np.linalg.norm(outward)
        # 偏航：局部 -Z 转到 outward。R_y(θ)·(0,0,-1) = (-sinθ, 0, -cosθ)
        yaw = math.degrees(math.atan2(-outward[0], -outward[1]))
        # 俯仰：下垂方向在 outward 上的分量（正 = 往外张，负 = 往里收）
        out_comp = float(h @ outward)
        drop = -d[1]
        tilt = math.degrees(math.atan2(out_comp, drop))
        fr = [top[0] - width / 2, top[1] - L, top[2] - thick / 2]
        to = [top[0] + width / 2, top[1], top[2] + thick / 2]
        return self.box(name, group, fr, to, mat, origin=top.tolist(), rotation=[tilt, yaw, 0.0], faces=faces,
                        inflate=inflate)

    # ---------- 任意方向的梁：top→bottom 可以同时往外、往侧偏 ----------
    def beam(self, name, group, top, bottom, width, thick, mat, facing=(0, 0, 1), faces=None, ext=0.0):
        """slab 只能在 outward 平面里倾斜；beam 让局部 -Y 精确对准 top→bottom（双马尾这类往侧面飘又往下垂的部件）。
        facing：板面（局部 -Z）大致朝向，会被正交化到与长轴垂直。ext：两端各延长，接缝处互相插入不露缝。
        旋转矩阵按 Blockbench 的 Euler 'ZYX'（R = Rz·Ry·Rx）分解成角度。"""
        top, bottom = np.array(top, float), np.array(bottom, float)
        d = bottom - top
        L = float(np.linalg.norm(d))
        ay = -d / L                                   # 局部 +Y
        f = np.array(facing, float)
        az = -(f - (f @ ay) * ay)                     # 局部 +Z = -facing（正交化）
        az /= np.linalg.norm(az)
        ax = np.cross(ay, az)
        R = np.stack([ax, ay, az], 1)
        ry = math.asin(max(-1.0, min(1.0, -R[2, 0])))
        rx = math.atan2(R[2, 1], R[2, 2])
        rz = math.atan2(R[1, 0], R[0, 0])
        o = top - ay * ext
        fr = [o[0] - width / 2, o[1] - L - 2 * ext, o[2] - thick / 2]
        to = [o[0] + width / 2, o[1], o[2] + thick / 2]
        return self.box(name, group, fr, to, mat, origin=o.tolist(),
                        rotation=[math.degrees(rx), math.degrees(ry), math.degrees(rz)], faces=faces)

    # ---------- 一圈斜板（裙子 / 发束） ----------
    @staticmethod
    def ellipse_point(center, rx, rz, phi, y, p=2.0):
        """phi=0 在正面（-Z），90° 在角色右侧（+X）。p>2 是超椭圆（圆角矩形）：|x/rx|^p+|z/rz|^p=1，
        用来紧贴方形的腰——普通椭圆要放大 √2 倍才包得住方块的角。"""
        sn, cs = math.sin(math.radians(phi)), math.cos(math.radians(phi))
        e = 2.0 / p
        return [center[0] + rx * math.copysign(abs(sn) ** e, sn), y, center[1] - rz * math.copysign(abs(cs) ** e, cs)]

    @staticmethod
    def ellipse_normal(rx, rz, phi, p=2.0):
        sn, cs = math.sin(math.radians(phi)), math.cos(math.radians(phi))
        e = 2.0 / p
        x, z = math.copysign(abs(sn) ** e, sn), -math.copysign(abs(cs) ** e, cs)   # 单位超椭圆上的点
        n = np.array([math.copysign(abs(x) ** (p - 1), x) / rx, math.copysign(abs(z) ** (p - 1), z) / rz])
        return n / np.linalg.norm(n)

    def ring(self, name, group_of, top_ellipse, bottom_ellipse, n, thick, mat_of, overlap=1.25, phase=0.0,
             skip=None, faces_of=None):
        """top/bottom_ellipse = (center_xz, rx, rz, y[, p])，p 是超椭圆指数（默认 2 = 椭圆）。
        group_of(phi)、mat_of(i, phi) 决定骨骼和材质。"""
        (c0, rx0, rz0, y0), (c1, rx1, rz1, y1) = top_ellipse[:4], bottom_ellipse[:4]
        p0 = top_ellipse[4] if len(top_ellipse) > 4 else 2.0
        p1 = bottom_ellipse[4] if len(bottom_ellipse) > 4 else 2.0
        out = []
        for i in range(n):
            phi = phase + 360.0 * i / n
            if skip and skip(phi):
                continue
            t = self.ellipse_point(c0, rx0, rz0, phi, y0, p0)
            b = self.ellipse_point(c1, rx1, rz1, phi, y1, p1)
            circ_mid = math.pi * (rx0 + rz0 + rx1 + rz1) / 2
            w = circ_mid / n * overlap
            nrm = self.ellipse_normal((rx0 + rx1) / 2, (rz0 + rz1) / 2, phi, (p0 + p1) / 2)
            faces = faces_of(i, phi) if faces_of else None
            out.append(self.slab(name, group_of(phi), t, b, w, thick, mat_of(i, phi), outward=nrm, faces=faces))
        return out

    def spec(self, base):
        s = dict(base)
        s["groups"] = self.groups
        s["cubes"] = self.cubes
        return s
