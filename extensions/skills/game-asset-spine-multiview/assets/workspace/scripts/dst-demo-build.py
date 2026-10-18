"""把 src/dst-demo/ 和三视角骨骼打成可发布的一个目录（Artifact / 任意静态托管）。

    python scripts/dst-demo-build.py <manifest.json> <out_dir>

做的事：index.html 去掉 <!doctype>/<html>/<head>/<body> 外壳（Artifact 发布时自己套），import map 换成 jsDelivr 上
固定版本的 three 0.184.0 与 spine-threejs 4.2.120（与本地 node_modules 同版本），加 <meta name="dst-rig" content="rig/manifest.json">；
main.js 原样拷；清单里引用的骨骼 json / atlas / 图集页 png 拷到 rig/ 下，清单路径改成相对 rig/。
"""
import json
import os
import re
import shutil
import sys

here = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(here, "..", "src", "dst-demo")
man_path, out = sys.argv[1], sys.argv[2]
os.makedirs(os.path.join(out, "rig"), exist_ok=True)
html = open(os.path.join(src, "index.html"), encoding="utf-8").read()
html = re.sub(r"<!doctype html>\s*|<html[^>]*>\s*|</html>\s*|<head>\s*|</head>\s*|<body>\s*|</body>\s*", "", html, flags=re.I)
html = re.sub(r'<meta charset="utf-8">\s*|<meta name="viewport"[^>]*>\s*', "", html)
html = html.replace("../../node_modules/three/build/three.module.js",
                    "https://cdn.jsdelivr.net/npm/three@0.184.0/build/three.module.js")
html = html.replace("../../node_modules/@esotericsoftware/spine-threejs/dist/esm/spine-threejs.mjs",
                    "https://cdn.jsdelivr.net/npm/@esotericsoftware/spine-threejs@4.2.120/dist/esm/spine-threejs.mjs")
html = html.replace("<title>", '<meta name="dst-rig" content="rig/manifest.json">\n<title>', 1)
open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)
shutil.copy(os.path.join(src, "main.js"), os.path.join(out, "main.js"))
man = json.load(open(man_path, encoding="utf-8"))
base = os.path.dirname(os.path.abspath(man_path))
files = []
for v, d in man["views"].items():
    for k in ("json", "atlas"):
        s = os.path.join(base, d[k])
        dst = f"{v}/{os.path.basename(s)}"
        os.makedirs(os.path.join(out, "rig", v), exist_ok=True)
        shutil.copy(s, os.path.join(out, "rig", dst))
        d[k] = dst
        files.append("rig/" + dst)
        if k == "atlas":  # 图集页
            for line in open(s, encoding="utf-8"):
                line = line.strip()
                if line.endswith(".png"):
                    shutil.copy(os.path.join(os.path.dirname(s), line), os.path.join(out, "rig", v, line))
                    files.append(f"rig/{v}/{line}")
json.dump(man, open(os.path.join(out, "rig", "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
files.append("rig/manifest.json")
print("\n".join(["main.js"] + files))
