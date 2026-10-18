"""解析台本 markdown：取出编号台词和【】音效行，按出现顺序返回。

台词行：`T3-07 [tag] 文本……`，编号不进 TTS，后面整段（含行内 [tag]）原样交给 S2 Pro。
音效行：单独一行的 `【...】`，挂在下一句台词之前。
"""

import json
import re
import sys
from pathlib import Path

LINE_RE = re.compile(r"^(T(\d+)-(\d+))\s+(.+)$")
SFX_RE = re.compile(r"^【(.+)】$")
TRACK_RE = re.compile(r"^##\s+Track\s+(\d+)\s*(.*)$")


def parse(path: str | Path) -> list[dict]:
    items = []
    track = None
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if m := TRACK_RE.match(s):
            track = int(m.group(1))
            items.append({"type": "track", "track": track, "title": m.group(2).strip()})
        elif m := LINE_RE.match(s):
            items.append({
                "type": "line",
                "id": m.group(1),
                "track": int(m.group(2)),
                "text": m.group(4).strip(),
            })
        elif m := SFX_RE.match(s):
            items.append({"type": "sfx", "track": track, "desc": m.group(1)})
    return items


def lines(path, ids=None, track=None):
    out = [i for i in parse(path) if i["type"] == "line"]
    if track is not None:
        out = [i for i in out if i["track"] == track]
    if ids:
        want = set(ids)
        out = [i for i in out if i["id"] in want]
    return out


if __name__ == "__main__":
    print(json.dumps(parse(sys.argv[1]), ensure_ascii=False, indent=1))
