"""Check visible coplanar overlapping textured cube faces.
Preserve existing layer order; mirror geometry corrections.
Uses upstream mcbemodelingmasterAI forge.checks.overlap_area.
Set FORGE_TOOLS_DIR to that project's tools directory.
Usage: model.bbmodel [--out report.json] [--fix fixed.bbmodel --mirror --move]
"""
import os, argparse, base64, importlib.util, io, json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from PIL import Image

if os.environ.get('FORGE_TOOLS_DIR'):
    sys.path.insert(0, os.environ['FORGE_TOOLS_DIR'])
from forge.checks import overlap_area  # noqa: E402
_s = importlib.util.spec_from_file_location('bgeom', Path(__file__).with_name('blocky-geometry.py'))
geom = importlib.util.module_from_spec(_s); _s.loader.exec_module(geom)

ap = argparse.ArgumentParser()
ap.add_argument('model'); ap.add_argument('--skip', default='^debris_')
ap.add_argument('--colour-diff', type=float, default=24, help='max channel difference of the two faces\' mean colours')
ap.add_argument('--plane-tol', type=float, default=0.012); ap.add_argument('--min-area', type=float, default=0.03)
ap.add_argument('--out', default=None); ap.add_argument('--fix', default=None); ap.add_argument('--step', type=float, default=0.02)
ap.add_argument('--mirror', action='store_true', help='with --fix: mirror cubes across x=0 keep equal inflate')
ap.add_argument('--offset-tol', type=float, default=5e-5, help='with --fix: faces further apart keep the one in front on top')
ap.add_argument('--move', action='store_true', help='with --fix: cubes may also shift along the normal (not for models '
                'that later steps match by bounding box)')
a = ap.parse_args()
m = json.load(open(a.model, encoding='utf-8'))
skip = re.compile(a.skip) if a.skip else None
G = {g['uuid']: g['name'] for g in m['groups']}; group = {}
def walk(n, g):
    for c in n:
        if isinstance(c, str): group[c] = g
        else: walk(c['children'], G[c['uuid']])
walk(m['outliner'], None)
imgs = [np.asarray(Image.open(io.BytesIO(base64.b64decode(t['source'].split(',')[1]))).convert('RGBA')).astype(float) for t in m['textures']]

def face_colour(f):
    t = f.get('texture')
    if t is None or t >= len(imgs): return None
    img, tt = imgs[t], m['textures'][t]
    sx, sy = img.shape[1] / (tt.get('uv_width') or img.shape[1]), img.shape[0] / (tt.get('uv_height') or img.shape[0])
    u0, v0, u1, v1 = f['uv']
    x0, x1 = sorted([u0 * sx, u1 * sx]); y0, y1 = sorted([v0 * sy, v1 * sy])
    x0, y0 = int(math.floor(x0)), int(math.floor(y0)); x1, y1 = max(int(math.ceil(x1)), x0 + 1), max(int(math.ceil(y1)), y0 + 1)
    px = img[max(0, y0):min(img.shape[0], y1), max(0, x0):min(img.shape[1], x1)].reshape(-1, 4)
    px = px[px[:, 3] >= 128]
    return px[:, :3].mean(0) if len(px) else None

faces = []
for e in m['elements']:
    if e.get('type', 'cube') != 'cube' or (skip and skip.search(e['name'])): continue
    inf = e.get('inflate', 0) or 0
    fr = np.array(e['from'], float) - inf; to = np.array(e['to'], float) + inf
    R = geom.rotation(e.get('rotation')); o = np.array(e.get('origin', [0, 0, 0]), float)
    centre = R @ ((fr + to) / 2 - o) + o
    for fn, f in e['faces'].items():
        if f.get('texture') is None: continue
        quad = np.array([R @ (fr + (to - fr) * np.array(c, float) - o) + o for c in geom.CORNERS[fn]])
        n = np.cross(quad[1] - quad[0], quad[3] - quad[0]); ln = np.linalg.norm(n)
        if ln < 1e-12: continue
        n /= ln
        if n @ (quad.mean(0) - centre) < 0: n = -n
        faces.append(dict(e=e, fn=fn, quad=quad, n=n, d=float(n @ quad.mean(0)), col=face_colour(f)))
buckets = defaultdict(list)
for f in faces: buckets[tuple(np.round(f['n'], 2))].append(f)
visible, same, unknown = [], 0, 0
for grp in buckets.values():
    grp.sort(key=lambda f: f['d'])
    for i, fa in enumerate(grp):
        for fb in grp[i + 1:]:
            if fb['d'] - fa['d'] > a.plane_tol: break
            if fa['e'] is fb['e'] or fa['n'] @ fb['n'] < 0.99995: continue
            ax = (fa['quad'][1] - fa['quad'][0]); ax /= np.linalg.norm(ax); ay = np.cross(fa['n'], ax)
            to2d = lambda q: [(float(p @ ax), float(p @ ay)) for p in q]
            area = overlap_area(to2d(fa['quad']), to2d(fb['quad']))
            if area <= a.min_area: continue
            if fa['col'] is None or fb['col'] is None: unknown += 1; continue
            diff = float(np.abs(fa['col'] - fb['col']).max())
            if diff < a.colour_diff: same += 1; continue
            visible.append(dict(a=f"{group.get(fa['e']['uuid'])}/{fa['e']['name']}", b=f"{group.get(fb['e']['uuid'])}/{fb['e']['name']}",
                                face=fa['fn'], area=round(area, 3), colour_diff=round(diff, 1),
                                a_uuid=fa['e']['uuid'], b_uuid=fb['e']['uuid'], a_d=fa['d'], b_d=fb['d'], n=fa['n'].tolist(),
                                a_area=float(np.linalg.norm(np.cross(fa['quad'][1] - fa['quad'][0], fa['quad'][3] - fa['quad'][0]))),
                                b_area=float(np.linalg.norm(np.cross(fb['quad'][1] - fb['quad'][0], fb['quad'][3] - fb['quad'][0])))))
pairs = Counter(tuple(sorted((v['a'], v['b']))) for v in visible)
print(f'{len(faces)} textured faces; visible z-fight pairs {len(visible)}; same-colour overlaps {same}; no colour {unknown}')
for (x, y), c in pairs.most_common(40): print(f'  {c:3d}  {x}  <->  {y}')
if a.out: json.dump({'visible': visible, 'same_colour_overlaps': same, 'no_colour': unknown}, open(a.out, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
if a.fix:
    by = {e['uuid']: e for e in m['elements']}
    mirror = {}
    if a.mirror:
        def box(e, flip=False):
            f, t, o, r = e['from'], e['to'], e.get('origin', [0, 0, 0]), e.get('rotation', [0, 0, 0])
            if flip: f, t, o, r = [-t[0], f[1], f[2]], [-f[0], t[1], t[2]], [-o[0], o[1], o[2]], [r[0], -r[1], -r[2]]
            return (bool(skip and skip.search(e['name'])),) + tuple(round(v, 2) + 0.0 for v in [*f, *t, *o, *r])
        at = defaultdict(list)
        for e in m['elements']:
            if e.get('type', 'cube') == 'cube': at[box(e)].append(e)
        for e in m['elements']:
            if e.get('type', 'cube') != 'cube' or abs(e['from'][0] + e['to'][0]) < 1e-6 or (skip and skip.search(e['name'])): continue
            other = [c for c in at.get(box(e, True), []) if c is not e]
            if len(other) == 1: mirror[e['uuid']] = other[0]['uuid']
    # Which face goes on top, per face pair. Faces already apart by more than --offset-tol keep the one in front: the
    # references offset such layers on purpose (Ellie 0.0001 / 0.0002, Jenny 0.001-0.012; rotation-baking noise stays
    # below 3.1e-5, 2026-10-14), and lifting the smaller one instead turned the layers round (Jenny's knee slices 0.012
    # behind the shin ended 0.008 in front of it, still inside --plane-tol, and the fix never settled). Truly coplanar
    # faces: the smaller one goes on top; mirror faces have equal areas up to float noise, so near-equal areas are
    # ordered (--mirror) by the pair's first element index, the same on both sides (no left/right cycle).
    order = {e['uuid']: i for i, e in enumerate(m['elements'])}
    canon = lambda u: min(order[u], order.get(mirror.get(u), order[u]))
    def small_big(v):
        x, y = (v['a_uuid'], v['a_area']), (v['b_uuid'], v['b_area'])
        if a.mirror and abs(x[1] - y[1]) <= 1e-3 * max(x[1], y[1]): return (x[0], y[0]) if canon(x[0]) > canon(y[0]) else (y[0], x[0])
        return (x[0], y[0]) if x[1] < y[1] else (y[0], x[0])
    front = lambda v: v['a_uuid'] if v['a_d'] > v['b_d'] else v['b_uuid']
    by_pair = defaultdict(list)
    for v in visible: by_pair[frozenset((v['a_uuid'], v['b_uuid']))].append(v)
    rows, kept, flipped = [], 0, 0           # (top, bottom, normal, how much further the top face has to come out)
    movers = set()                           # --move: only the cubes of pairs that inflate cannot order may shift
    for vs in by_pair.values():
        tops = [front(v) if abs(v['a_d'] - v['b_d']) > a.offset_tol else small_big(v)[0] for v in vs]
        if a.move and len(set(tops)) > 1: movers |= set(tops)
        if not a.move and len(set(tops)) > 1:
            # inflate grows every face of a cube, so it cannot put A on top on one face and B on another (a cube shifted
            # against its neighbour: Manglelie's thigh curves 0.001 off the leg, in front at the back, behind at the
            # front). Without --move the cube whose faces win more overlap area goes on top everywhere.
            won = Counter()
            for v, t in zip(vs, tops): won[t] += v['area']
            tops = [max(won, key=won.get)] * len(vs)
        for v, t in zip(vs, tops):
            b, dt, db = (v['b_uuid'], v['a_d'], v['b_d']) if t == v['a_uuid'] else (v['a_uuid'], v['b_d'], v['a_d'])
            if abs(v['a_d'] - v['b_d']) > a.offset_tol: kept += t == front(v); flipped += t != front(v)
            rows.append((t, b, np.array(v['n']), a.step - (dt - db)))
    # smallest change (linear programme, scipy HiGHS) meeting every row: added inflate s >= 0 moves all faces of a cube
    # out; with --move the cubes of pairs that inflate cannot order may also shift along any axis (twice the cost).
    # Costs are weighted by the cube's surface, so the small part moves (the recipe's "move one part"; unweighted, the
    # programme moved Jenny's whole head 0.018 back instead of lifting a dozen eye and lash decals; with shifts open to
    # every cube it lifted the shoes 0.02 off the ground to avoid an inflate chain). Mirror cubes: equal inflate
    # afterwards, shifts mirrored in x.
    from scipy.optimize import linprog
    inf0 = lambda u: by[u].get('inflate', 0) or 0
    used = {u for r in rows for u in r[:2]} | {u for u, w in mirror.items() if abs(inf0(u) - inf0(w)) > 1e-9}
    used |= {mirror[u] for u in list(used) if u in mirror}
    cubes = sorted(used, key=order.get); ix = {u: i for i, u in enumerate(cubes)}; nv = 7 if a.move else 1
    def surface(u):
        s = np.abs(np.array(by[u]['to'], float) - np.array(by[u]['from'], float)) + 2 * inf0(u)
        return 2 * (s[0] * s[1] + s[1] * s[2] + s[0] * s[2]) + 1e-3
    cost = np.concatenate([surface(u) * np.array([1.0] + [2.0] * (nv - 1)) for u in cubes]) if cubes else np.zeros(0)
    A_ub, b_ub, A_eq, b_eq = [], [], [], []
    for t, b, n, need in rows:               # s_t + n.t_t - s_b - n.t_b >= need, with t = p - q
        r = np.zeros(len(cost)); i, j = ix[t] * nv, ix[b] * nv
        r[i] -= 1; r[j] += 1
        if a.move: r[i + 1:i + 4] -= n; r[i + 4:i + 7] += n; r[j + 1:j + 4] += n; r[j + 4:j + 7] -= n
        A_ub.append(r); b_ub.append(-need)
    for u, w in {tuple(sorted(p, key=order.get)) for p in mirror.items() if p[0] in ix}:
        i, j = ix[u] * nv, ix[w] * nv
        r = np.zeros(len(cost)); r[i] = 1; r[j] = -1; A_eq.append(r); b_eq.append(inf0(w) - inf0(u))   # equal inflate after
        for c, sx in enumerate((-1, 1, 1) if a.move else ()):                        # t_u = (-t_wx, t_wy, t_wz)
            r = np.zeros(len(cost)); r[i + 1 + c] = 1; r[i + 4 + c] = -1; r[j + 1 + c] = -sx; r[j + 4 + c] = sx
            A_eq.append(r); b_eq.append(0)
    movers |= {mirror[u] for u in list(movers) if u in mirror}
    bounds = [(0, None) if k == 0 or u in movers else (0, 0) for u in cubes for k in range(nv)]
    x = np.zeros(0)
    if cubes:
        res = linprog(cost, A_ub=np.array(A_ub) if A_ub else None, b_ub=b_ub or None, A_eq=np.array(A_eq) if A_eq else None,
                      b_eq=b_eq or None, bounds=bounds, method='highs')
        if not res.success:                  # exit 2: nothing written (1 = pairs were visible, the fix was written)
            print(f'no inflate{"/shift" if a.move else ""} meets the layer order: {res.message}', file=sys.stderr); sys.exit(2)
        x = np.where(np.abs(res.x) < 1e-5, 0, np.round(res.x, 6))   # solver residue (1e-6 shifts) is no change
    key = lambda e: (tuple(round(v, 3) for v in e['from']), tuple(round(v, 3) for v in e['to']), tuple(round(v, 3) for v in e.get('rotation', [0, 0, 0])))
    copies = defaultdict(list)
    for e in m['elements']:
        if skip and skip.search(e['name']): copies[key(e)].append(e)
    # faces of zero area are never drawn; inflated from 0 they would become strips sampling whatever texel their UV
    # points at (a closed-surface workflow), so they stay off
    PLANE = {'north': (0, 1), 'south': (0, 1), 'east': (2, 1), 'west': (2, 1), 'up': (0, 2), 'down': (0, 2)}
    rims = 0
    def change(e, s, t):
        off = 0
        if s > 0 and not (e.get('inflate', 0) or 0):
            size = np.abs(np.array(e['to'], float) - np.array(e['from'], float))
            for fn, f in e['faces'].items():
                if f.get('texture') is not None and min(size[k] for k in PLANE[fn]) <= 1e-6: f['texture'] = None; off += 1
        if s > 0: e['inflate'] = round(float((e.get('inflate', 0) or 0) + s), 6)
        if t.any():                          # shifting from, to and the rotation origin together moves the cube in world space
            for k in ('from', 'to', 'origin'): e[k] = [round(float(p + q), 6) for p, q in zip(e.get(k, [0, 0, 0]), t)]
        return off
    bumped = moved = 0
    for u, i in ix.items():
        s, t = x[i * nv], (x[i * nv + 1:i * nv + 4] - x[i * nv + 4:i * nv + 7]) if a.move else np.zeros(3)
        if s <= 0 and not t.any(): continue
        for e in [by[u]] + copies.get(key(by[u]), []): rims += change(e, s, t)
        bumped += int(s > 0); moved += int(t.any())
    top = float(max([by[u].get('inflate', 0) or 0 for u in ix], default=0))
    m.setdefault('zfight_fix', []).append({'step': a.step, 'cubes': bumped, 'moved': moved, 'max_inflate': round(top, 3),
                                           'front_kept': kept, 'front_flipped': flipped, 'rim_faces_off': rims})
    json.dump(m, open(a.fix, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'fix: {bumped} cubes inflated (max {top:.3f}), {moved} moved; offset faces: {kept} keep the one in front, {flipped} '
          f'turned round; {rims} zero-area faces off -> {a.fix}; re-run the check on it')
sys.exit(1 if visible else 0)
