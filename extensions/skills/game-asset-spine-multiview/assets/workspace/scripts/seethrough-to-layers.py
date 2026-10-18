"""See-through 拆层结果 → front-rig.py 认的层目录（layers.json + 各层 PNG，原图画布坐标）。不做任何差分 / 颜色切分。

    python -I scripts/seethrough-to-layers.py \
        <front.png> <seethrough_dir> <poses.json> <out_dir> [--head-hires <dir>]

seethrough_dir：comfy-run-api.py --seethrough 拷出来的目录（layers.json + 各层 PNG，坐标在「原图按长边居中补成正方形、
  缩到推理分辨率」的空间里）。分辨率从原图长边与层坐标自动推不出来，所以从 9_00.png（节点预览图，正方形 = 推理分辨率）读。
--head-hires（默认 <seethrough_dir>/head_hires）：本项目给 ComfyUI-See-through 节点打的补丁（config/patches/see-through-head-hires.patch）另存的头部第二遍
  推理结果，已按原图像素尺寸、带 head.json（src_xyxy）。有它时脸、耳、五官、眉用它（原图分辨率），否则用节点缩小后的层。
poses.json：pose-extract.py 对同一张 front.png 的 DWPose 结果（骨骼位置用；front-rig.py 也读它的 kp / face）。
  写 - 表示没有（侧面 / 背面图给 dir-rig.py 用）：左右按头部层的水平中线分，layers.json 的 kp / face 为 null。

层对应（See-through 标签 → front-rig 层名；-r = 画面左 = 角色右 = R）：
  back hair → hair_back；legwear + footwear → legs；neck + bottomwear + topwear (+ neckwear) → body；
  ears + face → face；nose → nose；eyewhite / irides / eyelash / eyebrow → *_R / *_L；mouth → mouth_smile；
  handwear-r / -l → arm_R / arm_L；front hair (+ headwear) → hair_front。
合并按 See-through 的逐像素深度图（*_depth.png，越大越远）每个像素各自从远到近、用预乘 alpha 叠。只按整层中位深度排会出错：
  上衣层里带着补画出来的领口内侧（衣服后片），整层比脖子近，就把脖子盖成灰色（2026-10-09 1536 实测）。
  头部高分辨率层没有深度图，用节点同名层的深度图放大后代替。缩放都在预乘 alpha 下做（直通 alpha 缩放会在边缘带出透明处的杂色）。
头部高分辨率层没有左右拆分：按脸中线（DWPose 鼻尖 x）分左右——这是给已经分好的部件定侧别，不是切图。
表情（闭眼、张嘴）、腮红、手势这里没有；front-rig.py 对缺的层跳过。
"""
import argparse
import json
import os

import cv2
import numpy as np
from PIL import Image


def premul(rgba):
    a = rgba[..., 3:].astype(np.float32) / 255
    return np.concatenate([rgba[..., :3].astype(np.float32) * a, a * 255], -1)


def unpremul(p):
    a = np.clip(p[..., 3:], 0, 255)
    rgb = np.where(a > 0.5, p[..., :3] * 255 / np.maximum(a, 1e-3), 0)
    return np.concatenate([np.clip(rgb, 0, 255), a], -1).round().astype(np.uint8)


def place(crop, f, x0, y0, W, H):
    """把一张层图按缩放 f、左上角 (x0, y0)（画布像素，可为小数）放进 W×H 画布（预乘 alpha 下 Lanczos）。"""
    M = np.float32([[f, 0, x0], [0, f, y0]])
    flags = cv2.INTER_LANCZOS4 if f > 1 else cv2.INTER_AREA
    if f < 1:  # 缩小先 INTER_AREA 再平移，warpAffine 的 INTER_AREA 退化成双线性
        flags = cv2.INTER_LINEAR
    p = cv2.warpAffine(premul(crop), M, (W, H), flags=flags, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return unpremul(p)


def decontaminate(rgba, thr=0.85):
    """边缘去污染：α < thr 的像素 RGB 换成最近的 α ≥ thr 像素的颜色，α 不动（不切图）。
    See-through（透明 VAE 解码）的层在半透明外沿是灰色：张嘴层外沿 α 0.35 处 RGB (164,141,144)，
    叠在皮肤上成一圈暗线（2026-10-09 用户指出「嘴巴张开有一圈很奇怪的黑色描边」）。"""
    from scipy import ndimage
    al = rgba[..., 3]
    solid = al >= thr * 255
    if not solid.any() or solid.all():
        return rgba
    _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
    out = rgba.copy()
    edge = (~solid) & (al > 0)
    out[..., :3][edge] = rgba[..., :3][iy[edge], ix[edge]]
    return out


DECONTAM = ("mouth_ah", "mouth_happy")


def place_depth(dimg, f, x0, y0, W, H):
    M = np.float32([[f, 0, x0], [0, f, y0]])
    return cv2.warpAffine(dimg.astype(np.float32), M, (W, H), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


def zmerge(ims, depths):
    """逐像素按深度从远到近叠（预乘 alpha）。ims: 直通 alpha uint8 列表；depths: 同尺寸 float（越大越远）。"""
    if len(ims) == 1:
        return ims[0]
    P = np.stack([premul(im) for im in ims])
    D = np.stack([np.where(im[..., 3] > 0, d, -1e9) for im, d in zip(ims, depths)])
    order = np.argsort(-D, axis=0)
    out = np.zeros(P.shape[1:], np.float32)
    for k in range(len(ims)):
        src = np.take_along_axis(P, order[k][None, ..., None].repeat(4, -1), 0)[0]
        out = src + out * (1 - src[..., 3:] / 255)
    return unpremul(out)


def over(dst, src):
    """预乘 alpha 下 src 叠在 dst 上（都是直通 alpha uint8）。"""
    d, s = premul(dst), premul(src)
    sa = s[..., 3:] / 255
    return unpremul(s + d * (1 - sa))


SR = None


class Lazy(dict):
    """值在第一次 get / [] 时才算（层放进画布、超分都在这时做）。"""
    def add(self, k, fn):
        self._fns = getattr(self, "_fns", {})
        self._fns[k] = fn

    def __contains__(self, k):
        return k in getattr(self, "_fns", {})

    def get(self, k, default=None):
        if k not in self:
            return default
        if not dict.__contains__(self, k):
            dict.__setitem__(self, k, self._fns[k]())
        return dict.__getitem__(self, k)

    def __getitem__(self, k):
        if k not in self:
            raise KeyError(k)
        return self.get(k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("front")
    ap.add_argument("st_dir")
    ap.add_argument("poses")
    ap.add_argument("out")
    ap.add_argument("--head-hires", default=None, help="默认 <st_dir>/head_hires（存在时）")
    ap.add_argument("--closed", default=None, help="闭眼图（E2）的 See-through 目录：取睫毛层 → eye_closed_R/L")
    ap.add_argument("--ah", default=None, help="张嘴图（E3）的 See-through 目录：取嘴层 → mouth_ah")
    ap.add_argument("--happy", default=None, help="笑脸图（E4）的 See-through 目录：睫毛 → eye_happy_R/L，嘴 → mouth_happy")
    ap.add_argument("--no-decontam", action="store_true", help="不做边缘去污染（对比用）")
    ap.add_argument("--body", default=None,
                    help="衣身（neck / neckwear / bottomwear / topwear）改取这次 See-through 的结果（deepseek-chan：2048 那次裙子层是空的，1280 那次是全的）。"
                         "不同次的深度不能混着比，衣身内部只用这一次的深度合并，手臂前后也按这一次投票")
    ap.add_argument("--headwear", default=None,
                    help="头饰改取这次 See-through 的结果，单独成 headwear 层（不并进前发：两次的深度不能混比）。"
                         "前后按这一次内部头饰与前发重叠处的逐像素深度投票")
    ap.add_argument("--regions", default="",
                    help="逗号分隔的分部位 See-through 目录（带 crop.json，seethrough-regions.py 出的）。"
                         "非头部的层逐个挑：在哪一块里完整（不碰裁块内部边缘）且更清楚就用哪一块；一层只取一次的结果（深度不混比）")
    ap.add_argument("--sr", default=None,
                    help="放到画布前先用这个动漫超分模型放大（ComfyUI models/upscale_models 下的文件名，见 upscale-anime.py）；"
                         "只对需要放大的层（推理分辨率低于原图）做，头部原图分辨率层不动")
    ap.add_argument("--skip-tags", default="", help="逗号分隔，这些 See-through 标签不用（如 ears：模型把鲸鳍耳当人耳、补画了一对人耳）")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.sr:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        global SR
        SR = __import__("upscale-anime")
    front = np.array(Image.open(a.front).convert("RGBA"))
    H, W = front.shape[:2]
    S = max(W, H)
    ox, oy = (S - W) // 2, (S - H) // 2
    if a.poses != "-":
        pose = json.load(open(a.poses))[0]
        kp, face = pose["kp"], pose["face"]
        jaw = np.array([face[i] for i in range(17)])
        face_w = float(jaw[:, 0].max() - jaw[:, 0].min())
        mid_x = face[30][0]
    else:
        # 侧面 / 背面图（dir-rig.py 用）：没有可用的脸部关键点，左右按头部（前发 + 后发 + 脸）的水平中线分；
        # 侧面只有一只眼，分到哪一侧都行，dir-rig.py 不按左右用眼睛
        pose, kp, face, jaw, face_w, mid_x = {}, None, None, None, None, None

    def load_run(st_dir, hires_dir=None):
        """读一次 See-through 结果，返回 (get(tag), dget(tag), 推理分辨率)。"""
        res = Image.open(os.path.join(st_dir, "9_00.png")).size[0]
        # 分部位拆（seethrough-regions.py）：输入是原图的一块，crop.json 记它在原图里的位置
        cx0, cy0, cx1, cy1 = 0, 0, W, H
        if os.path.isfile(os.path.join(st_dir, "crop.json")):
            cx0, cy0, cx1, cy1 = json.load(open(os.path.join(st_dir, "crop.json")))["xyxy"]
        cw, ch = cx1 - cx0, cy1 - cy0
        cs = max(cw, ch)
        f = cs / res
        px, py = cx0 - (cs - cw) // 2, cy0 - (cs - ch) // 2
        info = json.load(open(os.path.join(st_dir, "layers.json"), encoding="utf-8"))
        st, dmap = Lazy(), {}
        for L in info["layers"]:
            def load_layer(L=L):
                im = np.array(Image.open(os.path.join(st_dir, L["filename"])).convert("RGBA"))
                if a.sr and f > 1.05:
                    # 先动漫超分再缩到画布尺寸（upscale-anime.py），代替直接 Lanczos 放大 f 倍
                    h0, w0 = im.shape[:2]
                    tw, th = max(1, round(w0 * f)), max(1, round(h0 * f))
                    im = SR.sr_rgba(im, a.sr, tw, th)
                    return place(im, f * w0 / tw, L["left"] * f + px, L["top"] * f + py, W, H)
                return place(im, f, L["left"] * f + px, L["top"] * f + py, W, H)
            st.add(L["name"], load_layer)  # 用到才读（超分慢，表情那几次只用头部层）
            dp = os.path.join(st_dir, L.get("depth_filename", ""))
            if L.get("depth_filename") and os.path.isfile(dp):
                dmap[L["name"]] = place_depth(np.array(Image.open(dp).convert("L")), f, L["left"] * f + px, L["top"] * f + py, W, H) / 255
            else:
                dmap[L["name"]] = np.full((H, W), L["depth_median"], np.float32)
        hires = {}
        hires_dir = hires_dir or os.path.join(st_dir, "head_hires")
        if os.path.isfile(os.path.join(hires_dir, "head.json")):
            hj = json.load(open(os.path.join(hires_dir, "head.json")))
            x1, y1, x2, y2 = hj["src_xyxy"]
            x1, y1, x2, y2 = x1 + cx0, y1 + cy0, x2 + cx0, y2 + cy0
            hj["src_xyxy"] = [x1, y1, x2, y2]
            for tag in hj["tags"]:
                p = os.path.join(hires_dir, f"{tag}.png")
                if not os.path.isfile(p):
                    continue
                im = np.array(Image.open(p).convert("RGBA"))
                full = np.zeros((H, W, 4), np.uint8)
                full[y1:y1 + im.shape[0], x1:x1 + im.shape[1]] = im[: H - y1, : W - x1]
                if tag in ("eyebrow", "eyewhite", "irides", "eyelash", "ears"):
                    xs = np.arange(W)[None, :, None]
                    hires[f"{tag}-r"] = np.where(xs < mid_x, full, 0).astype(np.uint8)  # 画面左 = 角色右 = -r
                    hires[f"{tag}-l"] = np.where(xs >= mid_x, full, 0).astype(np.uint8)
                else:
                    hires[tag] = full

        crop = None
        if hires:
            x1, y1, x2, y2 = hj["src_xyxy"]
            crop = np.zeros((H, W), bool)
            crop[y1:y2, x1:x2] = True

        def get(tag):
            if tag in skip or tag.rsplit("-", 1)[0] in skip:
                return None
            if tag in hires:
                # 头部第二遍只看头部裁剪框；部件伸出框外（deepseek-chan 的头饰）时高分辨率层是被截断的，用整图那遍的
                s = st.get(tag)
                if s is not None and (s[..., 3][~crop] > 127).sum() > 0.02 * max((s[..., 3] > 127).sum(), 1):
                    return s
                return hires[tag]
            return st.get(tag)

        def dget(tag):
            if tag in dmap:
                return dmap[tag]
            base = tag.split("-")[0]
            for k in (base, base + "-r", base + "-l"):
                if k in dmap:
                    return dmap[k]
            return np.full((H, W), 0.5, np.float32)
        get.hires = hires
        get.crop = (cx0, cy0, cx1, cy1)
        get.scale = f  # 推理图 1 像素 = 原图 f 像素，越小越清楚
        return get, dget, res

    skip = {t.strip() for t in a.skip_tags.split(",") if t.strip()}
    if mid_x is None:
        info0 = json.load(open(os.path.join(a.st_dir, "layers.json"), encoding="utf-8"))
        res0 = Image.open(os.path.join(a.st_dir, "9_00.png")).size[0]
        f0, xs0 = S / res0, []
        for L0 in info0["layers"]:
            if L0["name"] in ("front hair", "back hair", "face"):
                xs0 += [L0["left"] * f0 - ox, L0["right"] * f0 - ox]
        mid_x = (min(xs0) + max(xs0)) / 2 if xs0 else W / 2
    runs = {"base": load_run(a.st_dir, a.head_hires)}
    for k in ("closed", "ah", "happy", "body", "headwear"):
        if getattr(a, k):
            runs[k] = load_run(getattr(a, k))
    regions = [d.strip() for d in a.regions.split(",") if d.strip()]
    for i, d in enumerate(regions):
        runs[f"region{i}"] = load_run(d)
    res = runs["base"][2]

    def complete_in(run, tags, base_run):
        """这些标签在 run（某一块）里都有、且都不碰裁块的内部边缘（碰原图边不算）。"""
        get = runs[run][0]
        x0, y0, x1, y1 = get.crop
        for t in tags:
            if runs[base_run][0](t) is None:
                continue
            im = get(t)
            if im is None:
                return False
            al = im[..., 3] > 127
            if not al.any():
                return False
            ys, xs = np.nonzero(al)
            m = 4
            if (x0 > 0 and xs.min() <= x0 + m) or (y0 > 0 and ys.min() <= y0 + m) or \
               (x1 < W and xs.max() >= x1 - 1 - m) or (y1 < H and ys.max() >= y1 - 1 - m):
                return False
        return True

    def pick_run(tags, run):
        """分部位时给一层挑来源：基础那次头部高分辨率层优先，其余挑完整且最清楚的一块。"""
        if not regions or run not in ("base", "body", "headwear") or any(t in runs["base"][0].hires for t in tags):
            return run
        cands = sorted((r for r in runs if r.startswith("region")), key=lambda r: runs[r][0].scale)
        for r in cands:
            if runs[r][0].scale < runs[run][0].scale and complete_in(r, tags, run):
                return r
        return run

    def merge(tags, run="base"):
        get, dget, _ = runs[run]
        tags = [t for t in tags if get(t) is not None]
        if not tags:
            return np.zeros((H, W, 4), np.uint8), []
        return zmerge([get(t) for t in tags], [dget(t) for t in tags]),             [f"{run}:" + ("hires:" if get(t) is get.hires.get(t) else "st:") + t for t in tags]

    plan = {
        "hair_back": ["back hair"],
        "legs": ["legwear", "footwear"],
        "body": ("body" if a.body else "base", ["neck", "neckwear", "bottomwear", "topwear"]),
        # 耳朵单独一层（脸后面）：闭眼时换的脸来自另一次 See-through，耳朵是那次重新补画的，形状 / 颜色都不同，
        # 并在脸层里一起换，眨眼那一下耳朵会跳（2026-10-09 用户指出「眨眼那一瞬间耳朵的地方变化了」）
        "ears": ["ears-r", "ears-l"],
        "face": ["face"],
        "nose": ["nose"],
        "eyewhite_R": ["eyewhite-r"], "iris_R": ["irides-r"], "lash_R": ["eyelash-r"], "brow_R": ["eyebrow-r"],
        "eyewhite_L": ["eyewhite-l"], "iris_L": ["irides-l"], "lash_L": ["eyelash-l"], "brow_L": ["eyebrow-l"],
        "mouth_smile": ["mouth"],
        "arm_R": ["handwear-r"], "arm_L": ["handwear-l"],
        "hair_front": ["front hair"] + ([] if a.headwear else ["headwear"]),
        "headwear": ("headwear", ["headwear"]),
        "tail": ["tail"],
        "eye_closed_R": ("closed", ["eyelash-r"]), "eye_closed_L": ("closed", ["eyelash-l"]),
        # See-through 的脸层在眼睛位置留着一圈偏亮的底（睁眼时被眼白盖住），闭眼时露出来；
        # 闭眼图那次的脸层配它自己的闭眼睫毛时残留基本被盖住 → 闭眼 / 笑眼时脸也换成这张
        "face_closed": ("closed", ["face"]),
        "mouth_ah": ("ah", ["mouth"]),
        "eye_happy_R": ("happy", ["eyelash-r"]), "eye_happy_L": ("happy", ["eyelash-l"]),
        "mouth_happy": ("happy", ["mouth"]),
    }
    layers, srcs = {}, {}
    for name, tags in plan.items():
        run, tags = tags if isinstance(tags, tuple) else ("base", tags)
        if run not in runs:
            continue
        run = pick_run(tags, run)
        im, used = merge(tags, run)
        # 只对张嘴层做：全部层都做时重新合成误差 6.80 → 7.17（p99 41 → 56），半透明的外轮廓描线被换成了里面的填充色
        if name in DECONTAM and not a.no_decontam:
            im = decontaminate(im)
        m = im[..., 3] > 8
        if not m.any():
            print("空层", name, tags)
            continue
        ys, xs = np.nonzero(m)
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        Image.fromarray(im[y0:y1, x0:x1]).save(os.path.join(a.out, f"{name}.png"))
        layers[name] = {"bbox": [x0, y0, x1 - x0, y1 - y0], "area": int(m.sum()), "src": used}
        if name.startswith("eyewhite_"):
            pts = np.stack(np.nonzero(im[..., 3] > 127)[::-1], 1).astype(np.int32)
            layers[name]["hull"] = cv2.convexHull(pts).reshape(-1, 2).tolist()
        srcs[name] = im
    # 腿比衣身近的部分单独一层 legs_over（画在衣身前面）：正面跑步抬膝时，抬起的大腿在裙摆前面，
    # 整条腿层放在衣身后面会被裙子盖住（2026-10-10 用户指出「腿的图层在裙子后面」）。按 See-through 的逐像素深度分，不按颜色切；
    # 只取与衣身重叠、且腿更近的像素，边缘 2px 羽化。站姿时腿都在裙下，这一层基本为空就不输出
    if "legs" in srcs and "body" in srcs:
        g_, d_, _ = runs["base"]
        lt = [t for t in ("legwear", "footwear") if g_(t) is not None]
        bt = [t for t in ("bottomwear", "topwear") if g_(t) is not None]
        if lt and bt:
            dl = np.min(np.stack([np.where(g_(t)[..., 3] > 8, d_(t), 9.0) for t in lt]), 0)
            db = np.min(np.stack([np.where(g_(t)[..., 3] > 8, d_(t), 9.0) for t in bt]), 0)
            body_a = srcs["body"][..., 3] > 8
            near_m = (srcs["legs"][..., 3] > 8) & body_a & (dl < db - 0.01)  # 不能叫 over：会盖掉下面的合成函数 over()
            if near_m.sum() > 0.002 * W * H:
                near_m = cv2.dilate(near_m.astype(np.uint8), np.ones((3, 3), np.uint8))
                feather = cv2.GaussianBlur(near_m.astype(np.float32), (5, 5), 0)
                im = srcs["legs"].copy()
                im[..., 3] = (im[..., 3].astype(np.float32) * feather).round().astype(np.uint8)
                m = im[..., 3] > 8
                ys, xs = np.nonzero(m)
                x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
                Image.fromarray(im[y0:y1, x0:x1]).save(os.path.join(a.out, "legs_over.png"))
                layers["legs_over"] = {"bbox": [x0, y0, x1 - x0, y1 - y0], "area": int(m.sum()), "src": ["legs × 深度比衣身近"]}
                print(f"legs_over：{int(m.sum())} 像素的腿比衣身近，单独一层画在衣身前")
    # 手臂在身体前还是后：两者重叠处按逐像素深度投票（kurumi 实测 99.7% 是衣身在前——袖子内侧被衣身挡住）
    get, dget, _ = runs["body" if a.body else "base"]
    votes, arm_votes = [], {}
    for arm in ("handwear-r", "handwear-l"):
        av = []
        for bt in ("topwear", "bottomwear"):
            if get(arm) is None or get(bt) is None:
                continue
            ov = (get(arm)[..., 3] > 127) & (get(bt)[..., 3] > 127)
            av += list((dget(arm)[ov] < dget(bt)[ov]).astype(np.uint8))
        votes += av
        if av:  # 每只手臂单独的投票（侧面图：近侧手臂在衣身前、远侧在后），dir-rig.py 用
            arm_votes["arm_R" if arm.endswith("-r") else "arm_L"] = float(np.mean(av))
    arms_behind = bool(votes) and float(np.mean(votes)) < 0.5
    # 单独的头饰层在前发前还是后（deepseek-chan 种子 7：重叠处 93% 前发在前——鲸鳍耳从侧发后面伸出）
    hw_front = None
    if "headwear" in runs:
        hg, hd, _ = runs["headwear"]
        if hg("headwear") is not None and hg("front hair") is not None:
            ov = (hg("headwear")[..., 3] > 127) & (hg("front hair")[..., 3] > 127)
            if ov.any():
                hw_front = float((hd("headwear")[ov] < hd("front hair")[ov]).mean())
    hw_order = ["hair_front", "headwear"] if hw_front is not None and hw_front >= 0.5 else ["headwear", "hair_front"]
    # 重新合成检查按 front-rig.py 的插槽顺序叠（就是骨骼里静止时看到的样子）
    rig_order = ["hair_back", "tail", "legs"] + (["arm_R", "arm_L"] if arms_behind else []) + ["body", "ears", "face", "nose", "eyewhite_R", "iris_R", "lash_R", "eyewhite_L", "iris_L",
                 "lash_L", "brow_R", "brow_L", "mouth_smile"] + ([] if arms_behind else ["arm_R", "arm_L"]) + hw_order
    order = [n for n in rig_order if n in srcs]
    comp = np.zeros((H, W, 4), np.uint8)
    for n in order:
        comp = over(comp, srcs[n])
    Image.fromarray(comp).save(os.path.join(a.out, "_recomp.png"))
    fg = front[..., 3] > 200
    err = np.abs(comp[..., :3].astype(np.float32) - front[..., :3]).mean(-1)
    meta = {"size": [W, H], "order": order, "layers": layers, "arms_behind_body": arms_behind, "arm_chain": "layer",
            "arms_front_vote": float(np.mean(votes)) if votes else None, "arm_front_votes": arm_votes,
            "headwear_front_of_hair": bool(hw_front is not None and hw_front >= 0.5), "headwear_front_vote": hw_front,
            "kp": kp, "face": face,
            "hand_r": pose.get("hand_r"), "hand_l": pose.get("hand_l"), "gestures": {},
            "chin_y": float(jaw[:, 1].max()) if jaw is not None else None, "face_w": face_w, "mid_x": float(mid_x),
            "source": {"seethrough": a.st_dir, "res": res, "closed": a.closed, "ah": a.ah, "happy": a.happy,
                       "body": a.body, "headwear": a.headwear, "regions": regions, "skip_tags": sorted(skip), "sr": a.sr},
            "hidden": sorted(n for n in layers if n.startswith(("eye_closed", "eye_happy")) or n in ("mouth_ah", "mouth_happy", "face_closed")),
            "recomposite": {"mean_abs_err_fg": float(err[fg].mean()), "p99_fg": float(np.percentile(err[fg], 99)),
                            "alpha_miss": float(((comp[..., 3] < 128) & fg).mean() / max(fg.mean(), 1e-6))}}
    json.dump(meta, open(os.path.join(a.out, "layers.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(meta["recomposite"]), "层:", ", ".join(f"{n}{layers[n]['bbox'][2:]}" for n in layers))


if __name__ == "__main__":
    main()
