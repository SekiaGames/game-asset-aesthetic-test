"""方块风角色模板（第一步：按画风统计选比例，再套角色特征）。

预设与参数来源：docs/blocky-style-reference.md（社区 186 个 YSM 模型实测）。
- jenny：珍妮 mod 系实测，头 8×8×7、总高 32、沙漏身形（肩 6、腰 5、胯 8、深 3）、细臂 2×10×2、腿 3 宽带外斜条，眼睛是小方块；
- ysm：二次元 YSM 常见比例，头 7、总高约 41（含头发），四肢两节且上下同粗（臂 3、腿约 3.6，手是前臂末端同宽的一截），裙子用斜板圈。
两者共用：贴图 2 px/单位；只用方块；骨骼名按 YSM 习惯；手臂外张（13° / 17°）避开裙子。
胸部：--bust none|block|round|pair，--bust-size s|m|l。

角色只描述特征和配色（CHARS），比例不跟原画走：
  hair: bob | long；headwear: None | maid；ears: None | whale；sleeve: short | long；
  skirt: len short | long，front 面板材质，frill 荷叶边；apron / back_bow / tail / hairclip / hair_bows；
  torso_front（前襟材质）、waist_ribbon、neck_bow、leg_mat、strap。

自写（部件生成与像素脸），手法参考：斜板 / 板圈 scripts/blocky-kit.py；
iMasterProX/mcbemodelingmasterAI docs/03-shape-rules（不要阶梯、倾斜件伸进相接部件）。

用法：
  python scripts/blocky-template.py --char kurumi --preset jenny --bust block --bust-size m --out output/blocky/kurumi-jenny/spec.json
  python scripts/blocky-template.py --char deepseek --preset ysm --bust round --bust-size m --out output/blocky/deepseek-ysm/spec.json
"""
import argparse
import importlib.util
import json
import math

import numpy as np
from pathlib import Path

_s = importlib.util.spec_from_file_location("blocky_kit", Path(__file__).with_name("blocky-kit.py"))
_m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_m)
Kit = _m.Kit
_s = importlib.util.spec_from_file_location("blocky_clip", Path(__file__).with_name("blocky-clip-check.py"))
CLIP = importlib.util.module_from_spec(_s)
_s.loader.exec_module(CLIP)

_OPTIONAL = {}
for _key, _file in (("hair", "blocky-box-hair.py"), ("outfit", "blocky-stage-outfit.py"),
                     ("witch", "blocky-witch-outfit.py")):
    _s = importlib.util.spec_from_file_location("blocky_" + _key, Path(__file__).with_name(_file))
    _m = importlib.util.module_from_spec(_s)
    _s.loader.exec_module(_m)
    _OPTIONAL[_key] = _m

# ---------------- 角色参数（只放特征 / 配色，不放比例） ----------------
KURUMI = {
    "palette": {
        "s": "#fde5d4", "h": "#f0819d", "k": "#2b1d28", "I": "#c2457a", "D": "#6e1840", "L": "#ec8fb4",
        "w": "#ffffff", "W": "#ffffff", "p": "#f7bcb6", "m": "#b35a5a",
        "a": "#f28aa5", "b": "#de6b8b", "c": "#ffc7d6", "e": "#f7a6bd",
    },
    "materials": {
        "skin": {"gradient": ["#fde6d6", "#f7d8c8"]},
        "hair": {"gradient": ["#ef7f9b", "#f59cb5"], "streaks": {"amount": 16}, "hl": {"at": 0.3, "color": "#ffc7d6"}},
        "hair_low": {"gradient": ["#f496b0", "#fab4c8"], "streaks": {"amount": 14}},
        "hair_in": {"fill": "#d9668a"},
        "dress": {"gradient": ["#fcfafc", "#ece6f0"]},
        "dress_hem": {"gradient": ["#fcfafc", "#ece6f0"], "hband": [{"from_bottom": 0, "rows": 1, "color": "#d6ccdb"}]},
        "dress_in": {"fill": "#ddd3e1"},
        "collar": {"fill": "#ffffff", "frame": "#b6a9bd", "frame_all": True},
        "sleeve": {"gradient": ["#fcfafc", "#efe9f2"], "hband": [{"from_bottom": 0, "rows": 1, "color": "#d6ccdb"}]},
        "red": {"fill": "#a3243f"},
        "red_dk": {"fill": "#7a1730"},
        "shoe": {"gradient": ["#6a2236", "#4e1828"], "hband": [{"from_bottom": 0, "rows": 1, "color": "#33101b"}]},
        "white": {"fill": "#ffffff", "shade": False},
        "iris": {"gradient": ["#7a1c46", "#d4558a"], "shade": False},
        "lash": {"fill": "#2b1d28", "shade": False},
        "blush": {"fill": "#f7bcb6", "shade": False},
    },
    "eye": {"w": 4, "h": 4},
    "mouth": False,
    "hair": "bob",
    "hairclip": True,
    "neck_bow": {"mat": "red", "tail": "red_dk"},
    "waist_ribbon": "red",
    "skirt": {"len": "short", "mat": "dress", "hem_mat": "dress_hem", "in": "dress_in"},
    "strap": "red",
}

DEEPSEEK = {
    "palette": {
        "s": "#fde3dc", "h": "#34427a", "k": "#1f1b2e", "I": "#3d6bc9", "D": "#1d2c6b", "L": "#8db8f0",
        "w": "#ffffff", "W": "#ffffff", "p": "#f6b9b4", "m": "#b35a5a",
        "a": "#3a4880", "b": "#28325e", "c": "#7f95cf", "e": "#4a5c96", "n": "#2f3258", "G": "#c9a86b",
    },
    "materials": {
        "skin": {"gradient": ["#fde5dc", "#f6d6cc"]},
        "hair": {"gradient": ["#34427a", "#45568f"], "streaks": {"amount": 12}, "hl": {"at": 0.3, "color": "#7f95cf"}},
        "hair_low": {"gradient": ["#3d4d86", "#7ea6d6"], "streaks": {"amount": 12}, "hl": {"at": 0.18, "color": "#8aa2d8"}},
        "hair_in": {"fill": "#252e55"},
        "dress": {"gradient": ["#3f3e66", "#34335a"]},
        "dress_in": {"fill": "#26253f"},
        "skirt": {"gradient": ["#3f3e66", "#35345b"]},
        "skirt_hem": {"gradient": ["#3a3961", "#2f2e52"], "hband": [{"from_bottom": 2, "rows": 1, "color": "#c9a86b"},
                                                                   {"from_bottom": 4, "rows": 1, "color": "#c9a86b", "dots": 2}]},
        "skirt_front": {"fill": "#6d7ead", "vstripes": {"color": "#5b6b9c", "every": 2}},
        "skirt_front_hem": {"fill": "#6d7ead", "vstripes": {"color": "#5b6b9c", "every": 2},
                            "hband": [{"from_bottom": 2, "rows": 1, "color": "#c9a86b"}]},
        "frill": {"fill": "#f6f4f8", "vstripes": {"color": "#d8d3df", "every": 3, "offset": 1}, "scallop": "#cfc8d8"},
        "collar": {"fill": "#ffffff", "frame": "#b6aec0", "frame_all": True},
        "blouse": {"fill": "#f7f5f9", "vstripes": {"color": "#e2dde8", "every": 3, "offset": 1}},
        "sleeve": {"gradient": ["#43426b", "#36355c"], "hband": [{"from_bottom": 0, "rows": 1, "color": "#26253f"}]},
        "sleeve_long": {"gradient": ["#3f3e66", "#35345b"]},
        "cuff": {"fill": "#f7f5f9", "hband": [{"from_bottom": 1, "rows": 1, "color": "#3b3a5f"}]},
        "apron": {"fill": "#fbfafc", "frame": "#cfc8d6", "frame_all": True},
        "black": {"fill": "#1c1c2c"},
        "corset": {"gradient": ["#2f2e52", "#26254a"]},
        "gem": {"fill": "#5fb7e0", "shade": False},
        "white": {"fill": "#ffffff", "shade": False},
        "tail": {"gradient": ["#3f3e68", "#2e2d52"]},
        "tail_under": {"fill": "#b8c6dc"},
        "ear": {"fill": "#2f3258"},
        "ear_under": {"fill": "#b8c6dc"},
        "bow_blue": {"fill": "#5b9bd6"},
        "tights": {"gradient": ["#f6f3f8", "#e6e1ec"]},
        "shoe": {"gradient": ["#3b3b5f", "#2a2a45"], "hband": [{"from_bottom": 0, "rows": 1, "color": "#1c1c2c"}]},
        "iris": {"gradient": ["#1e3a8a", "#5b8fe0"], "shade": False},
        "lash": {"fill": "#1f1b2e", "shade": False},
        "blush": {"fill": "#f6b9b4", "shade": False},
    },
    "decals_extra": {"whale": ["...nn.n", ".nnnnnn", "nnwnnn.", ".nnnnn."],
                     "corset_buttons": ["..G..G..", "........", "..G..G..", "........", "..G..G.."]},
    "eye": {"w": 4, "h": 4},
    "mouth": False,
    "hair": "long",
    "headwear": "maid",
    "hair_bows": "bow_blue",
    "ears": "whale",
    "sleeve": "long",
    "torso_front": "blouse",
    "neck_bow": {"mat": "black", "tail": "black", "gem": "gem"},
    "waist_ribbon": "white",
    "corset": {"mat": "corset", "h": 3.0},
    "skirt": {"len": "long", "mat": "skirt", "hem_mat": "skirt_hem", "front_mat": "skirt_front",
              "front_hem_mat": "skirt_front_hem", "frill": "frill", "in": "dress_in"},
    "apron": "apron",
    "back_bow": "white",
    "tail": True,
    "leg_mat": "tights",
    "strap": "shoe",
    "bust_mat": "blouse",
}

# 初音未来（经典服装），参考 assets/blocky-anime/reference/miku-turnaround.png
MIKU = {
    "palette": {
        "s": "#fde5da", "h": "#3cb9b2", "k": "#1d3a44", "I": "#2a9d9b", "D": "#14605f", "L": "#7fe3da",
        "w": "#ffffff", "W": "#ffffff", "p": "#f7c0b8", "m": "#b35a5a",
        "r": "#d8345f", "t": "#37c9bd", "n": "#24242c", "P": "#e8467e", "Y": "#e9d36a",
    },
    "materials": {
        "skin": {"gradient": ["#fde6dc", "#f6d8cc"]},
        "hair": {"gradient": ["#24958f", "#2ba39b"], "streaks": {"amount": 14}, "hl": {"at": 0.3, "color": "#62cfc4"}},
        "hair_low": {"gradient": ["#289c95", "#34b0a6"], "streaks": {"amount": 14}},
        "hair_in": {"fill": "#1b6c68"},
        "dress": {"gradient": ["#c3c8cf", "#b3b8c1"]},
        "shirt_hem": {"gradient": ["#c0c5cc", "#b3b8c1"], "hband": [{"from_bottom": 0, "rows": 1, "color": "#37c9bd"}]},
        # 一体式腰：上面是衬衫，往下一行青色下摆边、两行黑色裙腰（从下往上数像素）
        "waist_band": {"gradient": ["#c3c8cf", "#b3b8c1"], "hband": [{"from_bottom": 0, "rows": 2, "color": "#2c2c35"},
                                                                     {"from_bottom": 2, "rows": 1, "color": "#37c9bd"}]},
        "collar": {"fill": "#c8cdd4", "frame": "#37c9bd"},
        "tie": {"gradient": ["#37c9bd", "#2bb3a8"]},
        "skirt": {"fill": "#2c2c35", "vstripes": {"color": "#202027", "every": 3, "offset": 1}},
        "skirt_hem": {"fill": "#2c2c35", "vstripes": {"color": "#202027", "every": 3, "offset": 1},
                      "hband": [{"from_bottom": 0, "rows": 2, "color": "#37c9bd"}]},
        "skirt_in": {"fill": "#1c1c22"},
        "dsleeve": {"gradient": ["#33333d", "#2a2a33"]},
        "dsleeve_cuff": {"fill": "#2a2a33", "hband": [{"from_bottom": 0, "rows": 2, "color": "#37c9bd"}]},
        "dsleeve_top": {"gradient": ["#33333d", "#2e2e37"], "tband": [{"from_top": 0, "rows": 1, "color": "#37c9bd"}]},
        "boot": {"gradient": ["#30303a", "#26262e"]},
        "boot_top": {"gradient": ["#30303a", "#2a2a33"], "tband": [{"from_top": 0, "rows": 2, "color": "#37c9bd"}]},
        "boot_sole": {"gradient": ["#37c9bd", "#2bb3a8"]},
        "headset": {"fill": "#26262e"},
        "hair_tie": {"fill": "#26262e", "panel": {"width_frac": 0.34, "color": "#e8467e", "faces": ["north", "south", "east", "west"]}},
        "white": {"fill": "#ffffff", "shade": False},
        "iris": {"gradient": ["#0d3f48", "#46e0d6"], "shade": False},   # 上暗下亮，和发色拉开
        "lash": {"fill": "#121419", "shade": False},
        "blush": {"fill": "#f7c0b8", "shade": False},
    },
    "decals_extra": {
        "tattoo01": ["rrr.r", "r.r.r", "rrr.r"],                  # 左上臂红色「01」
        "sleeve_lights": ["tY", "Pt", "tt", "Yt", "tP", "tt", "tY"],      # 袖子上的彩色灯条
        "headset_light": ["PP", "P.", "PP", "..", "PP"],
    },
    "eye": {"w": 4, "h": 4},
    "mouth": False,
    "hair": "twintail",
    "ahoge": False,
    "side_lock_bot": -3.2,       # 鬓发垂到胸前
    "side_lock_in": 0.25,        # 鬓发只压脸边 0.25（0.55 时脸被挤窄）
    "headset": True,
    "tie": "tie",
    "collar_up": 0.35,           # 领子在脖子根部立起一点，露出脖子
    # "shirt_hem": "shirt_hem",  # 方块下摆：社区模型基本不这么做，改用一体式腰（skirt.band）
    "bang_jag": [1.0, 0.5, 0.3, 0.6, 1.3, 3.0, 1.1, 0.4, 0.6, 0.3, 0.9],   # 中间一缕垂到两眼之间；两端别太长，会盖住脸颊
    "sleeve": "detached",
    "tattoo": "tattoo01",
    "skirt": {"len": "mini", "mat": "skirt", "hem_mat": "skirt_hem", "in": "skirt_in", "band": "waist_band"},
    "boots": {"mat": "boot", "top": "boot_top", "sole": "boot_sole"},
}


# 户山香澄：原版演出服，assets/blocky-anime/reference/kasumi-source.png。
# 三视图为 AI 补全，未见于原画的背面不是官方设定。
KASUMI = {
    "palette": {"s":"#fce3d8","h":"#795047","k":"#302229","I":"#9655b7","D":"#503272","L":"#cfa9ec",
                "w":"#ffffff","W":"#ffffff","p":"#f4b4b2","m":"#b36666","G":"#e6b64d","r":"#be262e"},
    "materials": {
        "skin":{"gradient":["#fce5dc","#f6d9cc"]},
        "hair":{"gradient":["#68433b","#966455"],"streaks":{"amount":9}},
        "hair_low":{"gradient":["#775044","#a27563"],"streaks":{"amount":9}},
        "hair_in":{"fill":"#4b302c"},
        "dress":{"gradient":["#fff9ef","#e7e3df"]},
        "waist_band":{"fill":"#f8f3e9","hband":[{"from_bottom":0,"rows":2,"color":"#302c31"},
                                                            {"from_bottom":2,"rows":1,"color":"#ddb141"}]},
        "collar":{"fill":"#fff8ed","frame":"#dad0ca"},
        "sleeve":{"fill":"#b72934","plaid":{"period":5,"dark":"#812730","light":"#eb852b","line":"#f1c55a"}},
        "skirt":{"fill":"#c3313b","plaid":{"period":6,"dark":"#802c3b","light":"#eb8231","line":"#f0bf4e"}},
        "skirt_hem":{"fill":"#bf2a37","plaid":{"period":6,"dark":"#802c3b","light":"#e87a2f","line":"#f0bf4e"}},
        "skirt_front":{"fill":"#302b31","vstripes":{"color":"#201f27","every":3}},
        "skirt_in":{"fill":"#64252d"},
        "frill":{"fill":"#fff8ef","vstripes":{"color":"#e5dcd6","every":3},"scallop":"#d8ccc7"},
        "red":{"fill":"#bd232e"},"red_dark":{"fill":"#8d1f2a"},
        "gold":{"fill":"#e8bd55","shade":False},
        "yellow":{"fill":"#f0c33b","shade":False},
        "black":{"fill":"#292a30"},
        "sock":{"gradient":["#45454d","#292b33"],"tband":[{"from_top":0,"rows":1,"color":"#d9b052"}]},
        "shoe":{"gradient":["#b51f2b","#841923"],"panel":{"width_frac":0.17,"color":"#e0b453","faces":["north","south"]},
                "hband":[{"from_bottom":0,"rows":1,"color":"#e8c991"}]},
        "white":{"fill":"#fffaf4","shade":False},
        "iris":{"gradient":["#573377","#b68ad7"],"shade":False},
        "lash":{"fill":"#33232b","shade":False},
        "blush":{"fill":"#efb8b6","shade":False}
    },
    "decals_extra":{"star_cut":["-G-","GGG","G-G"],"star_red":["-r-","rrr","r-r"],"star_large":["--G--","GGGGG","-GGG-","-G-G-","G---G"],"boot_edge":["G...G",".G.G.","..G.."]},
    "eye":{"w":4,"h":4},"mouth":False,
    "hair":"bob","hair_shell_style":"box","hair_detail":"reference","bob_drop":2.0,"hair_peaks":True,"star_hairclips":True,
    "ahoge":False,"side_lock_in":0.2,
    "bang_jag":[0.15,0.25,0.65,0.25,0.5,0.9,0.3,0.5],
    "sleeve":"armband","stage_outfit":True,"default_bust":"tri",
    "neck_bow":{"mat":"red","tail":"red_dark","gem":"yellow"},
    "skirt":{"len":"mini","mat":"skirt","hem_mat":"skirt_hem","in":"skirt_in",
             "front_mat":"skirt_front","front_hem_mat":"skirt_front","frill":"frill","band":"waist_band"},
    "strap":"shoe"
}

# 黑魔导女孩（暗黑魔法少女），参考 D:/download/暗黑魔法少女三视图设定稿.png（AI 三视图，非官方设定）。
# 配色从参考图取；尖帽、披肩片、护腕、法杖、开前襟锯齿裙等部件见 scripts/blocky-witch-outfit.py。
DMG = {
    "palette": {"s": "#fde4d8", "h": "#f0cf62", "k": "#3a2a2a", "I": "#2e8f74", "D": "#1c5a49", "L": "#7fd6b4",
                "w": "#ffffff", "W": "#ffffff", "p": "#f4b8b4", "m": "#b36666",
                "P": "#f29cbf", "B": "#2a4aa8", "G": "#e7c24f", "R": "#c4243f"},
    "materials": {
        "skin": {"gradient": ["#fde6dc", "#f6d8cc"]},
        "hair": {"gradient": ["#f1d06a", "#e2b54a"], "streaks": {"amount": 12}, "hl": {"at": 0.3, "color": "#fbe8a0"}},
        "hair_low": {"gradient": ["#ecc75c", "#d9a83e"], "streaks": {"amount": 12}},
        "hair_in": {"fill": "#b8862c"},
        "dress": {"gradient": ["#3156b8", "#26449a"]},
        "bodice": {"gradient": ["#3156b8", "#2c4fae"], "tband": [{"from_top": 0, "rows": 1, "color": "#fde4d8"}]},
        "leotard": {"gradient": ["#3156b8", "#26449a"]},
        # stacked hat rings: no per-face edge darkening, or every ring joint paints a stripe
        "hat": {"fill": "#2b4dad", "shade": {"edge": 0, "top": 0, "noise": 5}},
        "hat_brim": {"fill": "#2a4aa8", "hband": [{"from_bottom": 0, "rows": 1, "color": "#f29cbf"}]},
        "hat_in": {"fill": "#182c66"},
        "pink": {"fill": "#f29cbf"},
        "pink_trim": {"fill": "#ef8fb6", "shade": False},
        "skirt": {"gradient": ["#f6b3cd", "#ee9dbd"], "vstripes": {"color": "#e28aae", "every": 4, "offset": 1}},
        "skirt_hem": {"gradient": ["#f4aac6", "#ec95b8"], "vstripes": {"color": "#de86aa", "every": 4, "offset": 1}},
        "skirt_in": {"fill": "#c8728f"},
        "blue_trim": {"fill": "#2a4aa8", "hband": [{"from_bottom": 0, "rows": 1, "color": "#f29cbf"}],
                      "tband": [{"from_top": 0, "rows": 1, "color": "#f29cbf"}]},
        "flap": {"fill": "#2c4fae", "hband": [{"from_bottom": 0, "rows": 1, "color": "#f29cbf"}]},
        "gold": {"fill": "#e7c24f", "shade": False},
        "gold_metal": {"gradient": ["#f2d36a", "#d1a63a"]},
        "gem": {"gradient": ["#e04a63", "#9c1730"], "shade": False},
        "boot": {"gradient": ["#2f55b6", "#23409a"]},
        "boot_top": {"gradient": ["#2f55b6", "#2a4aa8"], "tband": [{"from_top": 0, "rows": 1, "color": "#f29cbf"}]},
        "boot_sole": {"fill": "#1f3887"},
        "staff": {"gradient": ["#3a62c4", "#2a4aa8"]},
        "white": {"fill": "#ffffff", "shade": False},
        "iris": {"gradient": ["#1d5e4c", "#4fc79d"], "shade": False},
        "lash": {"fill": "#3a2a2a", "shade": False},
        "blush": {"fill": "#f6c2bc", "shade": False},
    },
    "decals_extra": {
        # leotard V panel below the bust: pink outline narrowing to the crotch
        "leotard_v": ["PBBBBBBBBP", ".PBBBBBBP.", "..PBBBBP..", "...PBBP...", "....PP...."],
    },
    "eye": {"w": 4, "h": 4}, "mouth": False,
    "hair": "long", "ahoge": False, "side_lock_bot": -4.5, "side_lock_in": 0.3,
    "bang_jag": [0.6, 1.2, 0.4, 1.6, 0.8, 2.2, 0.5, 1.4, 0.9, 0.3],
    "collar": False, "neck_bow": None, "sleeve": "none", "default_bust": "tri",
    "bust_mat": "dress", "chest_mat": "bodice",
    "waist_front": {"mat": "leotard", "decal": "leotard_v", "at": ["center", -1]},
    "skirt": {"len": "thigh", "mat": "skirt", "hem_mat": "skirt_hem", "in": "skirt_in"},
    "skirt_open_front": 26, "skirt_jag": [1.6, 0.4, 2.3, 0.9, 1.9, 0.2, 2.6, 1.2],
    "boots": {"mat": "boot", "top": "boot_top", "sole": "boot_sole"},
    "witch_hat": {"mat": "hat", "in": "hat_in", "brim": "hat_brim", "band": "pink_trim", "gem": "gem",
                  "gem_rim": "gold", "height": 1.2, "tip_back": 0.5},
    "off_shoulder": {"mat": "blue_trim", "flap": "flap", "in": "hat_in"},
    "bracers": {"mat": "blue_trim", "trim": "pink_trim", "gem": "gem"},
    "choker": {"mat": "dress", "gem": "gem"},
    "belt": {"mat": "gold_metal"},
    "boot_gems": {"gem": "gem", "rim": "gold", "band": "pink_trim"},
    "staff": {"shaft": "staff", "metal": "gold_metal", "ring": "pink_trim", "hand": "Right"},
    # Jenny-mod body (scripts/blocky-jenny-dress.py): the bust and arms sit where the template's side
    # strands hang, so those are off and the side locks stop at the shoulder; leotard is painted on.
    "jenny_overrides": {"side_strands": False, "side_lock_bot": -2.0,
                        "bang_jag": [0.2, 0.5, 0.15, 0.6, 0.3, 0.8, 0.2, 0.55, 0.35, 0.1]},   # Jenny eyes sit high: short points
    "jenny_leotard": (44, 76, 170, 255), "bodice_line": 0.72,
}


CHARS = {"kurumi": KURUMI, "deepseek": DEEPSEEK, "miku": MIKU, "kasumi": KASUMI, "dmg": DMG}

PRESETS = {
    # hair_shell：头发圆顶比头骨外扩多少。珍妮系实测（JennyMod Jenny / Bia）头连头发宽 / 总高 0.29–0.34；
    # 外扩 0.95 时初音是 0.350，头显大、身子显细 → 0.6
    "jenny": {"head": 8.0, "head_d": 7.0, "head_y": 24.0, "texel": 2, "eyes": "jenny", "body": "jenny",
              "hair_shell": 0.6, "hair_flare": 0.05, "hair_thick": 0.5},   # 头宽 / 头高 ≈ 1（Jenny 参考 9.5 / 9.5）
    "ysm": {"head": 7.0, "head_y": 32.0, "texel": 2, "pixel_eyes": True, "body": "ysm"},
    # Q 版：GPT 做的 DS 娘实测（data/blocky-ref/ds-whale-ref.bbmodel）——下巴 27.75、腿长 16.9、约 4 头身，
    # 虹膜 1.6×1.65、眼睛中心在下巴上方约 1.9。身体沿用 ysm 的实测宽度，高度整体压到下巴 27.75。
    "chibi": {"head": 7.0, "head_y": 32.0, "texel": 2, "eyes": "gpt", "body": "ysm", "squash_to": 27.75},
}

# 方块眼尺寸（相对下巴 hy0；X 为离中线距离）
EYES = {
    "jenny": {  # 珍妮 mod 实测：眼白 2.5×1、虹膜 1.5×1.5 凸出 0.35
        "white": (1.0, 3.5, 1.5, 2.55), "iris": (1.0, 2.5, 1.3, 2.8), "glint": (1.1, 1.7, 2.15, 2.65),
        "lash": (0.9, 3.6, 2.55, 3.05), "lash_out": (3.5, 4.0, 2.05, 2.6), "blush": (1.1, 3.4, 0.95, 1.3)},
    "jenny_big": {  # 放大版（2026-10-11 第一版，用户认为可作备选）
        "white": (0.75, 3.7, 1.25, 2.8), "iris": (0.85, 2.75, 1.05, 3.0), "glint": (0.95, 1.65, 2.25, 2.85),
        "lash": (0.65, 3.85, 2.8, 3.35), "lash_out": (3.65, 4.15, 2.25, 2.9), "blush": (1.0, 3.5, 0.7, 1.0)},
    "ysm": {  # 社区二次元 YSM 中位数（头骨高 S=7 为单位）：单眼宽 0.21S、高 0.26S、两眼内间距 0.44S、中心 0.29S
        "white": (1.55, 3.05, 1.25, 2.6), "iris": (1.6, 3.0, 1.1, 2.75), "glint": (1.75, 2.2, 2.2, 2.6),
        "lash": (1.45, 3.15, 2.75, 3.1), "lash_out": (3.05, 3.45, 2.4, 2.9), "blush": (1.6, 3.1, 0.65, 0.95)},
    "gpt": {  # GPT 版 DS 娘实测：虹膜 1.6×1.65，中心在下巴上方 1.9
        "white": (0.95, 3.25, 1.25, 2.5), "iris": (1.23, 2.85, 1.08, 2.73), "glint": (1.35, 1.8, 2.2, 2.6),
        "lash": (0.85, 3.4, 2.6, 3.0), "lash_out": (3.25, 3.65, 2.25, 2.7), "blush": (1.0, 3.0, 0.7, 1.0)},
}

# 身体参照（来自 body_jenny / body_ysm 的实测尺寸），服装部件按它挂
BODY = {
    "jenny": {"chest_top": 23.0, "half_w": 3.0, "half_d": 2.0, "bow_y": 22.9, "ribbon": (20.2, 20.8, 2.62, 2.45),   # 腰带系在裙腰外面，要比裙上圈深
              # 躯干深 4 以后裙圈跟着加深（原来的浅裙圈让腿外侧斜条顶出裙摆）
              "skirt_short": (((0, 0), 2.65, 2.25, 20.4), ((0, 0.1), 4.2, 3.25, 14.6), ((0, 0.2), 5.2, 3.95, 9.2)),
              "skirt_long": (((0, 0), 2.65, 2.25, 20.4), ((0, 0.15), 4.3, 3.4, 13.0), ((0, 0.3), 5.4, 4.2, 6.0)),  # MC 长裙比原设短，到小腿中部
              "skirt_mini": (((0, 0), 2.8, 2.25, 16.8), ((0, 0.15), 4.3, 3.7, 14.6), ((0, 0.25), 4.9, 4.2, 12.4)),
              # to mid-thigh (waist 17 → hem 10.4; Dark Magician Girl turnaround, scaled to the jenny body)
              "skirt_thigh": (((0, 0), 2.8, 2.25, 17.0), ((0, 0.15), 4.4, 3.8, 13.8), ((0, 0.25), 5.3, 4.4, 10.6)),
              "boot_top": 9.0, "twintail_end": 1.8, "waist": (2.5, 2.0), "twintail_scale": 0.78, "neck_gap": 1.0,   # JennyMod 实测：躯干顶 23、下巴 24，中间一节 2×1 的脖子
              "bust": (22.6, -2.0), "apron_bot": 9.5, "hair_long_end": 11.0, "back_bow_y": 19.8,
              "tail": [(0, 15.5, 1.6), (0, 10.5, 4.4), (0, 5.5, 5.3), (0, 1.4, 6.1)], "tail_w": 3.0},  # 沿裙后垂到地（原画 / GPT 版背面）
    "ysm": {"chest_top": 31.0, "half_w": 3.7, "half_d": 2.0, "bow_y": 30.1, "ribbon": (25.6, 26.2, 3.22, 1.62),
            "skirt_short": (((0, 0), 3.3, 1.95, 25.7), ((0, 0.1), 4.7, 3.1, 20.4), ((0, 0.25), 5.7, 4.1, 14.6)),
            "skirt_long": (((0, 0), 3.3, 1.95, 25.7), ((0, 0.15), 4.9, 3.4, 17.0), ((0, 0.3), 6.0, 4.5, 8.0)),
            # 迷你百褶裙（初音参考图实测：裙腰约 22、下摆约 18）。上圈藏在衣摆方块里；腰盒在裙子里那截由 fit_under_skirt 收进去。
            # 超椭圆上圈试过：正面那段板太稀，露缝
            "skirt_mini": (((0, 0), 2.75, 1.7, 22.3), ((0, 0.3), 5.0, 4.0, 20.4), ((0, 0.4), 5.5, 4.4, 17.9)),
            "skirt_thigh": (((0, 0), 2.75, 1.7, 22.3), ((0, 0.3), 5.1, 4.1, 19.0), ((0, 0.4), 5.9, 4.7, 15.6)),
            "boot_top": 15.8, "twintail_end": 3.0, "waist": (2.45, 1.5), "twintail_scale": 1.0, "neck_gap": 1.0,
            "bust": (30.0, -2.0), "apron_bot": 12.5, "hair_long_end": 18.0, "back_bow_y": 25.0,
            "tail": [(0, 21.0, 2.2), (0, 14.0, 5.4), (0, 7.0, 6.6), (0, 1.6, 7.6)], "tail_w": 3.6},
}

# tri：底面固定（宽 = BUST m 宽，高 TRI_BASE_H），尺码 = (突出深度, 转折点在底面里的高度比例：越小越下垂)
TRI_BASE_H = 5.0          # 底面高（珍妮 S=8 → 0.62 S）；原来 2.8 只有参考的一半
TRI_BASE_W = {"jenny": 6.0, "ysm": 7.4}   # 底面宽：整片胸口（珍妮躯干 5 + 两侧斜板）
# s = 平胸（小胸做成三角会像一根刺）。乳尖张角必须 ≥ 90°：突出 ≤ √(上斜面高 × 下斜面高)，底面高 2.8 时最大 1.4；
# 张角是锐角时，有厚度的斜板端面会从另一面戳出来（l 原来 1.6 / 0.27 → 77°，领带撞上这个凸角）
TRI = {"s": None, "m": (1.6, 0.42), "l": (2.35, 0.38)}   # 突出 0.20 / 0.29 S（珍妮组 0.19–0.43）

BUST = {  # 宽、高、凸出深度（jenny 尺度；ysm 宽度 ×1.25）
    "s": (4.4, 2.2, 0.7), "m": (5.0, 2.7, 1.2), "l": (5.6, 3.2, 1.8),
}


# ---------------- 像素脸 ----------------
def face_rows(W, H, eye, mouth, draw_eyes=True):
    """W×H 像素；眼睛中心 = 从下往上 0.29H；上方画刘海底色（被 3D 刘海挡住的部分）。"""
    ew, eh = eye["w"], eye["h"]
    cy = H - 0.29 * H
    top = int(round(cy - eh / 2))
    gap = 4 if W >= 16 else 2
    if 2 * ew + gap > W - 2:
        gap = max(1, W - 2 - 2 * ew)
    x0 = (W - 2 * ew - gap) // 2
    xs = [x0, x0 + ew + gap]
    g = [["s"] * W for _ in range(H)]
    for y in range(0, max(0, top - 1)):
        for x in range(W):
            g[y][x] = "h"
    art = {5: ["kkkkk", "IwDDI", "IwDDI", "IDDLI", "WLLLW"], 4: ["kkkk", "IwDI", "IDDI", "WLLW"],
           3: ["kkk", "wDI", "DDI", "LLW"]}[ew]
    for i, ex in enumerate(xs if draw_eyes else []):
        for r, row in enumerate(art[:eh]):
            for c, ch in enumerate(row):
                g[top + r][ex + c] = ch
        flick = ex - 1 if i == 0 else ex + ew
        if 0 <= flick < W:
            g[top][flick] = "k"
        by = top + eh + 1
        bx = [ex, ex + 1] if i == 0 else [ex + ew - 2, ex + ew - 1]
        if by < H:
            for x in bx:
                g[by][x] = "p"
    if mouth:
        my = H - 2
        g[my][W // 2 - 1] = g[my][W // 2] = "m"
    return ["".join(r) for r in g]


def bangs_rows(W, H):
    """刘海板正面：渐变底 + 发束暗线 + 一行高光；下沿锯齿（'-' 透明）。"""
    jag = [0, 1, 2, 1, 0, 2, 3, 1, 0, 1, 3, 2, 0, 1, 2, 0]
    rows = []
    for y in range(H):
        r = []
        for x in range(W):
            j = jag[x % len(jag)]
            if y >= H - j:
                r.append("-")
            elif y == 2 and x % 7 in (2, 3):
                r.append("c")
            elif (x * 5) % 7 in (1, 4):
                r.append("b")
            else:
                r.append("a" if y < H // 2 else "e")
        rows.append("".join(r))
    return rows


def sx(s, a, b):
    return sorted([s * a, s * b])


# ---------------- 头和头发 ----------------
def head_parts(k, C, P, decals):
    if C.get("hair_shell_style") == "box":
        return _OPTIONAL["hair"].add_parts(k, C, P, decals)
    hs, d = P["head"], P.get("head_d", P["head"]) / 2
    h, hy0 = hs / 2, P["head_y"]
    hy1 = hy0 + hs
    # 头骨：前半（带脸）全宽，后半收窄——这样头骨的角不会从圆形头发里戳出来
    face_d = min(2 * d - 1.0, 2.6)
    k.box("head", "Head", [-h, hy0, -d], [h, hy1 - 0.8, -d + face_d], "hair",
          faces={"north": {"mat": "skin", "decal": "face"}, "down": "skin"})
    k.box("head_back", "Head", [-h * 0.7, hy0 + 0.3, -d + face_d - 0.1], [h * 0.7, hy1 - 1.0, d - 0.3], "hair")
    tone = lambda i: ("hair", "hair_v1", "hair_v2")[(i * 7 + 3) % 3]
    tone_low = lambda i: ("hair_low", "hair_low_v1", "hair_low_v2")[(i * 5 + 1) % 3]
    jit = lambda i, a: a * math.sin(i * 12.9898 + 1.7)
    # 头发外壳：椭球圆顶（头顶小块 + 4 圈斜板）+ 一圈垂帘；正面额头以下留给刘海和脸
    sh_ = P.get("hair_shell", 0.95)
    R_x, R_z = h + sh_, d + sh_
    cz = 0.15
    y_top = hy1 + 0.75
    H = hs * 0.3                                    # 圆顶竖向半轴：头顶到「赤道」
    y_eq = y_top - H
    k.box("hair_crown_cap", "Hair", [-1.3, y_top - 0.55, cz - 1.3], [1.3, y_top + 0.05, cz + 1.3], "hair")
    lv = [(14, 8), (40, 14), (64, 18), (88, 22)]   # (纬度角°, 片数)
    prev = 14
    for li, (th, n) in enumerate(lv[1:], 1):
        t0, t1 = math.radians(lv[li - 1][0]), math.radians(th)
        for i in range(n):
            phi = 360.0 * (i + 0.5 * (li % 2)) / n
            front = (phi % 360) <= 48 or (phi % 360) >= 312
            if front and th >= 88:
                continue                            # 额头以下正面交给刘海
            top = Kit.ellipse_point((0, cz), R_x * math.sin(t0), R_z * math.sin(t0), phi, y_top - H * (1 - math.cos(t0)))
            bot = Kit.ellipse_point((0, cz), R_x * math.sin(t1), R_z * math.sin(t1), phi, y_top - H * (1 - math.cos(t1)))
            nrm = Kit.ellipse_normal(R_x, R_z, phi)
            w = 2 * math.pi * max(R_x, R_z) * math.sin(t1) / n * 1.45
            k.slab("hair_dome", "Hair", top, bot, w, 0.65, tone(i + li), outward=nrm, faces={"south": "hair_in"})
    # 垂帘：赤道往下一圈，下沿略外张，给两颊和后脑的体积
    n = 20
    for i in range(n):
        phi = 360.0 * (i + 0.5) / n
        if (phi % 360) <= 50 or (phi % 360) >= 310:
            continue
        top = Kit.ellipse_point((0, cz), R_x - 0.05, R_z - 0.05, phi, y_eq + 0.4)
        fl = P.get("hair_flare", 0.35)               # 垂帘下沿外张
        bot = Kit.ellipse_point((0, cz + 0.1), R_x + fl + jit(i, 0.12), R_z + fl, phi, hy0 + 1.0 + jit(i + 2, 0.4))
        nrm = Kit.ellipse_normal(R_x, R_z, phi)
        k.slab("hair_curtain", "Hair", top, bot, 2 * math.pi * R_x / n * 1.4, P.get("hair_thick", 0.7), tone(i + 1), outward=nrm,
               faces={"south": "hair_in"})
    o = 0.45
    for s in (1, -1):
        x0, x1 = sx(s, h - C.get("side_lock_in", 1.0), h + 0.45)
        lock_bot = hy0 + C["side_lock_bot"] if "side_lock_bot" in C else hy0 - 0.8 if C["hair"] == "bob" else hy0 - hs * 0.55
        k.box("side_lock", "Hair", [x0, lock_bot, -d - 0.55], [x1, hy0 + hs * 0.62, -d + 0.7], "hair_low",
              faces={"south": "hair_in"})
    if C["hair"] == "bob":
        # 波波头：一圈两段式发束（上段外鼓、下段内收），正面留给刘海和鬓发
        n = 13
        for i in range(n):
            phi = 58 + 244 * (i + 0.5) / n
            back = max(0.0, -math.cos(math.radians(phi))) ** 4
            top = Kit.ellipse_point((0, 0.2), h + 0.3, d + 0.3, phi, hy1 - 1.0)
            mid = Kit.ellipse_point((0, 0.3), h + 1.15 + jit(i, 0.15), d + 1.1, phi, hy0 + 2.4)
            bot = Kit.ellipse_point((0, 0.3), h + 0.75, d + 0.75, phi, hy0 - 0.5 + 0.7 * back + jit(i, 0.3))
            nrm = Kit.ellipse_normal(h + 1.1, d + 1.1, phi)
            w = 2 * math.pi * (h + 1.0) * (244 / 360) / n * 1.45
            k.slab("bob_up", "Hair", top, mid, w, 0.8, tone(i), outward=nrm, faces={"south": "hair_in"})
            k.slab("bob_low", "Hair", mid, bot, w * 0.9, 0.75, tone_low(i), outward=nrm,
                   faces={"south": "hair_in", "down": "hair_in"})
    elif C["hair"] == "twintail":
        k.box("hair_nape", "Hair", [-h * 0.9, hy0 - 0.4, d - 0.9], [h * 0.9, hy0 + 2.4, d + 0.75], "hair_low",
              faces={"down": "hair_in"})
        twintails(k, C, h, d, hy0, hy1, tone, tone_low, jit)
    else:
        # 长发：后背两层发束（外层长、内层短而暗），每束长短 / 宽窄 / 外张都错开，发尾外翻
        end = BODY_CUR["hair_long_end"]
        k.box("hair_long_up", "Hair", [-h, hy0 - 1.0, d - 0.4], [h, hy0 + 1.4, d + 0.9], "hair")
        n = 7
        for i in range(n):
            x = (-1 + 2 * (i + 0.5) / n) * (h + 0.7)
            L = end + jit(i, 1.8)
            top = [x * 0.9, hy0 + 2.2, d + 0.8 + abs(jit(i + 5, 0.3))]
            bot = [x * 1.3 + jit(i + 3, 0.4), L, d + 1.3 + abs(jit(i, 1.1))]
            w = 2 * (h + 0.9) / n * 1.4
            k.slab("hair_back_strand", "Hair", top, bot, w, 0.85, tone_low(i), outward=[x * 0.08, 1],
                   faces={"south": "hair_in"})
            # 发尾：向外翻一小段，颜色更浅
            curl = 0.9 if x >= 0 else -0.9
            k.slab("hair_back_tip", "Hair", bot, [bot[0] + curl, L - 1.4, bot[2] + 0.9], w * 0.7, 0.6, "hair_low_v2",
                   outward=[curl * 0.3, 1])
        for i in range(n - 1):
            x = (-1 + 2 * (i + 1) / n) * (h + 0.3)
            top = [x * 0.9, hy0 + 1.8, d + 0.4]
            bot = [x * 1.05, end + 2.2 + jit(i, 0.8), d + 1.0]
            k.slab("hair_back_inner", "Hair", top, bot, 2 * (h + 0.4) / n * 1.5, 0.7, "hair_v1", outward=[0, 1])
        for s in (1, -1) if C.get("side_strands", True) else ():
            # 两侧：肩前一束、肩后一束，垂到胸下（身体在肩前 / 肩上很宽时可关掉，避免穿进胸和手臂）
            for j, (zt, zb, dx) in enumerate([(-0.4, -0.9, 1.0), (1.4, 2.0, 1.6)]):
                top = [s * (h + 0.5), hy0 + 2.4, zt]
                bot = [s * (h + dx), end + 3.0 + jit(j + (s > 0) * 2, 0.8), zb]
                k.slab("hair_side_strand", "Hair", top, bot, 2.0, 0.8, tone_low(j + 2 * (s > 0)), outward=[s, 0],
                       faces={"south": "hair_in"})
                k.slab("hair_side_tip", "Hair", bot, [bot[0] + s * 0.9, bot[1] - 1.3, bot[2] + 0.3], 1.3, 0.6,
                       "hair_low_v2", outward=[s, 0])
    if P.get("bang_h"):
        # caller measured the eyes (e.g. a Jenny-mod reference face): bangs stop above the brows
        bh = P["bang_h"]
        tips = [(-0.5, 0.3), (1.6, 0.2), (-2.3, 0.15)]
    elif P.get("eyes") == "gpt" or (P.get("eyes") and P.get("pixel_eyes")):
        bh = (hy1 + 0.3) - (hy0 + EYES[P["eyes"]]["lash"][3] + 0.25)
        tips = [(-0.5, 0.3), (1.6, 0.2), (-2.3, 0.15)]
    elif P.get("pixel_eyes"):
        # 刘海下沿停在像素眼上沿上方 0.2（眼睛行号与 face_rows 一致）
        H = hs * P["texel"]
        eye_top = int(round(H - 0.29 * H - 5 / 2))
        bh = (hy1 + 0.3) - (hy1 - eye_top / P["texel"] + 0.2)
        tips = [(-0.5, 0.25), (1.6, 0.15), (-2.3, 0.1)]
    else:
        bh = hs * 0.56
        tips = [(-0.5, 0.65), (1.9, 0.45), (-2.6, 0.35)]
    # 刘海：一排发束，从圆顶前沿接下来顺着脸前弧线排开，长短错开成锯齿下沿（不用平板，平板和圆顶之间会露缝）
    y_b = hy1 + 0.3 - bh                              # 刘海下沿基准（在眼睛上方）
    t64 = math.radians(64)
    jag = C.get("bang_jag", [0.15, 0.75, 0.3, 0.95, 0.1, 0.85, 0.35, 0.7, 0.2])
    nb = len(jag)
    for i, jg in enumerate(jag):
        phi = -54 + 108 * (i + 0.5) / nb
        top = Kit.ellipse_point((0, cz), R_x * math.sin(t64) - 0.15, R_z * math.sin(t64) - 0.15, phi,
                                y_top - H * (1 - math.cos(t64)) + 0.2)
        bot = Kit.ellipse_point((0, cz), h + 0.3, d + 0.62, phi, y_b - jg * 0.6 + 0.3)
        nrm = Kit.ellipse_normal(R_x, R_z, phi)
        w = 2 * math.pi * R_z * 108 / 360 / nb * 1.45
        k.slab("bang", "Hair", top, bot, w, 0.55, tone(i), outward=nrm, faces={"south": "hair_in", "down": "hair_in"})
    if C.get("ahoge", True):
        k.box("ahoge", "Hair", [-0.2, hy1 + 0.5, -0.5], [0.3, hy1 + 1.9, 0], "hair", rotation=[0, 0, -20], origin=[0, hy1 + 0.6, 0])
        k.box("ahoge", "Hair", [0.3, hy1 + 1.5, -0.5], [1.3, hy1 + 1.9, 0], "hair", rotation=[0, 0, -40], origin=[0.3, hy1 + 1.7, 0])
    if C.get("headset"):
        # 耳机：耳朵高度的扁盒，一半埋进垂帘（戴在头发下面），外侧一条粉色灯
        # 位置不手摆：先贴头放，和头发相交就每次往外挪 0.1，直到不碰（耳机戴在头发外面）
        hair_pre = ("hair_", "side_lock", "bang", "twintail")
        for s in (1, -1):
            side = "east" if s > 0 else "west"
            cy, cz_ = hy0 + 2.9, 0.2
            for k_off in range(40):
                x0, x1 = sx(s, h + 0.65 + 0.1 * k_off, h + 1.5 + 0.1 * k_off)
                c1 = k.box("headset", "Head", [x0, cy - 1.5, cz_ - 0.9], [x1, cy + 1.5, cz_ + 0.9], "headset",
                           faces={side: {"mat": "headset", "decal": "headset_light"}})
                c2 = k.box("headset", "Head", [x0, cy - 0.9, cz_ - 1.5], [x1, cy + 0.9, cz_ + 1.5], "headset")
                B_ = CLIP.obbs(k.spec({}), 0.03)
                hit = any(CLIP.sat(B_[c["name"]], B_[n]) for c in (c1, c2) for n in B_ if n.startswith(hair_pre))
                if not hit:
                    break
                k.cubes.remove(c1)
                k.cubes.remove(c2)
                k._names["headset"] -= 2
            # 麦克风杆试过：这个尺度下只剩脸上一个黑点（像痣），不做
    if C.get("hairclip"):
        k.box("hairclip", "Hair", [-h + 0.6, hy1 - 2.0, -d - 0.75], [-h + 2.0, hy1 - 1.6, -d - 0.5], "white",
              rotation=[0, 0, 15], origin=[-h + 1.3, hy1 - 1.8, -d - 0.6])
    if C.get("headwear") == "maid":
        # 女仆头饰：横过头顶的白带 + 前沿一排荷叶 + 两侧垂到耳上
        k.box("maid_band", "Hair", [-h - 0.6, hy1 - 0.1, -1.2], [h + 0.6, hy1 + 0.65, 0.3], "white")
        k.box("maid_frill", "Hair", [-h - 0.3, hy1 - 0.2, -1.5], [h + 0.3, hy1 + 1.05, -1.2], "frill")
        for i in range(5):
            x = -h + 0.6 + i * (2 * h - 1.2) / 4
            k.box("maid_frill_top", "Hair", [x - 0.55, hy1 + 0.6, -1.15], [x + 0.55, hy1 + 1.25, 0.15], "frill")
        for s in (1, -1):
            x0, x1 = sx(s, h + 0.95, h + 1.25)
            k.box("maid_side", "Hair", [x0, hy0 + 3.6, -1.2], [x1, hy1 - 0.3, 0.3], "white")
    if C.get("hair_bows"):
        for s in (1, -1):
            x0, x1 = sx(s, h + 1.0, h + 1.55)
            k.box("hair_bow", "Hair", [x0, hy0 + 4.4, -1.6], [x1, hy0 + 5.3, -0.3], C["hair_bows"])
    if C.get("ears") == "whale":
        for s in (1, -1):
            side = "Right" if s > 0 else "Left"
            k.group(f"{side}Ear", "Head", (s * (h + 0.3), hy0 + 3.6, 0.6), (0, 0, -20 * s))
            x0, x1 = sx(s, h + 0.2, h + 2.6)
            k.box(f"ear_{side[0]}", f"{side}Ear", [x0, hy0 + 3.05, -1.0], [x1, hy0 + 4.15, 2.3], "ear",
                  faces={"down": "ear_under"})
            # 鳍尖分两片：一片朝外后、一片朝外前，像原画的鲸鳍
            x0, x1 = sx(s, h + 2.3, h + 4.0)
            k.box(f"ear_lobe_{side[0]}", f"{side}Ear", [x0, hy0 + 3.15, 0.6], [x1, hy0 + 3.95, 2.8], "ear",
                  faces={"down": "ear_under"}, rotation=[0, -12 * s, 0], origin=[s * (h + 2.4), hy0 + 3.5, 1.5])
            k.box(f"ear_lobe2_{side[0]}", f"{side}Ear", [x0, hy0 + 3.2, -1.1], [x1, hy0 + 3.9, 0.7], "ear",
                  faces={"down": "ear_under"}, rotation=[0, 14 * s, 0], origin=[s * (h + 2.4), hy0 + 3.5, -0.2])


def twintails(k, C, h, d, hy0, hy1, tone, tone_low, jit):
    """双马尾（按设定表）：发根在后脑上方两侧、很细，先往外后方甩出，再垂到脚踝附近，中段最宽。
    中心线上几段梁 = 主体 + 内外两侧错开长短的细发束 + 底端发尖。整条挂在身体后方（z > 手臂），手臂不会插进去。
    发饰：发根处一根竖长的黑条（内侧粉色灯），往外倾。"""
    end = BODY_CUR["twintail_end"]
    sc = BODY_CUR["twintail_scale"]               # 按身高缩放（尺寸按 ysm 41 高定的）
    hd = BODY_CUR["half_d"]                        # 下垂段挂在身体后面，按身体厚度走
    top_y = hy1 - 5.0
    for s in (1, -1):
        side = "Right" if s > 0 else "Left"
        g = f"{side}Twintail"
        root = [s * (h - 0.7), hy1 + 0.1, d - 1.0]
        k.group(g, "Hair", tuple(root))
        ys = [root[1], hy1 - 1.4, top_y] + [top_y + (end + 1.2 - top_y) * t for t in (0.35, 0.75, 1.0)]
        xs = [h - 0.7] + [h + v * sc for v in (0.9, 1.9, 2.5, 2.6, 2.3)]
        zs = [root[2], d + 0.3, d + 1.0, hd + 3.0, hd + 3.2, hd + 2.9]
        ws = [v * sc for v in (1.3, 2.1, 3.0, 3.8, 3.7, 2.9)]
        ts = [v * sc for v in (1.3, 1.9, 2.5, 2.8, 2.7, 2.2)]
        pts = [[s * x, y, z] for x, y, z in zip(xs, ys, zs)]
        for i in range(len(pts) - 1):
            a_, b_ = pts[i], pts[i + 1]
            w, t = (ws[i] + ws[i + 1]) / 2, (ts[i] + ts[i + 1]) / 2
            k.beam("twintail", g, a_, b_, w, t, tone_low(i) if i > 1 else tone(i), facing=(0, 0, 1),
                   faces={"up": "hair_in", "down": "hair_in"}, ext=0.5)
            if i >= 2:
                # 两侧发束：比主体略薄、长短错开，打破直筒轮廓
                for e, sgn in ((0, 1), (1, -1)):
                    off = s * sgn * (w / 2 - 0.3)
                    a2 = [a_[0] + off, a_[1] - 0.4 + jit(i + e, 0.5), a_[2] + 0.2]
                    b2 = [b_[0] + off * 1.08, b_[1] + jit(i * 3 + e, 0.9), b_[2] + 0.1]
                    k.beam("twintail_strand", g, a2, b2, 1.2 * sc, t * 0.8, tone(i + e + 1), facing=(0, 0, 1),
                           faces={"up": "hair_in", "down": "hair_in"}, ext=0.3)
        # 发尖：底端 5 束，宽窄 / 长短错开，往中间收成尖
        b_ = pts[-1]
        for j in range(5):
            u = -1 + 2 * (j + 0.5) / 5
            a2 = [b_[0] + u * ws[-1] * 0.38, b_[1] + 0.8, b_[2] + u * 0.3]
            L = (2.0 + 1.6 * abs(math.cos(j * 2.1)) - 0.9 * abs(u)) * sc
            b2 = [b_[0] + u * ws[-1] * 0.15, b_[1] - L, b_[2] + 0.2]
            k.beam("twintail_tip", g, a2, b2, 1.0 * sc, ts[-1] * (0.7 - 0.15 * abs(u)), tone_low(j + 2),
                   facing=(0, 0, 1), faces={"up": "hair_in"})
        # 发饰：竖长黑条，下半埋进发根，往外后方倾
        x0, x1 = sx(s, h - 1.45, h + 0.05)
        k.box("hair_tie", g, [x0, hy1 - 1.6, d - 2.2], [x1, hy1 + 1.9, d + 0.1], "hair_tie",
              rotation=[-10, 0, -12 * s], origin=root)


# ---------------- 服装 ----------------
def collar_and_bow(k, C, B):
    """圆领（白底描边的薄板，正面两片翻领）+ 领口蝴蝶结（可带宝石）。"""
    U = "UpperBody"
    top, half_w, half_d = B["chest_top"], B["half_w"], B["half_d"]
    front_z = -half_d
    ct = top + min(C.get("collar_up", 0.25), max(B["neck_gap"], 0.25))
    if C.get("collar", True):   # off-shoulder / strapless outfits have no collar
        k.box("collar_back", U, [-half_w - 0.15, top - 1.1, half_d - 0.5], [half_w + 0.15, ct, half_d + 0.3], "collar")
        for s in (1, -1):
            x0, x1 = sx(s, half_w - 0.7, half_w + 0.2)
            k.box("collar_side", U, [x0, top - 1.1, -half_d - 0.25], [x1, ct, half_d + 0.3], "collar")
            x0, x1 = sx(s, 0.3, half_w - 0.35)
            k.box("collar_front", U, [x0, top - 1.5, front_z - 0.3], [x1, ct, front_z - 0.05], "collar",
                  rotation=[0, 0, -9 * s], origin=[s * 0.3, ct, front_z])
    if C.get("tie"):
        # 领带：领口一个结 + 一条沿胸前斜下来的带子，下端到胸下
        m = C["tie"]
        B["tie_pending"] = (m, top - 1.5, B.get("tie_end", top - 7.3), top)   # 带子等胸部建完再挂（照胸部折线贴）
        return
    nb = C.get("neck_bow")
    if not nb:
        return
    by = B["bow_y"] - 0.4
    k.box("bow_knot", U, [-0.3, by - 0.3, front_z - 0.55], [0.3, by + 0.3, front_z - 0.2], nb["mat"])
    for s in (1, -1):
        x0, x1 = sx(s, 0.25, 1.15)
        k.box("bow_loop", U, [x0, by - 0.38, front_z - 0.45], [x1, by + 0.42, front_z - 0.22], nb["mat"],
              rotation=[0, 0, -12 * s], origin=[s * 0.3, by, front_z])
        x0, x1 = sx(s, 0.06, 0.42)
        k.box("bow_tail", U, [x0, by - 1.5, front_z - 0.4], [x1, by - 0.2, front_z - 0.28], nb["tail"],
              rotation=[0, 0, -8 * s], origin=[s * 0.25, by - 0.2, front_z])
    if nb.get("gem"):
        k.box("bow_gem", U, [-0.2, by - 0.2, front_z - 0.66], [0.2, by + 0.2, front_z - 0.5], nb["gem"])


def front_profile(k, names, x_half, y):
    """y 高度处、|x| < x_half 范围内这些方块最靠前（最小 z）的表面。方块按世界坐标 8 个角投到 yz 平面，
    凸包边界上的最小 z = 所有角两两连线里跨过 y 的那些线段在 y 处 z 的最小值。"""
    B_ = CLIP.obbs(k.spec({}), 0.0)
    best = None
    for n, (c, R, h) in B_.items():
        if not n.startswith(names):
            continue
        P = [c + R @ (h * [sx_, sy_, sz_]) for sx_ in (-1, 1) for sy_ in (-1, 1) for sz_ in (-1, 1)]
        if min(p[0] for p in P) > x_half or max(p[0] for p in P) < -x_half:
            continue
        for i in range(8):
            for j in range(i + 1, 8):
                (y0, z0), (y1, z1) = (P[i][1], P[i][2]), (P[j][1], P[j][2])
                if min(y0, y1) <= y <= max(y0, y1):
                    z = z0 if abs(y1 - y0) < 1e-6 else z0 + (z1 - z0) * (y - y0) / (y1 - y0)
                    best = z if best is None else min(best, z)
    return best


def tie_strip(k, C, B):
    """领带：领结 → 胸口 → 照胸部的折线（上斜面、过渡面）贴着走 → 从过渡面下沿竖直垂到下摆边。
    每段前表面离胸部 0.02，块数 = 胸部折线段数 + 2，不采样、不往外推。
    之前逐点采样贴轮廓、切进去就往前推 0.1，碎成六七段还一级级鼓出来，在两胸之间像一道棱。
    没有胸（或非 tri）时：领结下一块竖直贴着胸口。"""
    m, y0, end, top = B["tie_pending"]
    zc = -B["half_d"]                                      # 胸口前表面
    gap, th = 0.03, 0.2
    # 领结：小、薄，放在领口下（珍妮身体胸口顶 = 下巴，领结贴着下巴会像喉咙肿）
    k.box("tie_knot", "UpperBody", [-0.45, top - 0.85, zc - 0.32], [0.45, top + 0.05, zc - 0.02], m)
    path = [(top - 0.75, zc)]
    for y, z in (B.get("bust_center") or [])[:3]:          # T、F1、F2
        path.append((y, z))
    path.append((end + 0.8, path[-1][1]))                  # 从最后一个折点竖直垂下
    # 每段沿自己那段胸面的法线往外偏（gap + 半厚）；按竖直方向挪的话，斜面越陡实际离得越近，会切进胸里
    last = None
    for (y0_, z0_), (y1_, z1_) in zip(path, path[1:]):
        if y0_ - y1_ <= 0.05:
            continue
        L = math.hypot(y0_ - y1_, z1_ - z0_)
        ny, nz = (z0_ - z1_) / L, -(y0_ - y1_) / L          # 段方向 (y1-y0, z1-z0) 的垂线，朝前（-z）
        if nz > 0:
            ny, nz = -ny, -nz
        o = gap + th / 2
        a_, b_ = [0, y0_ + ny * o, z0_ + nz * o], [0, y1_ + ny * o, z1_ + nz * o]
        k.slab("tie", "UpperBody", a_, b_, 1.15, th, m, outward=[0, -1])
        last = b_
    k.slab("tie_tip", "UpperBody", last, [0, end, last[2]], 0.7, th, m, outward=[0, -1])


def ring_z(rings, y):
    """裙圈在高度 y 处的（中心 z, rx, rz）——按上 / 中 / 下三圈线性插值。"""
    pts = [(r[3], r[0][1], r[1], r[2]) for r in rings]
    for (y0, c0, a0, b0), (y1, c1, a1, b1) in zip(pts, pts[1:]):
        if y1 <= y <= y0:
            t = (y0 - y) / (y0 - y1)
            return c0 + (c1 - c0) * t, a0 + (a1 - a0) * t, b0 + (b1 - b0) * t
    y, c, a, b = pts[-1] if y < pts[-1][0] else pts[0]
    return c, a, b


def skirt(k, C, B):
    """A 字裙：两圈斜板（上圈到中段、下圈错开半格到裙摆）+ 可选正面面板材质 + 可选荷叶边圈。"""
    S = C["skirt"]
    top, mid, bot = B["skirt_" + S["len"]]
    if S.get("band"):
        # 一体式腰：腰盒往下通到裙圈上沿下 0.2，换成「衬衫 + 下摆边 + 裙腰」画在一起的材质；
        # 裙子上圈缩进腰盒截面以内（顶边藏在盒子里），裙子从腰盒下沿底下张出去
        ww, wd = B["waist"]
        for c in k.cubes:
            if c["name"] == "waist":
                c["from"] = [c["from"][0], top[3] - 0.2, c["from"][2]]
                c["mat"] = S["band"]
        top = (top[0], ww - 0.15, wd - 0.15, top[3])
    for s in ("Front", "Back", "Left", "Right"):
        k.group(f"{s}Skirt", "Skirt", (0, top[3], 0))

    def grp(phi):
        p = phi % 360
        return "FrontSkirt" if p <= 45 or p > 315 else "RightSkirt" if p <= 135 else "BackSkirt" if p <= 225 else "LeftSkirt"

    def front(phi):
        p = phi % 360
        return p <= 34 or p >= 326
    up_mat = lambda i, p: S["front_mat"] if S.get("front_mat") and front(p) else S["mat"]
    low_mat = lambda i, p: S["front_hem_mat"] if S.get("front_hem_mat") and front(p) else S["hem_mat"]
    mid_hi = (mid[0], mid[1] - 0.1, mid[2] - 0.1, mid[3] + 0.4)
    n_up, n_low = 12, 16
    k.ring("skirt_up", grp, top, mid, n_up, 0.38, up_mat, overlap=1.3, faces_of=lambda i, p: {"south": S["in"]})
    k.ring("skirt_low", grp, mid_hi, bot, n_low, 0.38, low_mat, overlap=1.3, phase=180 / n_low,
           faces_of=lambda i, p: {"south": S["in"], "down": S["in"]})
    if S.get("frill"):
        c, rx, rz, y = bot[0], bot[1], bot[2], bot[3]
        k.ring("skirt_frill", grp, (c, rx - 0.1, rz - 0.1, y + 0.7), ((c[0], c[1] + 0.05), rx + 0.45, rz + 0.45, y - 1.0),
               20, 0.3, lambda i, p: S["frill"], overlap=1.25, faces_of=lambda i, p: {"south": S["frill"]})
    return (top, mid, bot)


def hem_box(B, rings):
    """上衣下摆方块的范围：从裙子上圈往下 0.25 到往上 1.3；半宽 / 半深至少比腰盒大 0.35，
    并且盖得住裙面在下沿处的截面（+0.12），这样裙子是从下摆底下张出去的。"""
    top = rings[0]
    y0, y1 = top[3] - 0.25, top[3] + 1.3
    _, rx, rz = ring_z(rings, y0)
    ww, wd = B["waist"]
    return y0, y1, max(ww + 0.35, rx + 0.12), max(wd + 0.35, rz + 0.12)


def shirt_hem(k, C, B, rings):
    """上衣下摆压在裙子外面：一块比腰略宽的方块 + 青边，裙子上圈缩在它里面。
    试过一圈斜板，三种都不干净——上圈外接腰盒露锯齿；上圈藏进腰盒板扭着交叉露缝；照裙子上段外偏拐角处板稀成一片片。"""
    y0, y1, hw, hd = hem_box(B, rings)
    k.box("shirt_hem", "UpBody", [-hw, y0, -hd], [hw, y1, hd], C["shirt_hem"],
          faces={"down": C["skirt"]["in"]})


def trim_under_skirt(k, rings, prefix="leg_out_"):
    """珍妮腿外侧斜条：被裙子盖住的那段本来看不见，截到裙摆下沿 + 0.3 为止（不然会从裙面顶出来）。"""
    hem = rings[-1][3] + 0.3
    for c in list(k.cubes):
        if c["name"].startswith(prefix) and c["to"][1] > hem:
            if c["from"][1] >= hem:
                k.cubes.remove(c)
            else:
                c["to"] = [c["to"][0], hem, c["to"][2]]


def fit_under_skirt(k, rings, names=("hips", "waist")):
    """裙子里的身体块按裙面截面收进去：半宽 / 半深不超过该高度裙圈的 0.68（椭圆内接矩形 ≈ 0.707，再留板厚）。
    胯整个在裙子里；腰盒跨过裙子上沿时拆成两块，只收裙子里那一截（外面看不见，只是不再从裙面顶出来）。"""
    y_top = rings[0][3]
    for c in list(k.cubes):
        if c["name"] not in names or c.get("rotation") or c["from"][1] >= y_top:
            continue
        if c["to"][1] > y_top:
            lo = k.box(c["name"] + "_low", c["group"], [c["from"][0], c["from"][1], c["from"][2]],
                       [c["to"][0], y_top, c["to"][2]], c["mat"])
            c["from"] = [c["from"][0], y_top, c["from"][2]]
            c = lo
        y = min(c["to"][1], y_top)
        cz, rx, rz = ring_z(rings, y)
        hw = min((c["to"][0] - c["from"][0]) / 2, rx * 0.68)
        hd = min((c["to"][2] - c["from"][2]) / 2, rz * 0.68)
        c["from"] = [-hw, c["from"][1], cz - hd]
        c["to"] = [hw, c["to"][1], cz + hd]


def fit_under_skirt(k, rings, names=("hips",)):
    """裙子里的身体块（胯）按裙面截面收进去：半宽 / 半深不超过该高度裙圈的 0.68（椭圆内接矩形 ≈ 0.707，再留板厚）。
    胯整个藏在裙子里，收窄看不见，只是不再从裙面顶出来。"""
    for c in k.cubes:
        if c["name"] not in names or c.get("rotation"):
            continue
        y = min(c["to"][1], rings[0][3])
        cz, rx, rz = ring_z(rings, y)
        hw = min((c["to"][0] - c["from"][0]) / 2, rx * 0.68)
        hd = min((c["to"][2] - c["from"][2]) / 2, rz * 0.68)
        c["from"] = [-hw, c["from"][1], cz - hd]
        c["to"] = [hw, c["to"][1], cz + hd]


def apron(k, C, B, rings):
    """白围裙：顺着裙子前面的斜度挂一块板（从腰到膝下），带小鲸鱼。"""
    y_top, y_bot = rings[0][3] - 0.2, B["apron_bot"]
    c0, rx0, rz0 = ring_z(rings, y_top)
    c1, rx1, rz1 = ring_z(rings, y_bot)
    width = (rx0 + rx1) * 0.72
    k.slab("apron", "FrontSkirt", [0, y_top, c0 - rz0 - 0.45], [0, y_bot, c1 - rz1 - 0.55], width, 0.25, C["apron"],
           outward=[0, -1], faces={"north": {"mat": C["apron"], "decal": "whale", "at": ["center", -4]}})


def back_bow(k, C, B):
    y, z = B["back_bow_y"], B["half_d"] + 0.15
    m = C["back_bow"]
    k.box("back_bow_knot", "UpBody", [-0.6, y - 0.6, z], [0.6, y + 0.6, z + 0.8], m)
    for s in (1, -1):
        x0, x1 = sx(s, 0.5, 3.0)
        k.box("back_bow_loop", "UpBody", [x0, y - 0.7, z + 0.1], [x1, y + 1.6, z + 0.6], m,
              rotation=[0, 0, 10 * s], origin=[s * 0.5, y, z])
        x0, x1 = sx(s, 0.2, 1.1)
        k.box("back_bow_tail", "UpBody", [x0, y - 4.5, z + 0.25], [x1, y - 0.4, z + 0.55], m,
              rotation=[0, 0, -10 * s], origin=[s * 0.6, y - 0.4, z])


def tail(k, B):
    """鲸鱼尾：从腰后伸出，往后下垂再往上翘的三节链 + 两片尾鳍。"""
    pts, w = B["tail"], B["tail_w"]
    k.group("Tail", "UpBody", tuple(pts[0]))
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        ww = w * (1 - 0.16 * i)
        k.slab(f"tail_{i + 1}", "Tail", a, b, ww, ww * 0.85, "tail", outward=[0, 1],
               faces={"south": "tail_under"})  # 浅色腹面朝裙子，背面是深色
    end = pts[-1]
    for s in (1, -1):
        # 尾鳍：贴地的两片宽叶，向两侧后方张开、叶尖略翘
        k.slab("tail_fluke", "Tail", end, [s * w * 1.8, end[1] + 0.5, end[2] + w * 0.9], w * 1.0, 0.5, "tail",
               faces={"down": "tail_under"})


def add_bust(k, C, preset, style, size):
    """胸部：tri 侧面三角（推荐）/ block 一整块前倾 / round 三层叠圆弧 / pair 两块并排外偏。大小 s/m/l。
    tri：社区模型的做法（DDLC Monika 等，胸部方块绕 X 轴转 ~53°，一个棱角朝前）。侧面看是一个三角：
    上斜面从锁骨处顺着斜出去，只在乳尖一个转折，下斜面收回下胸；不是整块凸出，也不是台阶。
    矩形的角是 90°，所以 上斜面竖向长 × 下斜面竖向长 = 凸出深度²；取上 / 下 = 1.8（转折偏下）。"""
    w, hh, d = BUST[size]
    if preset == "ysm":
        w *= 1.25
    top, z0 = BODY[preset]["bust"]
    mat = C.get("bust_mat", "dress")
    # 底面不再用裙子内衬的深色：tri 的斜板一转，底面会从折线处露出来成一条黑线
    faces = None if style == "tri" else {"down": C["skirt"]["in"]}
    if style == "tri":
        # 侧面一个三角：上斜面从胸口斜出去，只在乳尖一个转折，下斜面收回下胸。每侧上下两块斜板。
        # 底面（贴在胸口上的宽 × 高）所有尺码一样，尺码只改乳尖：往前 = 突出，往下 = 下垂。s = 平胸（不加）。
        # 两侧都正对前方：往外偏转的话两块板靠中间的边更靠前，胸骨正中会鼓出一道棱（领带压在上面）。
        # 试过、用户否掉的：转折处加过渡面 + 内外两列 / 两侧再叠凸起——中间还是显得突出。
        # 斜板前表面正好落在折线上，往里加厚填到胸口里面。返回胸骨中线的折线（胸口顶、乳尖）给领带贴。
        if TRI[size] is None:
            return None
        bw = TRI_BASE_W[preset]
        depth, fold = TRI[size]
        yt = top - 0.6
        yb = yt - TRI_BASE_H
        yf = yb + TRI_BASE_H * fold
        assert depth <= math.sqrt((yt - yf) * (yf - yb)) + 1e-6, "乳尖张角 < 90°，斜板端面会戳出来"
        fwd = np.array([0.0, 0.0, -1.0])
        for s in (1, -1):
            xc, wcol = s * (bw / 4 + 0.04), bw / 2 + 0.04
            T, F, Bt = np.array([xc, yt, z0]), np.array([xc, yf, z0 - depth]), np.array([xc, yb, z0])
            for nm, a_, b_ in (("bust_up", T, F), ("bust_lo", F, Bt)):
                dv = (b_ - a_) / np.linalg.norm(b_ - a_)
                f = fwd - (fwd @ dv) * dv
                f /= np.linalg.norm(f)
                th = depth + 0.35
                off = -f * th / 2
                k.beam(nm, "UpperBody", (a_ + off).tolist(), (b_ + off).tolist(), wcol, th, mat,
                       facing=tuple(fwd), ext=0.0, faces=faces)
        return [(yt, z0), (yf, z0 - depth)]
    elif style == "block":
        k.box("bust", "UpperBody", [-w / 2, top - hh, z0 - d], [w / 2, top, z0 + 0.6], mat,
              rotation=[8, 0, 0], origin=[0, top, z0], faces=faces)
    elif style == "round":
        y = top
        for lw, lh, ld in [(0.86, 0.28, 0.55), (1.0, 0.42, 1.0), (0.92, 0.30, 0.78)]:
            k.box("bust", "UpperBody", [-w * lw / 2, y - hh * lh, z0 - d * ld], [w * lw / 2, y, z0 + 0.6], mat, faces=faces)
            y -= hh * lh
    else:
        k.group("Bust", "UpperBody", (0, top, z0), (18, 0, 0))
        for s in (1, -1):
            x0, x1 = sx(s, 0.05, w / 2 + 0.15)
            k.box("bust", "Bust", [x0, top - hh, z0 - d], [x1, top, z0 + 1.2], mat, faces=faces,
                  rotation=[0, -10 * s, 0], origin=[s * w / 4, top, z0])


# ---------------- 身体（实测比例） ----------------
def body_jenny(k, C, splay=13):
    """珍妮系实测：腰 5×6×3、胯 8×2×3、细臂 2×10×2、腿 3 宽 + 外侧 1 宽外斜条（大腿上宽下窄）。"""
    U, Bn = "UpperBody", "UpBody"
    tf = {"north": C["torso_front"]} if C.get("torso_front") else None
    # 轻微倒三角：芯是腰宽（半宽 2.5，原珍妮实测）的一根，两侧斜板外表面从肩下（半宽 2.95，y 23.6）斜收到腰（2.5，y 18.2）
    # （第一版收到 2.35，用户：「腰显得细了」）
    k.box("neck", U, [-1.0, 22.8, -1.0], [1.0, 24.2, 1.0], "skin")
    # 躯干深 4（z ±2）：社区参考见 docs/blocky-community-analysis.md
    k.box("shoulders", U, [-3.0, 22.0, -2.0], [3.0, 23.0, 2.0], "dress", faces=tf)
    k.box("chest", U, [-2.5, 21.0, -2.0], [2.5, 22.5, 2.0], C.get("chest_mat", "dress"), faces=tf)
    k.box("waist", Bn, [-2.5, 15.0, -2.0], [2.5, 21.0, 2.0], "dress",
          faces={"north": C["waist_front"]} if C.get("waist_front") else None)
    for s in (1, -1):
        t = 0.6
        k.slab("torso_side", U, [s * (2.95 - t / 2), 22.9, 0], [s * (2.5 - t / 2), 18.2, 0], 4.0, t, "dress",
               outward=[s, 0])
    k.box("hips", Bn, [-4.0, 13.0, -2.0], [4.0, 15.0, 2.0], "dress")
    leg = C.get("leg_mat", "skin")
    for side, s in (("Right", 1), ("Left", -1)):
        k.group(f"{side}Arm", U, (4.0 * s, 21.6, 0), (0, 0, splay * s))  # 外张让开 A 字裙
        A = f"{side}Arm"
        if C.get("sleeve") == "long":
            x0, x1 = sx(s, 3.0, 5.0)
            k.box(f"arm_{side[0]}", A, [x0, 14.6, -1.0], [x1, 22.5, 1.0], "sleeve_long")
            x0, x1 = sx(s, 2.85, 5.15)
            k.box(f"cuff_{side[0]}", A, [x0, 13.9, -1.15], [x1, 15.1, 1.15], "cuff")
            x0, x1 = sx(s, 3.0, 5.0)
            k.box(f"hand_{side[0]}", A, [x0, 12.5, -1.0], [x1, 14.6, 1.0], "skin")
        elif C.get("sleeve") == "detached":
            # 分离袖套：上臂中段开始，手腕喇叭口 + 青色边；外侧一列灯；左上臂纹身
            outer = "east" if s > 0 else "west"
            x0, x1 = sx(s, 3.0, 5.0)
            af = {outer: {"mat": "skin", "decal": C["tattoo"], "at": ["center", 2]}} if C.get("tattoo") and s < 0 else None
            k.box(f"arm_{side[0]}", A, [x0, 12.5, -1.0], [x1, 22.5, 1.0], "skin", faces=af)
            for j, (y0, y1, e) in enumerate([(17.3, 19.8, 0.3), (15.1, 17.4, 0.6), (13.4, 15.2, 0.95)]):
                x0, x1 = sx(s, 3.0 - e, 5.0 + e)
                mat = ("dsleeve_top", "dsleeve", "dsleeve_cuff")[j]
                f = {outer: {"mat": mat, "decal": "sleeve_lights", "at": ["center", 0]}} if j == 1 else None
                k.box(f"dsleeve_{side[0]}" if j < 2 else f"cuff_{side[0]}", A, [x0, y0, -1.0 - e], [x1, y1, 1.0 + e], mat, faces=f)
        else:
            x0, x1 = sx(s, 3.0, 5.0)
            k.box(f"arm_{side[0]}", A, [x0, 12.5, -1.0], [x1, 22.5, 1.0], "skin")
        if C.get("sleeve") not in ("detached", "none", "armband"):
            x0, x1 = sx(s, 2.75, 5.3)
            k.box(f"sleeve_{side[0]}", A, [x0, 19.7, -1.35], [x1, 23.2, 1.35], "sleeve")
        k.group(f"{side}Leg", "DownBody", (2.0 * s, 13.1, 0))
        x0, x1 = sx(s, 0.25, 3.25)
        k.box(f"leg_{side[0]}", f"{side}Leg", [x0, 0, -1.5], [x1, 12.5, 2.0], leg)
        bt = C.get("boots")
        x0, x1 = sx(s, 3.0, 4.0)
        k.box(f"leg_out_{side[0]}", f"{side}Leg", [x0, BODY["jenny"]["boot_top"] - 0.6 if bt else 0, -1.5], [x1, 12.5, 2.0], leg,
              rotation=[0, 0, -3.6 * s], origin=[2.0 * s, 13.1, 0])
        if bt:
            # 过膝长靴：靴筒套在腿外（外扩 0.15），靴口青边；外斜条止于靴口
            x0, x1 = sx(s, 0.22, 3.5)
            k.box(f"boot_top_{side[0]}", f"{side}Leg", [x0, 1.8, -1.65], [x1, BODY["jenny"]["boot_top"], 2.15], bt["top"])
            x0, x1 = sx(s, 0.22, 3.6)
            k.box(f"shoe_{side[0]}", f"{side}Leg", [x0, 1.0, -3.4], [x1, 1.9, 2.25], bt["mat"])          # 鞋往前伸
            k.box(f"platform_{side[0]}", f"{side}Leg", [x0, 0, -3.45], [x1, 1.0, 2.3], bt["sole"])   # 厚底
            continue
        x0, x1 = sx(s, 0.15, 3.45)
        k.box(f"shoe_{side[0]}", f"{side}Leg", [x0, 0, -3.3], [x1, 1.8, 2.15], "shoe")   # 鞋往前伸（社区约 0.95 S）
        k.box(f"strap_{side[0]}", f"{side}Leg", [x0, 1.8, -1.65], [x1, 2.2, 2.1], C.get("strap", "red"))


def body_ysm(k, C, splay=17):
    """YSM 二次元实测（莱莎 / 星 / 真机伶 / 伊蕾娜）：胸 7.4×4×4、下胸 6.2×2×3、腰 4.9×3×3、胯约 7.9 宽；
    手臂 3×6.2×3 + 3×6×3 + 手 3×2×3，外张 17°；大腿 3.65×10×4.1、小腿 3.5×9×4，两腿间留缝。"""
    U, Bn = "UpperBody", "UpBody"
    tf = {"north": C["torso_front"]} if C.get("torso_front") else None
    k.box("neck", U, [-0.75, 30.8, -0.7], [0.75, 32.2, 0.7], "skin")
    k.box("chest", U, [-3.7, 27.0, -2.0], [3.7, 31.0, 2.0], "dress", faces=tf)
    k.box("underchest", U, [-3.1, 25.2, -1.5], [3.1, 27.2, 1.5], "dress", faces=tf)
    k.box("waist", Bn, [-2.45, 22.1, -1.5], [2.45, 25.3, 1.5], "dress")
    k.box("hips", Bn, [-3.95, 19.3, -2.2], [3.95, 22.0, 2.2], "dress")
    leg = C.get("leg_mat", "skin")
    long_sleeve = C.get("sleeve") == "long"
    for side, s in (("Right", 1), ("Left", -1)):
        k.group(f"{side}Arm", U, (4.4 * s, 29.6, 0), (0, 0, splay * s))
        k.group(f"{side}ForeArm", f"{side}Arm", (4.3 * s, 24.5, 0))
        k.group(f"{side}Hand", f"{side}ForeArm", (4.3 * s, 18.7, 0))

        def bx(name, grp_, a, b_, y0, y1, z0, z1, mat):
            x0, x1 = sx(s, a, b_)
            k.box(f"{name}_{side[0]}", grp_, [x0, y0, z0], [x1, y1, z1], mat)
        arm_mat = "sleeve_long" if long_sleeve else "skin"
        outer = "east" if s > 0 else "west"
        up_faces = {outer: {"mat": "skin", "decal": C["tattoo"]}} if C.get("tattoo") and s < 0 else None
        x0, x1 = sx(s, 2.75, 5.8)
        k.box(f"upper_arm_{side[0]}", f"{side}Arm", [x0, 24.55, -1.5], [x1, 30.75, 1.55], arm_mat, faces=up_faces)
        if C.get("sleeve") == "detached":
            # 分离袖套：上臂中段开始，越往下越宽，手腕处喇叭口 + 青色边；外侧一列青色灯
            bx("dsleeve_up", f"{side}Arm", 2.45, 6.1, 24.5, 26.9, -1.8, 1.85, "dsleeve")
            x0, x1 = sx(s, 2.35, 6.2)
            k.box(f"dsleeve_{side[0]}", f"{side}ForeArm", [x0, 19.5, -1.9], [x1, 24.7, 1.9], "dsleeve",
                  faces={outer: {"mat": "dsleeve", "decal": "sleeve_lights", "at": ["center", 2]}})
            bx("cuff", f"{side}ForeArm", 2.05, 6.5, 18.1, 19.7, -2.2, 2.2, "dsleeve_cuff")
        elif C.get("sleeve") not in ("none", "armband"):
            bx("sleeve", f"{side}Arm", 2.5, 6.1, 26.6, 31.1, -1.85, 1.85, "sleeve")
        bx("forearm", f"{side}ForeArm", 2.78, 5.78, 18.65, 24.65, -1.5, 1.5, arm_mat)
        if long_sleeve:
            bx("cuff", f"{side}ForeArm", 2.6, 5.96, 18.3, 19.7, -1.7, 1.7, "cuff")
        bx("hand", f"{side}Hand", 2.78, 5.78, 16.65, 18.65, -1.5, 1.5, "skin")
        k.group(f"{side}Leg", "DownBody", (2.32 * s, 19.55, 0))
        k.group(f"{side}LowerLeg", f"{side}Leg", (2.12 * s, 11.1, 0.25))
        k.group(f"{side}Foot", f"{side}LowerLeg", (2.11 * s, 2.75, 0.44))
        bx("thigh", f"{side}Leg", 0.29, 3.94, 10.55, 20.55, -1.7, 2.4, leg)
        bt = C.get("boots")
        if bt:
            # 过膝长靴：靴筒比腿外扩约 0.2（套在腿外），靴口一圈青边；靴底更大一圈
            bx("boot_top", f"{side}Leg", 0.12, 4.11, 10.4, BODY["ysm"]["boot_top"], -1.88, 2.58, bt["top"])
            bx("shin", f"{side}LowerLeg", 0.15, 4.09, 1.9, 10.9, -1.85, 2.55, bt["mat"])
            bx("shoe", f"{side}Foot", 0.05, 4.15, 0.0, 2.0, -2.9, 2.7, bt["sole"])
            continue
        bx("shin", f"{side}LowerLeg", 0.35, 3.89, 1.9, 10.9, -1.65, 2.35, leg)
        bx("shoe", f"{side}Foot", 0.25, 3.95, 0.0, 2.0, -2.6, 2.5, "shoe")
        bx("strap", f"{side}Foot", 0.3, 3.9, 2.0, 2.4, -1.75, 2.45, C.get("strap", "red"))


BODY_CUR = None


HEAD_GROUPS = {"AllHead", "Head", "Hair", "Face", "RightEar", "LeftEar", "RightTwintail", "LeftTwintail"}


def squash(k, chin, to):
    """Q 版：头部整体下移到 to，下巴以下的身体高度按 to/chin 等比压缩（宽度不变）。"""
    f, dy = to / chin, to - chin
    head = lambda g: g in HEAD_GROUPS
    for g in k.groups:
        o = g["origin"]
        g["origin"] = [o[0], o[1] + dy if head(g["name"]) else o[1] * f, o[2]]
    for c in k.cubes:
        if head(c["group"]):
            mv = lambda v: [v[0], v[1] + dy, v[2]]
        else:
            mv = lambda v: [v[0], v[1] * f, v[2]]
        c["from"], c["to"] = mv(c["from"]), mv(c["to"])
        if "origin" in c:
            c["origin"] = mv(c["origin"])


def _shift(hexc, d):
    v = [max(0, min(255, int(hexc[i:i + 2], 16) + d)) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(v)


def hair_variants(mats):
    """发束用的三档深浅：hair / hair_v1（暗）/ hair_v2（亮），hair_low 同理。"""
    out = dict(mats)
    for base in ("hair", "hair_low"):
        m = mats[base]
        for tag, dlt in (("v1", -14), ("v2", 10)):
            mm = dict(m)
            if "gradient" in m:
                mm["gradient"] = [_shift(c, dlt) for c in m["gradient"]]
            elif "fill" in m:
                mm["fill"] = _shift(m["fill"], dlt)
            out[f"{base}_{tag}"] = mm
    return out


ARM_RULES = ("arm vs skirt/hem", "arm vs twintail", "arm vs torso")


def build(char, preset, bust, bust_size, eyes=None, hair_shell=None, hair_detail=None):
    """手臂外张角先用预设值（jenny 13° / ysm 17°），穿模检查发现手臂碰到裙子 / 衣摆 / 双马尾 / 身体，就每次加 1° 重建。"""
    base = 13 if PRESETS[preset]["body"] == "jenny" else 17
    for splay in range(base, base + 15):
        spec = _build(char, preset, bust, bust_size, eyes, splay, hair_shell, hair_detail)
        hits = CLIP.check(spec)
        if not any(hits[r] for r in ARM_RULES):
            break
    spec["arm_splay"] = splay
    spec["head_size"] = PRESETS[preset]["head"]
    spec["preset_body"] = PRESETS[preset]["body"]
    return spec


def _build(char, preset, bust, bust_size, eyes, splay, hair_shell=None, hair_detail=None):
    global BODY_CUR
    C, P = dict(CHARS[char]), dict(PRESETS[preset])
    if hair_shell:
        C["hair_shell_style"] = hair_shell
    if hair_detail:
        C["hair_detail"] = hair_detail
    if eyes:
        P["eyes"] = eyes
    B = dict(BODY[P["body"]])
    mats = hair_variants(C["materials"])
    if C.get("hair_detail") in ("fine","reference"):
        for name in list(mats):
            if name.startswith(("hair",)):
                mm=dict(mats[name],texel_per_unit=4)
                mm.pop("gradient",None)
                mm["fill"]=_shift(C["palette"]["h"],6) if name.startswith("hair_low") else C["palette"]["h"]
                if name.endswith("_v1"): mm["fill"]=_shift(C["palette"]["h"],-8)
                elif name.endswith("_v2"): mm["fill"]=_shift(C["palette"]["h"],9)
                mm["streaks"]={"amount":6}
                mm["shade"]={"edge":3,"top":3,"noise":2}
                mats[name]=mm
        mats["hair_tip"] = {"fill": C["palette"]["h"], "texel_per_unit":4, "shade":False}
        mats["hair_clip"] = {"fill": C["materials"]["red"]["fill"], "texel_per_unit":8 if C.get("hair_detail") == "reference" else 4, "shade":False}
    mats.setdefault("brow", dict(mats["lash"]))
    if C.get("corset"):
        # 束腰：胸下到腰一段，白腰带 / 裙子 / 围裙 / 背后蝴蝶结整体下移到束腰下沿
        cb = B["ribbon"][1] - C["corset"]["h"]
        _, _, hw, hd = B["ribbon"]
        B["corset"] = (cb, B["ribbon"][1], hw + 0.08, hd + 0.03)
        B["ribbon"] = (cb - 0.6, cb + 0.05, hw + 0.12, hd + 0.08)
        for key in ("skirt_short", "skirt_long"):
            t, m_, b_ = B[key]
            B[key] = ((t[0], t[1], t[2], cb - 0.1), m_, b_)
        B["back_bow_y"] = cb - 0.3
    BODY_CUR = B
    k = Kit()
    hs, hy0 = P["head"], P["head_y"]
    d = P.get("head_d", hs) / 2
    G = k.group
    G("Root")
    G("AllBody", "Root")
    G("UpBody", "AllBody", (0, hy0 - 12 if P["body"] == "jenny" else 21.5, 0))
    G("UpperBody", "UpBody", (0, hy0, 0))
    G("AllHead", "UpperBody", (0, hy0, 0))
    G("Head", "AllHead", (0, hy0, 0))
    G("Hair", "Head", (0, hy0 + hs / 2, 0))
    G("Face", "Head", (0, hy0 + 2, -d))
    G("Skirt", "UpBody", (0, hy0 - 6, 0))
    G("DownBody", "AllBody", (0, 12 if P["body"] == "jenny" else 19.5, 0))

    decals = dict(C.get("decals_extra", {}))
    W = int(hs * P["texel"])
    decals["face"] = face_rows(W, W, {"w": 5, "h": 5} if P.get("pixel_eyes") else C["eye"], C["mouth"],
                               draw_eyes=bool(P.get("pixel_eyes")) and not P.get("eyes"))
    head_parts(k, C, P, decals)
    if C.get("hair_detail") == "reference":
        clip_surface=[c["name"] for c in k.cubes if c["group"]=="Hair"
                      and c["name"].startswith("side_lock_clip") and c["from"][0]>0]
        for c in k.cubes:
            if c["name"].startswith("hairclip_star"):
                cy=(c["from"][1]+c["to"][1])/2
                z=front_profile(k,tuple(clip_surface),c["to"][0]+0.1,cy)
                c["from"][2]=z-0.03
                c["to"][2]=z-0.005
    if C.get("stage_outfit") and C.get("hair_shell_style") != "box":
        _OPTIONAL["hair"].add_details(k, C, P, decals)
    if P["body"] == "jenny":
        body_jenny(k, C, splay)
    else:
        body_ysm(k, C, splay)
    if P.get("eyes"):
        eyes_cubes(k, hy0, d, EYES[P["eyes"]])
    if C.get("shirt_hem"):
        S_ = C["skirt"]
        B["tie_end"] = hem_box(B, B["skirt_" + S_["len"]])[1] + 0.15   # 领带停在下摆上沿
    elif C["skirt"].get("band"):
        B["tie_end"] = B["skirt_" + C["skirt"]["len"]][0][3] + 1.6     # 领带停在画出来的下摆边上方
    collar_and_bow(k, C, B)
    if B.get("corset"):
        y0, y1, hw, hd = B["corset"]
        k.box("corset", "UpBody", [-hw, y0, -hd], [hw, y1, hd], C["corset"]["mat"],
              faces={"north": {"mat": C["corset"]["mat"], "decal": "corset_buttons"}})
    if C.get("waist_ribbon"):
        y0, y1, hw, hd = B["ribbon"]
        k.box("waist_ribbon", "UpperBody", [-hw, y0, -hd], [hw, y1, hd], C["waist_ribbon"])
    rings = skirt(k, C, B)
    fit_under_skirt(k, rings, ("hips",) if C["skirt"].get("band") else ("hips", "waist"))
    trim_under_skirt(k, rings)
    if C.get("shirt_hem"):
        shirt_hem(k, C, B, rings)
    if C.get("apron"):
        apron(k, C, B, rings)
    if C.get("back_bow"):
        back_bow(k, C, B)
    if C.get("tail"):
        tail(k, B)
    if bust != "none":
        B["bust_center"] = add_bust(k, C, P["body"], bust, bust_size)
    if B.get("tie_pending"):
        tie_strip(k, C, B)
    _OPTIONAL["outfit"].add_parts(k, C, B, P)
    _OPTIONAL["witch"].add_parts(k, C, B, P, rings)
    _OPTIONAL["outfit"].fit_chest(k, C, B)
    if P.get("squash_to"):
        squash(k, hy0, P["squash_to"])
    return k.spec({"texel_per_unit": P["texel"], "atlas_width": 256, "palette": C["palette"],
                   "materials": mats, "decals": decals})


def eyes_cubes(k, hy0, h, dims):
    """方块眼：眼白 + 凸出 0.35 的虹膜 + 高光 + 睫毛条 + 外眼角 + 腮红，尺寸见 EYES。"""
    zf = -h
    layers = [("eye_white", "white", -0.08, 0.2), ("iris", "iris", -0.38, 0.0), ("glint", "white", -0.42, -0.38),
              ("lash", "lash", -0.32, 0.0), ("lash_out", "lash", -0.32, 0.0), ("blush", "blush", -0.03, 0.0),
              ("brow", "brow", -0.25, 0.0)]
    for s in (1, -1):
        tag = "R" if s > 0 else "L"
        for name, mat, z0, z1 in layers:
            key = name.replace("eye_", "")
            if key == "brow" and "brow" not in dims:
                # 眉毛：睫毛条上方 0.35、略短一点、往外稍高（社区 71/74 有眉毛）
                la = dims["lash"]
                dims = dict(dims, brow=(la[0] + 0.15, la[1] - 0.25, la[3] + 0.35, la[3] + 0.7))
            ax, bx_, y0, y1 = dims[key]
            x0, x1 = sx(s, ax, bx_)
            k.box(f"{name}_{tag}", "Face", [x0, hy0 + y0, zf + z0], [x1, hy0 + y1, zf + z1], mat, hide=["south"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--char", default="kurumi", choices=list(CHARS))
    ap.add_argument("--preset", choices=list(PRESETS), required=True)
    ap.add_argument("--bust", choices=["none", "tri", "block", "round", "pair"], default=None)
    ap.add_argument("--bust-size", choices=list(BUST), default="m")
    ap.add_argument("--eyes", choices=list(EYES), help="覆盖预设的方块眼尺寸")
    ap.add_argument("--hair-shell", choices=["dome", "box"], help="头发外壳方案；默认沿用角色配置")
    ap.add_argument("--hair-detail", choices=["coarse","fine","reference"], help="头发版本：原版、细化版、参照立绘的偏分中发")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    bust_style=a.bust or CHARS[a.char].get("default_bust","none")
    spec = build(a.char, a.preset, bust_style, a.bust_size, a.eyes, a.hair_shell, a.hair_detail)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{a.char} {a.preset} {bust_style}-{a.bust_size}: {len(spec['cubes'])} cubes, arm splay {spec['arm_splay']}° -> {a.out}")


if __name__ == "__main__":
    main()
