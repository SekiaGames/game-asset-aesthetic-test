"""Create fictional narration voice references with Qwen VoiceDesign or VoxCPM.
Neutral example prompts replace the source project's role descriptions.
Model roots: TTS_MODELS_DIR; outputs: TTS_VOICE_OUTPUT.
"""

import argparse
import os
import random
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parent.parent
MODELS = Path(os.environ.get("TTS_MODELS_DIR", str(ROOT / "models")))
OUT = Path(os.environ.get("TTS_VOICE_OUTPUT", str(ROOT / "assets/voice/candidates")))

REF_TEXT = "大家好，今天介绍游戏角色素材的制作流程。我们先看参考图，再比较两种方法，最后说明检查结果和仍需改进的地方。"
STYLES = {
    "a": "成年女性讲解声线，温暖清晰，自然口语，中等语速，吐字准确。",
    "b": "成年男性讲解声线，沉稳清晰，自然口语，中等语速，吐字准确。",
}


def seed_all(s):
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)
    torch.cuda.manual_seed_all(s)


def run_qwen(n):
    from qwen_tts import Qwen3TTSModel

    kw = {}
    try:
        import flash_attn  # noqa: F401
        kw["attn_implementation"] = "flash_attention_2"
    except ImportError:
        pass
    model = Qwen3TTSModel.from_pretrained(
        str(MODELS / "qwen3-tts-voicedesign"), device_map="cuda:0", dtype=torch.bfloat16, **kw
    )
    for style, instruct in STYLES.items():
        for s in range(1, n + 1):
            seed_all(s)
            wavs, sr = model.generate_voice_design(text=REF_TEXT, language="Chinese", instruct=instruct)
            save(f"qwen-{style}-s{s}", wavs[0], sr)


def run_voxcpm(n):
    from voxcpm import VoxCPM

    model = VoxCPM.from_pretrained(str(MODELS / "voxcpm2"), load_denoiser=False)
    sr = model.tts_model.sample_rate
    for style, desc in STYLES.items():
        for s in range(1, n + 1):
            seed_all(s)
            wav = model.generate(text=f"({desc}){REF_TEXT}", cfg_value=2.0, inference_timesteps=10)
            save(f"voxcpm-{style}-s{s}", wav, sr)


def save(name, wav, sr):
    OUT.mkdir(parents=True, exist_ok=True)
    wav = np.asarray(wav, dtype=np.float32).squeeze()
    sf.write(OUT / f"{name}.wav", wav, sr)
    (OUT / f"{name}.lab").write_text(REF_TEXT, encoding="utf-8")
    print(f"OK {name} {len(wav) / sr:.1f}s sr={sr}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("backend", choices=["qwen", "voxcpm"])
    ap.add_argument("-n", type=int, default=4)
    a = ap.parse_args()
    {"qwen": run_qwen, "voxcpm": run_voxcpm}[a.backend](a.n)
