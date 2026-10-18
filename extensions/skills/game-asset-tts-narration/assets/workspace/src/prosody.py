"""起伏度量：给“捧读”找个能算的代理指标。只是代理，好不好听还得人听。

每条 wav 算：
- f0_st_std：有声帧基频的标准差（半音）。越大音高起伏越大，捧读通常很小。
- f0_st_range：基频 5%–95% 分位跨度（半音）。
- f0_max：基频 95% 分位（Hz），尖叫、拔高时会升。
- rms_db_std：20ms 帧能量（dB，只算 -50dB 以上的帧）的标准差。越大轻重变化越大。
- voiced：有能量的帧里有基频的比例。喘着说、气声多时会降，平静念白接近 1。
- dur：时长（秒）。

用法（WSL，venv-asr 里有 pyworld）：
  python src/prosody.py <wav 或目录>... [-o out.json]
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pyworld
import soundfile as sf
from scipy.signal import resample_poly


def measure(path):
    y, sr = sf.read(path, dtype="float64")
    if y.ndim > 1:
        y = y.mean(1)
    y16 = resample_poly(y, 16000, sr) if sr != 16000 else y
    f0, _ = pyworld.harvest(y16, 16000, f0_floor=70, f0_ceil=1000, frame_period=10)
    v = f0[f0 > 0]
    st = 12 * np.log2(v / 100.0) if len(v) else np.array([0.0])
    hop = 320  # 20ms @16k
    fr = y16[: len(y16) // hop * hop].reshape(-1, hop)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    peak = db.max()
    loud = db > peak - 40
    vf = f0[1::2][: len(db)] > 0  # 10ms 一帧的基频对到 20ms 帧
    voiced = float(vf[loud[: len(vf)]].mean()) if loud.any() else 0.0
    db = db[db > peak - 50]
    return {
        "f0_st_std": round(float(st.std()), 2),
        "f0_st_range": round(float(np.percentile(st, 95) - np.percentile(st, 5)), 2),
        "f0_max": round(float(np.percentile(v, 95)) if len(v) else 0.0, 1),
        "rms_db_std": round(float(db.std()), 2),
        "voiced": round(voiced, 3),
        "dur": round(len(y) / sr, 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    files = []
    for p in map(Path, a.paths):
        files += sorted(p.glob("*.wav")) if p.is_dir() else [p]
    res = {}
    for f in files:
        res[str(f)] = measure(f)
        print(f, res[str(f)], flush=True)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
