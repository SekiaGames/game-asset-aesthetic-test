"""命令行入口。子命令：

    doctor                          检查环境（ComfyUI 目录 / 镜像 / 依赖 / 磁盘）
    list                            列出 Manager 清单里能直接下的模型（可按关键字过滤）
    missing <workflow.json>         只报告缺失的模型和来源，不下载
    fill <workflow.json>            下载所有缺失项（--yes 跳过确认）
    get <url|repo> [path]           直接下一个（URL 或 repo + repo内路径）
"""
import argparse
import json
import os
import shutil
import sys
import urllib.request

from . import config, fetch, sources


def _hr(title):
    print(f"\n{title}")
    print("-" * len(title))


def cmd_doctor(a):
    comfy = config.comfy_dir(a.comfy)
    ep = config.endpoint(a.endpoint)
    _hr("环境")
    print(f"python        {sys.executable}")
    try:
        import huggingface_hub
        print(f"hub           {huggingface_hub.__version__}")
    except Exception:                                           # noqa: BLE001
        print("hub           缺失（用 ComfyUI 自带的 python 跑，见 run.command）")
    print(f"ComfyUI       {comfy or '未找到（用 --comfy 指定）'}")
    print(f"镜像          {ep}")
    if comfy:
        m = config.models_dir(comfy)
        print(f"models        {m}")
        print(f"磁盘余量      {config.free_gb(m):.0f} GB")
        print(f"已有模型      {len(sources.local_files(m))} 个文件")
    _hr("镜像连通性")
    try:
        req = urllib.request.Request(ep + "/api/models?limit=1",
                                     headers={"User-Agent": "dltool/0.1"})
        with urllib.request.urlopen(req, timeout=8) as r:
            print(f"GET {ep}/api/models  {r.status}")
    except Exception as e:                                      # noqa: BLE001
        print(f"GET {ep}/api/models  失败：{e}")
    return 0


def cmd_list(a):
    comfy = config.comfy_dir(a.comfy)
    if not comfy:
        print("找不到 ComfyUI 目录")
        return 2
    idx = sources.manager_index(comfy)
    rows = [(e.get("filename"), e.get("size"), e.get("type")) for e in idx.values()]
    if a.filter:
        f = a.filter.lower()
        rows = [r for r in rows if f in (r[0] or "").lower()]
    for fn, size, typ in sorted(rows)[: a.limit]:
        print(f"{str(size or ''):>9}  {str(typ or ''):<16} {fn}")
    print(f"\n共 {len(rows)} 条（显示前 {min(len(rows), a.limit)}）")
    return 0


def _scan(a):
    comfy = config.comfy_dir(a.comfy)
    if not comfy:
        print("找不到 ComfyUI 目录，用 --comfy 指定")
        return None, None, None
    wf = a.workflow
    if os.path.isdir(wf):
        wfs = config.workflows(comfy)
        if not wfs:
            print("没有工作流文件")
            return None, None, None
        wf = wfs[0]
        print(f"用最近的工作流：{wf}")
    names, urls = sources.from_workflow(wf)
    have = sources.local_files(config.models_dir(comfy))
    ep = config.endpoint(a.endpoint)
    rows = []
    for n in names:
        r = sources.resolve(comfy, n, urls, endpoint=ep)
        r["present"] = n.lower() in have
        rows.append(r)
    return comfy, rows, wf


def cmd_missing(a):
    comfy, rows, wf = _scan(a)
    if rows is None:
        return 2
    _hr(f"缺失检查：{os.path.basename(wf)}")
    miss = [r for r in rows if not r["present"]]
    for r in rows:
        tag = "有" if r["present"] else ("缺·可下" if r["url"] else "缺·无源")
        print(f"[{tag:6s}] {r['filename']:<52} -> models/{r['subdir'] or '?'}  ({r['source'] or '无'})")
    print(f"\n共 {len(rows)} 个引用，缺 {len(miss)} 个")
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    return 0


def cmd_fill(a):
    comfy, rows, wf = _scan(a)
    if rows is None:
        return 2
    todo = [r for r in rows if not r["present"] and r["url"]]
    no_src = [r for r in rows if not r["present"] and not r["url"]]
    if no_src:
        print("以下文件找不到下载源，需要手工指定 URL：")
        for r in no_src:
            print("  -", r["filename"])
    if not todo:
        print("没有需要下载的项。")
        return 0
    print(f"准备下载 {len(todo)} 个文件：")
    for r in todo:
        print(f"  - {r['filename']}  ({r['repo']}/{r['path']})")
    if not a.yes:
        if input("\n继续？[y/N] ").strip().lower() not in ("y", "yes"):
            print("已取消")
            return 1
    models = config.models_dir(comfy)
    ep = config.endpoint(a.endpoint)
    ok = 0
    for i, r in enumerate(todo, 1):
        print(f"\n[{i}/{len(todo)}] {r['filename']}")
        try:
            p = fetch.download(ep, r["repo"], r["path"], models, to=(r["subdir"] if a.flat else None))
            print(f"  -> {p}")
            ok += 1
        except Exception as e:                                  # noqa: BLE001
            print(f"  失败：{e}")
            if a.stop_on_error:
                return 3
    print(f"\n完成 {ok}/{len(todo)}")
    return 0 if ok == len(todo) else 3


def cmd_get(a):
    comfy = config.comfy_dir(a.comfy)
    if not comfy:
        print("找不到 ComfyUI 目录")
        return 2
    ep = config.endpoint(a.endpoint)
    target = a.target
    if "://" in target:
        u = target.replace("https://huggingface.co", ep)
        repo, path = sources.parse_url(u)
        if not repo:
            print("URL 解析失败，需要 .../<repo>/resolve/<rev>/<path> 形式")
            return 2
    else:
        repo, path = target, a.path
        if not path:
            print("用法：get <repo> <repo内路径>  或  get <url>")
            return 2
    models = config.models_dir(comfy)
    if not a.to and "/" not in path:      # repo 根目录的权重 → 默认放 checkpoints
        a.to = "checkpoints"
    print(f"{repo} :: {path}")
    print(f"-> {os.path.join(models, a.to or '')}")
    p = fetch.download(ep, repo, path, models, to=a.to)
    print("完成", p)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dl", description="独立的模型下载工具（不依赖工作流）")
    ap.add_argument("--comfy", help="ComfyUI 目录（含 models/）")
    ap.add_argument("--endpoint", help="HF 镜像，默认 hf-mirror.com")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="检查环境")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("list", help="列出 Manager 清单里的模型")
    p.add_argument("--filter", help="按文件名过滤")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("missing", help="检查某个工作流缺哪些模型")
    p.add_argument("workflow", help="工作流 JSON 或目录（默认取最近一个）")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_missing)

    p = sub.add_parser("fill", help="下载工作流缺失的模型")
    p.add_argument("workflow")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--flat", action="store_true", help="按解析出的子目录放（默认保持 repo 内路径）")
    p.add_argument("--stop-on-error", action="store_true")
    p.set_defaults(func=cmd_fill)

    p = sub.add_parser("get", help="直接下一个模型")
    p.add_argument("target", help="HF URL 或 repo id")
    p.add_argument("path", nargs="?", help="repo 内路径（target 是 repo id 时必填）")
    p.add_argument("--to", help="存到 models/<子目录>（默认保持 repo 内路径）")
    p.set_defaults(func=cmd_get)

    a = ap.parse_args(argv)
    if not a.comfy:
        a.comfy = os.environ.get("COMFYUI_DIR")
    return a.func(a)
