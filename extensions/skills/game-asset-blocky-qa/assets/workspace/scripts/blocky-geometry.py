"""Shared reader: Generic/free .bbmodel -> world-space faces (rest pose).

Blockbench convention: every group and element rotates about its own pivot
(`origin`) by R = Rz*Ry*Rx (degrees), groups nest. Cubes apply `inflate`
(negative values collapse slices; axes are min/max normalised as in the
reference preview), skip faces with `texture: null` or per-face
`visibility: false`. Meshes use their vertex/face lists about `origin`.
Group attributes may live in a `groups` list (older files) or directly on
outliner nodes (newer exports); both are read.
"""
import json
from pathlib import Path
import numpy as np

CORNERS={'north':[(1,0,0),(0,0,0),(0,1,0),(1,1,0)],'south':[(0,0,1),(1,0,1),(1,1,1),(0,1,1)],
         'east':[(1,0,1),(1,0,0),(1,1,0),(1,1,1)],'west':[(0,0,0),(0,0,1),(0,1,1),(0,1,0)],
         'up':[(0,1,1),(1,1,1),(1,1,0),(0,1,0)],'down':[(0,0,0),(1,0,0),(1,0,1),(0,0,1)]}


def rotation(r):
    rx,ry,rz=np.radians(r if r else [0,0,0])
    cx,sx,cy,sy,cz,sz=np.cos(rx),np.sin(rx),np.cos(ry),np.sin(ry),np.cos(rz),np.sin(rz)
    Rx=np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]]);Ry=np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]]);Rz=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])
    return Rz@Ry@Rx


def pivot(r,o):
    """4x4 rotation about pivot o."""
    M=np.eye(4);R=rotation(r);o=np.array(o if o else [0,0,0],float);M[:3,:3]=R;M[:3,3]=o-R@o;return M


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def faces(model,keep=None,skip_groups=()):
    """Yield dict(element, group_path, name, pts[k,3], kind) for every drawn face.
    keep(group_path_list, element) -> bool filters; skip_groups prunes by name."""
    elements={e['uuid']:e for e in model['elements']}
    attrs={g['uuid']:g for g in model.get('groups',[])}
    out=[]
    def walk(node,M,trail):
        g={**attrs.get(node.get('uuid'),{}),**{k:v for k,v in node.items() if k in('name','origin','rotation')}}
        name=g.get('name','');
        if name in skip_groups:return
        M=M@pivot(g.get('rotation'),g.get('origin'));trail=trail+[name]
        for c in node.get('children',[]):
            if isinstance(c,dict):walk(c,M,trail);continue
            e=elements.get(c)
            if e is None or (keep and not keep(trail,e)):continue
            E=M@pivot(e.get('rotation'),e.get('origin'))
            if e.get('type')=='mesh':
                verts=e['vertices']
                for f in e['faces'].values():
                    if f.get('texture') is None:continue
                    p=np.array([verts[k] for k in f['vertices']],float)
                    out.append(dict(element=e,group_path=trail,name=e['name'],kind='mesh',pts=(E[:3,:3]@p.T).T+E[:3,3]))
                continue
            if 'from' not in e:continue
            inf=e.get('inflate',0) or 0
            b=np.array([np.array(e['from'],float)-inf,np.array(e['to'],float)+inf]);lo=b.min(0);size=b.max(0)-lo
            vis=e.get('visibility')
            for fn,f in (e.get('faces') or {}).items():
                if f.get('texture') is None or (isinstance(vis,dict) and vis.get(fn) is False) or vis is False:continue
                p=np.array([lo+np.array(c)*size for c in CORNERS[fn]])
                out.append(dict(element=e,group_path=trail,name=e['name'],kind='cube',face=fn,pts=(E[:3,:3]@p.T).T+E[:3,3]))
    for n in model['outliner']:
        if isinstance(n,dict):walk(n,np.eye(4),[])
    return out


def triangles(fs):
    tris=[]
    for f in fs:
        p=f['pts']
        for i in range(1,len(p)-1):tris.append([p[0],p[i],p[i+1]])
    return np.array(tris) if tris else np.zeros((0,3,3))
