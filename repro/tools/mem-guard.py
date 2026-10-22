#!/usr/bin/env python3
"""ComfyUI 内存看门狗：剩余内存跌破红线就中断当前任务，别让整机被 OOM 拖重启。

    python3 mem-guard.py                      # 默认 http://127.0.0.1:8189，红线 6 GB
    python3 mem-guard.py --min-free-gb 8 --log /tmp/mem-guard.log

为什么需要它：SeeThrough 的 1280 分辨率会同时持有两套 SDXL 管线、21 层 RGBA
图集和 Marigold 的 batch，48 GB 机器上没有余量，macOS 会直接把整机卡死重启
（本项目已发生 3 次，最近一次 2026-10-22 13:31）。进程内的 MemoryError 抓不到，
只能在外部盯 /system_stats 的 ram_free。

红线给 6 GB 是留出「中断 → 释放模型」的时间；真的到 3 GB 以下通常已经来不及。
中断后脚本会再调一次 /free 让 ComfyUI 把模型权重还给系统，并清掉排队的 prompt，
避免下一个任务紧接着又顶上去。

退出条件：连续 --idle-exit 次采样既没有运行中也没有排队任务。
"""
import argparse
import json
import time
import urllib.error
import urllib.request

GB = 1 << 30


def get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def post(url, payload, timeout=10):
    req = urllib.request.Request(
        url, json.dumps(payload).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def ram_free_gb(base):
    d = get(f"{base}/system_stats")["system"]
    return d["ram_free"] / GB, d["ram_total"] / GB


def queue_state(base):
    d = get(f"{base}/queue")
    return len(d.get("queue_running", [])), len(d.get("queue_pending", []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8189")
    ap.add_argument("--min-free-gb", type=float, default=6.0)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--log", default="")
    ap.add_argument("--idle-exit", type=int, default=15,
                    help="连续多少次采样空闲后退出（默认 15 次 ≈ 30s）")
    a = ap.parse_args()

    logf = open(a.log, "a", encoding="utf-8", buffering=1) if a.log else None

    def emit(msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        if logf:
            logf.write(line + "\n")

    emit(f"watch {a.base}  红线 {a.min_free_gb:.1f} GB  间隔 {a.interval}s")
    miss = idle = 0
    low = 0.0
    tripped = False

    while True:
        try:
            free, total = ram_free_gb(a.base)
            running, pending = queue_state(a.base)
            miss = 0
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            miss += 1
            if miss == 1:
                emit(f"连不上后端（{type(e).__name__}），等它回来…")
            if miss > 15:
                emit("后端连续 15 次不可达，退出。若是被 OOM 杀掉，查系统日志 console.log")
                return 2
            time.sleep(a.interval)
            continue

        low = free if low == 0.0 else min(low, free)

        if running or pending:
            idle = 0
            emit(f"free {free:.1f} / {total:.0f} GB  running={running} pending={pending}"
                 f"  本轮最低 {low:.1f}")
            if free < a.min_free_gb and not tripped:
                tripped = True
                emit(f"⚠️ 剩余内存 {free:.1f} GB 低于红线，中断任务")
                try:
                    post(f"{a.base}/interrupt", {})
                    post(f"{a.base}/queue", {"clear": True})
                except Exception as e:  # noqa: BLE001
                    emit(f"中断请求失败：{e}")
        else:
            idle += 1
            if idle == 1:
                emit(f"空闲，本轮最低 {low:.1f} GB（total {total:.0f} GB）")
            if idle >= a.idle_exit:
                try:
                    post(f"{a.base}/free", {"unload_models": True, "free_memory": True})
                    free2, _ = ram_free_gb(a.base)
                    emit(f"已释放模型，free {free:.1f} → {free2:.1f} GB")
                except Exception as e:  # noqa: BLE001
                    emit(f"释放模型失败（不影响结果）：{e}")
                emit("任务结束，退出")
                return 1 if tripped else 0

        time.sleep(a.interval)


if __name__ == "__main__":
    raise SystemExit(main())
