"""Measure narration quality with ASR/pitch or speaker embeddings.
Metrics are proxies and do not replace listening. Chinese CER ignores non-Han characters.
Use local approved model resources; no source audio is bundled.
"""

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def embedder():
    from funasr import AutoModel
    m = AutoModel(model="iic/speech_campplus_sv_zh-cn_16k-common", device="cpu", disable_update=True)

    def emb(path):
        r = m.generate(input=str(path))[0]
        v = np.asarray(r["spk_embedding"]).reshape(-1)
        return v / np.linalg.norm(v)
    return emb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    emb = embedder()
    r = emb(ROOT / a.ref)
    rows = []
    for p in map(lambda x: ROOT / x, a.paths):
        for w in sorted(p.rglob("*.wav")) if p.is_dir() else [p]:
            s = float(emb(w) @ r)
            rows.append({"file": str(w.relative_to(ROOT)).replace("\\", "/"), "sim": round(s, 3)})
            print(rows[-1], flush=True)
    if a.out:
        Path(ROOT / a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
