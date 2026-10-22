"""提交 See-through 的 API 格式 prompt 并轮询到结束。纯标准库。"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8188"
IMG = "Anime_game_character_reference_2026-10-21T13-55-27.png"

g = {
    "1": {"class_type": "LoadImage", "inputs": {"image": IMG}},
    "2": {"class_type": "JoinImageWithAlpha", "inputs": {"image": ["1", 0], "alpha": ["1", 1]}},
    "3": {"class_type": "SeeThrough_LoadLayerDiffModel", "inputs": {
        "model": "layerdifforg/seethroughv0.0.2_layerdiff3d", "vae_ckpt": "", "unet_ckpt": "",
        "quant_mode": "none", "cache_tag_embeds": True, "group_offload": False, "auto_download": False}},
    "4": {"class_type": "SeeThrough_LoadDepthModel", "inputs": {
        "model": "layerdifforg/seethroughv0.0.1_marigold", "quant_mode": "none",
        "cache_tag_embeds": True, "group_offload": False, "auto_download": False}},
    "5": {"class_type": "SeeThrough_GenerateLayers", "inputs": {
        "image": ["2", 0], "layerdiff_model": ["3", 0], "seed": 42,
        "resolution": 1280, "num_inference_steps": 30}},
    "6": {"class_type": "SeeThrough_GenerateDepth", "inputs": {
        "layers": ["5", 0], "depth_model": ["4", 0], "seed": 42, "resolution_depth": -1}},
    "7": {"class_type": "SeeThrough_PostProcess", "inputs": {
        "layers_depth": ["6", 0], "tblr_split": True, "use_lama": False}},
    "8": {"class_type": "SeeThrough_SavePSD", "inputs": {"parts": ["7", 0], "filename_prefix": "seethrough_kurumi"}},
}

req = urllib.request.Request(f"{BASE}/prompt", json.dumps({"prompt": g, "client_id": "verify"}).encode(),
                             {"Content-Type": "application/json"})
resp = json.load(urllib.request.urlopen(req, timeout=30))
if resp.get("node_errors"):
    raise SystemExit("校验失败: " + json.dumps(resp["node_errors"], ensure_ascii=False)[:1500])
pid = resp["prompt_id"]
print("submitted", pid, flush=True)

t0 = time.time()
last = 0
while True:
    h = json.load(urllib.request.urlopen(f"{BASE}/history/{pid}", timeout=20)).get(pid)
    if h:
        st = h.get("status", {})
        if st.get("completed"):
            print(f"\n完成 {time.time() - t0:.0f}s", flush=True)
            print("outputs:", json.dumps(h.get("outputs"), ensure_ascii=False)[:800], flush=True)
            break
        if st.get("status_str") == "error":
            msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
            print("\n执行失败:", json.dumps(msgs, ensure_ascii=False)[:2000], flush=True)
            break
    el = int(time.time() - t0)
    if el // 30 != last:
        last = el // 30
        print(f"  ...{el}s", flush=True)
    if el > 1800:
        print("超时 30 分钟", flush=True)
        break
    time.sleep(3)
