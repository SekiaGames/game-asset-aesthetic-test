"""按编号批量调用 fish-speech API 服务（S2 Pro）配音，每句可抽多遍。

在 WSL 的 fish-speech venv 里跑（需要 ormsgpack、requests）：
  python src/tts_batch.py --ref assets/voice/<音色>.wav --track 3 --takes 3 -o output/tts/<音色>
  python src/tts_batch.py --ref ... --ids T3-07 T5-12 ...
  python src/tts_batch.py --no-ref --seed 11 --text "……" -o ...   # 不给参考，随机音色

参考音频旁边要有同名 .lab/.txt 写参考文本。输出 <id>_t<k>.wav 和 manifest.jsonl（记录文本、种子、耗时）。
已存在的文件跳过，可以断点续跑。
"""

import argparse
import json
import sys
import time
from pathlib import Path

import ormsgpack
import requests

sys.path.insert(0, str(Path(__file__).parent))
import script_parse  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def ref_payload(ref: Path):
    for suf in (".lab", ".txt"):
        side = ref.with_suffix(suf)
        if side.is_file():
            return [{"audio": ref.read_bytes(), "text": side.read_text(encoding="utf-8").strip()}]
    sys.exit(f"参考音频缺文本：{ref.with_suffix('.lab')}")


def synth(url, text, refs, seed, temperature, top_p, timeout=900):
    req = {
        "text": text,
        "references": refs,
        "format": "wav",
        "seed": seed,
        "normalize": False,  # 讲稿先自行将数字与单位写成期望读音
        "use_memory_cache": "on",  # 缓存参考音频的编码，省掉每句约 4 秒的固定开销
    }
    if temperature is not None:
        req["temperature"] = temperature
    if top_p is not None:
        req["top_p"] = top_p
    r = requests.post(
        url,
        data=ormsgpack.packb(req),
        headers={"content-type": "application/msgpack"},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080/v1/tts")
    ap.add_argument("--script", default=str(ROOT / "scripts/narration.md"))
    ap.add_argument("--ref", help="参考音频 wav")
    ap.add_argument("--no-ref", action="store_true")
    ap.add_argument("--track", type=int)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--text", action="append", help="直接给文本（不从台本取）")
    ap.add_argument("--named", help="JSON 文件:键，取其中 {名字: 文本}，如 config/narration-example.json:voice")
    ap.add_argument("--takes", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1000, help="第 k 遍用 seed+k")
    ap.add_argument("--temperature", type=float)
    ap.add_argument("--top-p", type=float)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    refs = [] if a.no_ref else ref_payload(Path(a.ref))
    if a.named:
        fn, key = a.named.rsplit(":", 1)
        d = json.loads(Path(fn).read_text(encoding="utf-8"))[key]
        items = [{"id": k, "text": v} for k, v in d.items()]
    elif a.text:
        items = [{"id": f"X{i:02d}", "text": t} for i, t in enumerate(a.text, 1)]
    else:
        items = script_parse.lines(a.script, ids=a.ids, track=a.track)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    man = (out / "manifest.jsonl").open("a", encoding="utf-8")

    failures = 0
    for it in items:
        for k in range(1, a.takes + 1):
            f = out / f"{it['id']}_t{k}.wav"
            if f.exists():
                continue
            seed = a.seed + k
            t0 = time.time()
            try:
                wav = synth(a.url, it["text"], refs, seed, a.temperature, a.top_p)
            except Exception as e:  # 单句失败不影响整批
                failures += 1
                print(f"FAIL {it['id']} t{k}: {e}", flush=True)
                continue
            f.write_bytes(wav)
            dt = time.time() - t0
            rec = {"id": it["id"], "take": k, "seed": seed, "text": it["text"],
                   "ref": a.ref, "sec": round(dt, 1), "file": f.name}
            man.write(json.dumps(rec, ensure_ascii=False) + "\n")
            man.flush()
            print(f"OK {it['id']} t{k} {dt:.1f}s", flush=True)

    man.close()
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
