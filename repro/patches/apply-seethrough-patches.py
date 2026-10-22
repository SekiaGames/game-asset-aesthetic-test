#!/usr/bin/env python3
"""给 ComfyUI-See-through 0.5.0 打两个必需的补丁（幂等）。

    python3 apply-seethrough-patches.py [--node <custom_nodes/ComfyUI-See-through>]

补丁 1 · scheduler 走本地
    KDiffusionStableDiffusionXLPipeline 在 scheduler=None 时写死去拉
    frankjoshua/juggernautXL_version6Rundiffusion 的 scheduler_config.json。
    本地模型目录自带等价配置，改成从本地读。

补丁 2 · 修 MPS 上的 median 崩溃
    TransparentVAEDecoder.estimate_augmented 把 n 个 4 维结果 stack 成 5 维再
    torch.median(dim=0)，Metal 的 MPSNDArraySort 只支持 axis 0..3，直接
    "Axis = 4 ... only supports axis = 0, 1, 2, 3" 并 abort 整个进程。
    单分支时中位数就是它自己；多分支退回 CPU。

两个补丁都幂等：已经打过就跳过。
"""
import argparse
import os
import re
import sys

DEFAULT_NODE = "/Volumes/Data/Users/sekia/ComfyUI-Installs/ComfyUI/ComfyUI/custom_nodes/ComfyUI-See-through"

SCHED_MARK = "Scheduler from local model dir"
MEDIAN_MARK = "MPSNDArraySort"

SCHED_OLD = """        pipeline = KDiffusionStableDiffusionXLPipeline.from_pretrained(
            pretrained, trans_vae=trans_vae, unet=unet, scheduler=None, local_files_only=local_only)"""

SCHED_NEW = """        # 0.5.0 在 scheduler=None 时会写死去拉
        # frankjoshua/juggernautXL_version6Rundiffusion 的 scheduler/scheduler_config.json，
        # 离线或镜像不通时报 "does not appear to have a file named scheduler_config.json"。
        # 本地模型目录自带同一份配置（DPMPP_2M_SDE + final_sigmas_type=zero，SDXL betas），
        # 所以优先从本地读，读不到才退回原行为。
        scheduler = None
        if os.path.isfile(os.path.join(pretrained, "scheduler", "scheduler_config.json")):
            from diffusers import DPMSolverMultistepScheduler
            scheduler = DPMSolverMultistepScheduler.from_pretrained(
                pretrained, subfolder="scheduler", local_files_only=True)
            print("[SeeThrough] Scheduler from local model dir (no juggernaut fetch)", flush=True)

        pipeline = KDiffusionStableDiffusionXLPipeline.from_pretrained(
            pretrained, trans_vae=trans_vae, unet=unet, scheduler=scheduler, local_files_only=local_only)"""

MEDIAN_OLD = """        result = torch.stack(result, dim=0)
        median = torch.median(result, dim=0).values
        return median"""

MEDIAN_NEW = """        result = torch.stack(result, dim=0)
        # Apple MPS 的 MPSNDArraySort 只支持 axis 0..3；result 是 5 维
        # (n_aug, B, C, H, W)，torch.median(dim=0) 会触发
        # "Axis = 4 ... only supports axis = 0, 1, 2, 3" 并把进程 abort。
        if result.shape[0] == 1:
            return result[0]
        if result.ndim > 4 and result.device.type == "mps":
            return result.cpu().median(dim=0).values.to(result.device)
        return torch.median(result, dim=0).values"""


def patch(path, old, new, mark, label):
    with open(path, encoding="utf-8") as f:
        s = f.read()
    if mark in s:
        print(f"  [跳过] {label}（已打过）")
        return False
    if old not in s:
        print(f"  [失败] {label}：找不到目标代码，版本可能变了 → {path}")
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(s.replace(old, new, 1))
    print(f"  [已打] {label}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", default=os.environ.get("SEETHROUGH_NODE_DIR", DEFAULT_NODE))
    a = ap.parse_args()

    nodes = os.path.join(a.node, "nodes.py")
    vae = os.path.join(a.node, "see-through/common/modules/layerdiffuse/vae.py")
    for p in (nodes, vae):
        if not os.path.isfile(p):
            print(f"找不到 {p}")
            return 2

    print(f"目标：{a.node}")
    r1 = patch(nodes, SCHED_OLD, SCHED_NEW, SCHED_MARK, "scheduler 走本地")
    r2 = patch(vae, MEDIAN_OLD, MEDIAN_NEW, MEDIAN_MARK, "MPS median 5 维崩溃")
    if r1 is None or r2 is None:
        return 3
    if r1 or r2:
        print("\n改完要重启 ComfyUI 后端才生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
