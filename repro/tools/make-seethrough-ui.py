#!/usr/bin/env python3
"""把作者的 API 格式 see-through.json 还原成 ComfyUI 画布能打开的 UI 格式工作流。

作者仓库里那份 `config/workflows/see-through.json` 是 **API 格式**（节点号 → {class_type, inputs}），
只能喂给 `/prompt`（`comfy-run-api.py` 就是这么用的）。ComfyUI 前端要的是 UI 格式
（`nodes` 数组 + `links` 数组），直接拖进去会报 `TypeError: e is not iterable` 并中止加载。

本脚本不去猜 widget 顺序，而是以 ComfyUI-See-through 官方仓库自带的 UI 工作流
（`workflows/seethrough-basic.json`，已 vendor 在 workflows/vendor/）为骨架，
再按作者 API 文件里的参数改写数值、补上作者多出来的 JoinImageWithAlpha 与层预览：

    python3 tools/make-seethrough-ui.py [--out <path>] [--install]

--install 会额外拷一份到 ComfyUI 的 user/default/workflows/，前端侧栏就能直接打开。
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENDOR = os.path.join(ROOT, "workflows", "vendor", "seethrough-basic.json")
DEFAULT_OUT = os.path.join(ROOT, "workflows", "see-through.ui.json")

# 作者 API 文件里的参数（见 config/workflows/see-through.json）
SEED = 42
# 作者用 1280，但 1280 在本机（M4 Pro / 48GB）会把整台机器顶到重启：
# 1280² 的 token 数是 1024² 的 1.56 倍，注意力与 21 层 RGBA 叠加后直接
# 触发系统级 OOM，连续 3 次（最新一次 2026-10-22 13:31 重启）。
# 1024 已实测完整跑通，默认值改成 1024；要试 1280 请自己加 --resolution。
RESOLUTION = 1024
STEPS = 30
# -1 = 按 layers 分辨率（1024）跑，会把 19 张图一批塞进 Marigold，MPS 上直接
# "Invalid buffer size: 50.00 GiB"。512 足够（深度是低频信息），实测 39s。
RESOLUTION_DEPTH = 512
TBLR_SPLIT = True
USE_LAMA = False
SAVE_PREFIX = "seethrough_kurumi"
LAYERDIFF_MODEL = "layerdifforg/seethroughv0.0.2_layerdiff3d"
DEPTH_MODEL = "layerdifforg/seethroughv0.0.1_marigold"


def load_vendor():
    with open(VENDOR, encoding="utf-8") as f:
        return json.load(f)


def node(nid, ntype, pos, size, widgets=None, inputs=None, outputs=None, order=0):
    return {
        "id": nid,
        "type": ntype,
        "pos": list(pos),
        "size": list(size),
        "flags": {},
        "order": order,
        "mode": 0,
        "inputs": inputs or [],
        "outputs": outputs or [],
        "properties": {"Node name for S&R": ntype},
        "widgets_values": widgets if widgets is not None else [],
    }


def inp(name, typ, link):
    return {"name": name, "type": typ, "link": link}


def out(name, typ, links):
    return {"name": name, "type": typ, "links": list(links), "slot_index": 0}


def build(src):
    """按类型取官方节点的 widgets_values，保证控件顺序与该版本节点定义一致。"""
    w = {n["type"]: n.get("widgets_values") or [] for n in src["nodes"]}

    ldm = list(w["SeeThrough_LoadLayerDiffModel"])
    ldm[0] = LAYERDIFF_MODEL
    ldm[3] = "none"          # quant_mode
    ldm[4] = True            # cache_tag_embeds
    ldm[5] = False           # group_offload
    ldm[6] = False           # auto_download（作者关掉，强制本地）

    dm = list(w["SeeThrough_LoadDepthModel"])
    dm[0] = DEPTH_MODEL
    dm[1] = "none"           # quant_mode
    dm[3] = False            # group_offload
    dm[4] = False            # auto_download

    nodes = [
        node(1, "LoadImage", (0, 0), (300, 340), ["", "image"], [],
             [out("IMAGE", "IMAGE", [1]), out("MASK", "MASK", [2])], 0),
        node(3, "SeeThrough_LoadLayerDiffModel", (0, 380), (330, 300), ldm, [],
             [out("layerdiff_model", "SEETHROUGH_LAYERDIFF_MODEL", [4])], 1),
        node(4, "SeeThrough_LoadDepthModel", (0, 720), (330, 230), dm, [],
             [out("depth_model", "SEETHROUGH_DEPTH_MODEL", [6])], 2),
        node(2, "JoinImageWithAlpha", (350, 0), (240, 60), [],
             [inp("image", "IMAGE", 1), inp("alpha", "MASK", 2)],
             [out("IMAGE", "IMAGE", [3])], 3),
        node(5, "SeeThrough_GenerateLayers", (640, 0), (300, 200),
             [SEED, "fixed", RESOLUTION, STEPS],
             [inp("image", "IMAGE", 3), inp("layerdiff_model", "SEETHROUGH_LAYERDIFF_MODEL", 4)],
             [out("layers", "SEETHROUGH_LAYERS", [5]),
              out("preview", "IMAGE", [10])], 4),
        node(6, "SeeThrough_GenerateDepth", (990, 0), (360, 190),
             [SEED, "fixed", RESOLUTION_DEPTH],
             [inp("layers", "SEETHROUGH_LAYERS", 5),
              inp("depth_model", "SEETHROUGH_DEPTH_MODEL", 6)],
             [out("layers_depth", "SEETHROUGH_LAYERS_DEPTH", [7])], 5),
        node(7, "SeeThrough_PostProcess", (1400, 0), (280, 160),
             [TBLR_SPLIT, USE_LAMA],
             [inp("layers_depth", "SEETHROUGH_LAYERS_DEPTH", 7)],
             [out("parts", "SEETHROUGH_PARTS", [8]),
              out("preview", "IMAGE", [9])], 6),
        node(8, "SeeThrough_SavePSD", (1730, 0), (280, 170),
             [SAVE_PREFIX, "Download PSD", "Download Depth PSD"],
             [inp("parts", "SEETHROUGH_PARTS", 8)],
             [out("info_file", "STRING", [])], 7),
        node(9, "PreviewImage", (1730, 220), (240, 290), [],
             [inp("images", "IMAGE", 9)], [], 8),
        node(10, "PreviewImage", (640, 250), (240, 290), [],
             [inp("images", "IMAGE", 10)], [], 9),
    ]

    links = [
        [1, 1, 0, 2, 0, "IMAGE"],
        [2, 1, 1, 2, 1, "MASK"],
        [3, 2, 0, 5, 0, "IMAGE"],
        [4, 3, 0, 5, 1, "SEETHROUGH_LAYERDIFF_MODEL"],
        [5, 5, 0, 6, 0, "SEETHROUGH_LAYERS"],
        [6, 4, 0, 6, 1, "SEETHROUGH_DEPTH_MODEL"],
        [7, 6, 0, 7, 0, "SEETHROUGH_LAYERS_DEPTH"],
        [8, 7, 0, 8, 0, "SEETHROUGH_PARTS"],
        [9, 7, 1, 9, 0, "IMAGE"],
        [10, 5, 1, 10, 0, "IMAGE"],
    ]

    return {
        "id": "see-through-ui",
        "revision": 0,
        "last_node_id": 10,
        "last_link_id": 10,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {
            "_说明": "由 repro/tools/make-seethrough-ui.py 生成：以 ComfyUI-See-through 0.5.0 官方 "
                     "workflows/seethrough-basic.json 为骨架，套用作者 API 版 see-through.json 的参数",
        },
        "version": 0.4,
    }


def validate(g):
    """结构自检：id 唯一、links 两端一致。UI 加载报错基本都是这两类。"""
    ids = [n["id"] for n in g["nodes"]]
    assert len(ids) == len(set(ids)), "节点 id 重复"
    by_id = {n["id"]: n for n in g["nodes"]}
    seen = set()
    for lid, src, sslot, dst, dslot, typ in g["links"]:
        assert lid not in seen, f"link {lid} 重复"
        seen.add(lid)
        assert src in by_id and dst in by_id, f"link {lid} 端点不存在"
        o = by_id[src]["outputs"][sslot]
        assert lid in (o.get("links") or []), f"link {lid} 未登记在源节点 {src} 输出上"
        i = by_id[dst]["inputs"][dslot]
        assert i.get("link") == lid, f"link {lid} 与目标节点 {dst} 输入 {dslot} 不符"
    for n in g["nodes"]:
        for i in n["inputs"]:
            if i.get("link") is not None:
                assert i["link"] in seen, f"节点 {n['id']} 输入 {i['name']} 指向不存在的 link"
        for o in n["outputs"]:
            for l in o.get("links") or []:
                assert l in seen, f"节点 {n['id']} 输出登记了不存在的 link {l}"
    return True


def comfy_workflows_dir():
    for c in (os.environ.get("COMFYUI_DIR"),
              "/Volumes/Data/Users/sekia/ComfyUI-Installs/ComfyUI/ComfyUI"):
        if c and os.path.isdir(os.path.join(c, "models")):
            d = os.path.join(c, "user", "default", "workflows")
            os.makedirs(d, exist_ok=True)
            return d
    return None


def main():
    global RESOLUTION, STEPS
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--resolution", type=int, default=RESOLUTION,
                    help="生成分辨率，默认 1024；1280 在本机会 OOM 重启整机")
    ap.add_argument("--steps", type=int, default=STEPS)
    a = ap.parse_args()
    RESOLUTION = a.resolution
    STEPS = a.steps

    g = build(load_vendor())
    validate(g)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=1)
    print(f"写好 {a.out}（{len(g['nodes'])} 节点 / {len(g['links'])} 连线）")

    if a.install:
        d = comfy_workflows_dir()
        if not d:
            print("找不到 ComfyUI 的 user/default/workflows，跳过 --install")
            return 1
        dst = os.path.join(d, "see-through.ui.json")
        shutil.copy(a.out, dst)
        print(f"已放到 {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
