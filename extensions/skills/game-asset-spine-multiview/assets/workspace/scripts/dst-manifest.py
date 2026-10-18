"""三套方向骨骼（dir-rig.py 的输出）→ 演示页的清单 manifest.json。

    python scripts/dst-manifest.py <rig_root> [--name kurumi] [--speed-from side]

<rig_root> 下应有 front/、side/、back/ 三个目录，各含 <name>_<视角>.json / .atlas / .rigmeta.json（dir-rig.py 写的）。
写 <rig_root>/manifest.json：
- views：三套骨骼的相对路径和角色高（像素，演示页按它把三套缩放到同一身高）；
- height：正面的角色高；side_faces：侧面图朝向（dir-rig 的侧面按「朝画面右」处理）；
- speeds：走 / 跑的移动速度（角色高 / 秒），取 --speed-from 那套骨骼里动捕投影换算的像素速度 ÷ 角色高，
  演示页乘角色高度得世界速度，脚步不打滑。没有动捕动作（程序写的动作）时不写，演示页用固定值。
"""
import argparse
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rig_root")
    ap.add_argument("--name", default="kurumi")
    ap.add_argument("--speed-from", default="side")
    a = ap.parse_args()
    man = {"_说明": "dst-manifest.py 生成：三视角 Spine 骨骼，演示页 src/dst-demo/ 读它。", "side_faces": "right",
           "views": {}, "speeds": {}}
    metas = {}
    for v in ("front", "side", "back"):
        mp = os.path.join(a.rig_root, v, f"{a.name}_{v}.rigmeta.json")
        if not os.path.isfile(mp):
            continue
        m = json.load(open(mp, encoding="utf-8"))
        metas[v] = m
        man["views"][v] = {"json": f"{v}/{a.name}_{v}.json", "atlas": f"{v}/{a.name}_{v}.atlas", "height": m["height"]}
    if "front" not in metas:
        raise SystemExit("缺正面骨骼")
    man["height"] = metas["front"]["height"]
    src = metas.get(a.speed_from) or metas["front"]
    for an, info in (src.get("motion") or {}).items():
        man["speeds"][an] = round(info["speed_px_s"] / src["height"], 4)
    out = os.path.join(a.rig_root, "manifest.json")
    json.dump(man, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(out, {v: d["height"] for v, d in man["views"].items()}, man["speeds"])


if __name__ == "__main__":
    main()
