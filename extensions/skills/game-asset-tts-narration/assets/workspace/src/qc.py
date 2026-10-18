"""Measure narration quality with ASR/pitch or speaker embeddings.
Metrics are proxies and do not replace listening. Chinese CER ignores non-Han characters.
Use local approved model resources; no source audio is bundled.
"""

import argparse
import os
import json
import re
import sys
from pathlib import Path

import numpy as np
import pyworld
import soundfile as sf
import soxr

ROOT = Path(__file__).resolve().parent.parent
TAG = re.compile(r"\[[^\]]*\]")
NONHAN = re.compile(r"[^一-鿿]")
SV_TAG = re.compile(r"<\|([^|]+)\|>")
_model = None


def asr(path):
    global _model
    if _model is None:
        from funasr import AutoModel
        _model = AutoModel(model=os.environ.get("TTS_ASR_MODEL", str(ROOT / "models/sensevoice-small")), device="cpu", disable_update=True)
    r = _model.generate(input=str(path), language="zh", use_itn=False)[0]["text"]
    tags = SV_TAG.findall(r)
    return SV_TAG.sub("", r).strip(), tags


def f0_median(y, sr):
    y16 = soxr.resample(y, sr, 16000).astype(np.float64)
    f0, t = pyworld.harvest(y16, 16000, f0_floor=70, f0_ceil=600, frame_period=10)
    v = f0[f0 > 0]
    return (float(np.median(v)) if len(v) else 0.0), float(len(v) / max(len(f0), 1))


def cer(ref, hyp):
    ref, hyp = NONHAN.sub("", ref), NONHAN.sub("", hyp)
    if not ref:
        return None
    d = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, hc in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (rc != hc))
    return d[-1] / len(ref)


def expected(wav: Path):
    lab = wav.with_suffix(".lab")
    if lab.exists():
        return lab.read_text(encoding="utf-8")
    man = wav.parent / "manifest.jsonl"
    if man.exists():
        for line in man.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec.get("file") == wav.name:
                return rec["text"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    wavs = []
    for p in map(Path, a.paths):
        wavs += sorted(p.rglob("*.wav")) if p.is_dir() else [p]
    rows = []
    for w in wavs:
        y, sr = sf.read(w, dtype="float32", always_2d=True)
        y = y.mean(1)
        dur = len(y) / sr
        f0, voiced = f0_median(y, sr)
        text, tags = asr(w)
        exp = expected(w)
        clean = TAG.sub("", exp) if exp else None
        c = cer(clean, text) if clean else None
        n = len(NONHAN.sub("", clean)) if clean else len(NONHAN.sub("", text))
        row = {"file": str(w.relative_to(ROOT)) if w.is_relative_to(ROOT) else str(w),
               "dur": round(dur, 2), "f0": round(f0, 1), "voiced": round(voiced, 2),
               "cps": round(n / dur, 2) if dur else 0, "cer": None if c is None else round(c, 3),
               "asr": text, "sv_tags": tags}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
