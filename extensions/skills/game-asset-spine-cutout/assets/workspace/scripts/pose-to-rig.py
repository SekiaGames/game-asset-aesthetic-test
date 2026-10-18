"""Turn DWPose keypoints of a looping side-view clip into a cutout-rig animation (spine-cutout-rig.py
bone names and conventions).

Usage: python -I scripts/pose-to-rig.py \
    <loop poses.json> <rest poses.json> <out anim.json> [--name run_video] [--fps 24] [--harmonics 4] [--elbow-harmonics 2] [--keys 24]

<loop poses.json>: pose-extract.py output for a clip whose last frame flows into its first (e.g. the
17-frame RR_loop found by sprite-postprocess.py loopsearch). <rest poses.json>: the standing pose the
rig parts were cut from (baseline for torso lean).

Angles: limbs measured from straight down (+ = tip forward, the character faces right), lower limbs
relative to the upper ones. Side views confuse DWPose: it swaps near/far limbs, and sometimes even a
single knee or ankle (a knee paired with the other leg's ankle, or both ankles on one foot). So no
frame-to-frame tracking: one periodic curve per joint is fitted, the near limb plays it at phase u and
the far limb at u + 1/2, and each frame only decides which of its detections fits the near/far slot
best (alternating fit/assign). Pairings that bend a knee forward or an elbow backward are discarded.
Two hypotheses are fitted and the one with the lower residual kept: the clip is one full stride
(curve period = clip) or one step (period = 2 x clip, near/far trade places at the loop point).
Writes {"<name>": {"bones": {...}}, "_diagnostics": {...}} in Spine 4.2 timeline format.
"""
import argparse
import json
import math

import numpy as np

# OpenPose-18 indices
NECK, RSH, REL, RWR, LSH, LEL, LWR, RHIP, RKNE, RANK, LHIP, LKNE, LANK = 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13
# rig geometry from spine-cutout-rig.py (kurumi): hip bone 471 above the feet, leg joints 72 below it,
# THIGH_LEN 180, knee to sole 223 (leg image height 273 - KNEE_Y 50)
HIP_UP, HIP_TO_JOINT, THIGH, SHIN_TO_SOLE = 471, 72, 180, 223
LEG_LEN_RIG = THIGH + SHIN_TO_SOLE
NAN2 = (np.nan, np.nan)


def P(kp, i):
    k = kp[i]
    return None if k is None else np.array(k[:2], float)


def down_angle(a, b):
    """Angle of a→b from straight down, degrees; + when b is in front (+x) of a."""
    v = b - a
    return math.degrees(math.atan2(v[0], v[1]))


def mid(a, b):
    return None if a is None or b is None else (a + b) / 2


def candidates(kp, roots, mids, ends, bend, min_score=0.3):
    """Every way to pair the two mid joints and the two end joints with the two roots, as
    [(chain0, chain1)] with chain = (upper, rel) or NaNs. A chain bending the wrong way (sign
    opposite to `bend`: legs -1, arms +1) by more than 10 degrees is discarded as a mis-pairing."""
    out = []
    for m in (mids, mids[::-1]):
        for e in (ends, ends[::-1]):
            chains = []
            for r, mi, en in zip(roots, m, e):
                if None in (kp[r], kp[mi], kp[en]) or min(kp[mi][2], kp[en][2]) < min_score:
                    chains.append(NAN2)
                    continue
                up = down_angle(P(kp, r), P(kp, mi))
                rel = (down_angle(P(kp, mi), P(kp, en)) - up + 180) % 360 - 180
                chains.append(NAN2 if bend * rel < -10 else (up, rel))
            out.append(tuple(chains))
    return out


def design(u, H):
    cols = [np.ones_like(u)]
    for k in range(1, H + 1):
        cols += [np.cos(2 * np.pi * k * u), np.sin(2 * np.pi * k * u)]
    return np.stack(cols, 1)


def evalf(c, u):
    return design(np.asarray(u, float) % 1.0, (len(c) - 1) // 2) @ c


def robust_fit(u, y, H, iters=2):
    """Periodic least squares at sample phases u; NaNs skipped, outliers > max(2.5 MAD, 8 deg) dropped."""
    A = design(u % 1.0, H)
    ok = ~np.isnan(y)
    for _ in range(iters + 1):
        c, *_ = np.linalg.lstsq(A[ok], y[ok], rcond=None)
        r = np.abs(y - A @ c)
        ok = ~np.isnan(y) & (r <= max(2.5 * 1.4826 * np.nanmedian(r[~np.isnan(y)]), 8.0))
    return c, ok


def fit_limb(cands, period, H, iters=15, H_lower=None):
    """Alternate: assign each frame's detections to near (phase u) / far (u + 1/2), then refit.
    period = curve period in clip lengths (1: clip is a full stride, 2: clip is one step).
    H_lower: harmonics for the lower-limb curve (fewer for noisy elbows)."""
    H_lower = H_lower or H
    n = len(cands)
    u = np.arange(n) / (n * period)
    best = None
    for phase0 in np.linspace(0, 1, 12, endpoint=False):    # a few starting guesses
        # start: upper limb swings +-30 deg around 8 deg with this phase; lower limb unknown
        cu = np.zeros(2 * H + 1)
        cu[0] = 8
        cu[1:3] = 30 * np.array([math.sin(2 * np.pi * phase0), math.cos(2 * np.pi * phase0)])
        cr = np.zeros(2 * H_lower + 1)
        cr_set = False
        for _ in range(iters):
            pred = [(evalf(cu, [x])[0], evalf(cr, [x])[0], evalf(cu, [x + .5])[0], evalf(cr, [x + .5])[0]) for x in u]
            near, far = [], []
            for (pu0, pr0, pu1, pr1), cs in zip(pred, cands):
                opts = []
                for c0, c1 in cs:
                    for a, b in ((c0, c1), (c1, c0)):
                        d = 0.0
                        for (au, ar), (qu, qr) in ((a, (pu0, pr0)), (b, (pu1, pr1))):
                            d += 900.0 if np.isnan(au) else (au - qu) ** 2 + (ar - qr) ** 2 * (1.0 if cr_set else 0.0)
                        opts.append((d, a, b))
                _, a, b = min(opts, key=lambda o: o[0])
                near.append(a), far.append(b)
            uu = np.r_[u, u + 0.5]
            yu = np.r_[[a[0] for a in near], [b[0] for b in far]]
            yr = np.r_[[a[1] for a in near], [b[1] for b in far]]
            cu, oku = robust_fit(uu, yu, H)
            cr, okr = robust_fit(uu, yr, H_lower)
            cr_set = True
        res_u = np.nanstd((yu - design(uu % 1, H) @ cu)[oku])
        res_r = np.nanstd((yr - design(uu % 1, H_lower) @ cr)[okr])
        score = res_u + res_r + 50.0 * (np.mean(~oku) + np.mean(~okr))
        if best is None or score < best[0]:
            best = (score, cu, cr, res_u, res_r, int((~oku).sum()), int((~okr).sum()), yu, yr, uu)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("loop")
    ap.add_argument("rest")
    ap.add_argument("out")
    ap.add_argument("--name", default="run_video")
    ap.add_argument("--fps", type=float, default=24)
    ap.add_argument("--harmonics", type=int, default=4)
    ap.add_argument("--keys", type=int, default=24)
    ap.add_argument("--elbow-harmonics", type=int, default=2, help="elbows are half hidden and noisy")
    a = ap.parse_args()

    frames = [f["kp"] for f in json.load(open(a.loop))]
    rest = json.load(open(a.rest))[0]["kp"]
    n, H = len(frames), a.harmonics

    def torso_lean(kp):
        hipm, nk = mid(P(kp, RHIP), P(kp, LHIP)), P(kp, NECK)
        if hipm is None or nk is None:
            return np.nan
        v = nk - hipm
        return math.degrees(math.atan2(v[0], -v[1]))  # + = leaning forward

    leg_c = [candidates(kp, (RHIP, LHIP), (RKNE, LKNE), (RANK, LANK), -1) for kp in frames]
    arm_c = [candidates(kp, (RSH, LSH), (REL, LEL), (RWR, LWR), +1) for kp in frames]
    diag = {"frames": n, "harmonics": H, "hypotheses": {}}
    fits = {}
    for period in (1, 2):
        lf, af = fit_limb(leg_c, period, H), fit_limb(arm_c, period, H, H_lower=a.elbow_harmonics)
        diag["hypotheses"][f"period={period}x clip"] = {
            "leg resid deg (thigh, knee)": [round(lf[3], 1), round(lf[4], 1)],
            "leg outliers (thigh, knee) of 2n": [lf[5], lf[6]],
            "arm resid deg (upper, elbow)": [round(af[3], 1), round(af[4], 1)],
            "arm outliers (upper, elbow) of 2n": [af[5], af[6]]}
        fits[period] = (lf, af)
    period = min(fits, key=lambda p: fits[p][0][0])           # decided by the legs (arms half hidden)
    lf, af = fits[period]
    diag["chosen_period_x_clip"] = period
    cycle = n * period / a.fps
    diag["cycle_s"] = round(cycle, 4)

    u = np.arange(n) / (n * period)
    lean = np.array([torso_lean(kp) for kp in frames]) - torso_lean(rest)
    L = np.median([np.linalg.norm(P(kp, k) - P(kp, h)) + np.linalg.norm(P(kp, an) - P(kp, k))
                   for kp in frames for h, k, an in ((RHIP, RKNE, RANK), (LHIP, LKNE, LANK))
                   if kp[h] and kp[k] and kp[an]])
    hip_up = np.array([np.nan if mid(P(kp, RHIP), P(kp, LHIP)) is None else -mid(P(kp, RHIP), P(kp, LHIP))[1] / L
                       for kp in frames])
    hip_up -= np.nanmean(hip_up)
    # torso lean and hip bob repeat every step (half a stride): duplicate samples half a cycle on
    c_lean, _ = robust_fit(np.r_[u, u + .5], np.r_[lean, lean], H)
    c_hip, _ = robust_fit(np.r_[u, u + .5], np.r_[hip_up, hip_up], H)
    diag["torso_lean_deg"] = [round(float(np.nanmin(lean)), 1), round(float(np.nanmax(lean)), 1)]
    diag["hip_bob_leglen"] = [round(float(np.nanmin(hip_up)), 3), round(float(np.nanmax(hip_up)), 3)]

    keys = a.keys
    us = np.arange(keys + 1) / keys
    times = us * cycle
    us[-1] = 0.0
    tl = {}

    def put(bone, ch, vals):
        if ch == "rotate":
            tl.setdefault(bone, {})[ch] = [{"time": round(float(t), 4), "value": round(float(v), 3)} for t, v in zip(times, vals)]
        else:
            tl.setdefault(bone, {})[ch] = [{"time": round(float(t), 4), "x": 0, "y": round(float(v), 3)} for t, v in zip(times, vals)]

    for side, sh in (("near", 0.0), ("far", 0.5)):
        put(f"{side}-upper-leg", "rotate", evalf(lf[1], us + sh))
        put(f"{side}-lower-leg", "rotate", evalf(lf[2], us + sh))
        put(f"{side}-upper-arm", "rotate", evalf(af[1], us + sh))
        put(f"{side}-lower-arm", "rotate", evalf(af[2], us + sh))
    put("torso", "rotate", -evalf(c_lean, us))   # rig: forward lean is negative

    # hip: video bob + a constant so the lowest sole over the cycle just touches the ground.
    # Rig legs hang from the hip bone (no hip rotation): sole height = HIP_UP + y - HIP_TO_JOINT
    #   - THIGH*cos(thigh) - SHIN_TO_SOLE*cos(thigh + knee)
    ud = np.linspace(0, 1, 360, endpoint=False)
    bob = evalf(c_hip, ud) * LEG_LEN_RIG
    soles = []
    for sh in (0.0, 0.5):
        th, kn = np.radians(evalf(lf[1], ud + sh)), np.radians(evalf(lf[2], ud + sh))
        soles.append(HIP_UP + bob - HIP_TO_JOINT - THIGH * np.cos(th) - SHIN_TO_SOLE * np.cos(th + kn))
    lift = -float(np.min(np.minimum(*soles)))
    diag["hip_lift_px"] = round(lift, 1)
    put("hip", "translate", evalf(c_hip, us) * LEG_LEN_RIG + lift)

    for nm, c in (("thigh", lf[1]), ("knee", lf[2]), ("upper_arm", af[1]), ("elbow", af[2]), ("torso_lean", c_lean)):
        v = evalf(c, ud)
        diag[f"curve_{nm}_deg"] = [round(float(v.min()), 1), round(float(v.max()), 1)]
    with open(a.out, "w") as f:
        json.dump({a.name: {"bones": tl}, "_diagnostics": diag,
                   "_samples": {"leg": {"u": lf[9].tolist(), "thigh": np.nan_to_num(lf[7], nan=-999).tolist(),
                                        "knee": np.nan_to_num(lf[8], nan=-999).tolist()},
                                "arm": {"u": af[9].tolist(), "upper": np.nan_to_num(af[7], nan=-999).tolist(),
                                        "elbow": np.nan_to_num(af[8], nan=-999).tolist()}}}, f, indent=1)
    print(json.dumps(diag, indent=1))


if __name__ == "__main__":
    main()
