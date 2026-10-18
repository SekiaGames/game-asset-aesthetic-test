"""Find stair-step ledges in a model's silhouette (front and side).

Rule from mcbemodelingmasterAI (docs/03-shape-rules.md, "No stair steps"):
curves are tilted links joined corner to corner, never boxes of decreasing
size. A ledge shows as the silhouette edge jumping sideways within one
raster row. Selected faces (regex on element and group names) are drawn into
front (x,y) and side (z,y) silhouettes at `--px` pixels per unit; for each
row the outer edges are taken; a jump of at least `--step` units between
neighbouring rows inside [--y0, --y1] is reported. A smooth slope moves the
edge by slope/px per row, so a 0.3 step at 16 px/unit means a local slope
steeper than ~78 degrees (an overhang/shelf).
Usage: blocky-step-check.py model.bbmodel [--include REGEX] [--exclude REGEX]
"""
import argparse,importlib.util,json,re
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

spec=importlib.util.spec_from_file_location('geom',Path(__file__).with_name('blocky-geometry.py'));geom=importlib.util.module_from_spec(spec);spec.loader.exec_module(geom)
DEFAULT_EXCLUDE=r'(?i)(hair|bang|lock|ahoge|maid|head|face|eye|iris|lash|brow|blush|glint|ear|mouth|arm|hand|leg|shin|shoe|foot|knee|tail|fin|wing|item|weapon|custom|cloth|armor)'


def silhouette(fs,axis,px,bounds):
    (u0,u1),(y0,y1)=bounds;W=int(np.ceil((u1-u0)*px))+2;H=int(np.ceil((y1-y0)*px))+2
    im=Image.new('1',(W,H),0);d=ImageDraw.Draw(im)
    for f in fs:
        p=f['pts'];poly=[((q[axis]-u0)*px,(y1-q[1])*px) for q in p]
        d.polygon(poly,fill=1)
    return np.array(im,bool),(u0,y1,px)


def edges(mask,frame):
    u0,y1,px=frame;rows=[]
    for r in range(mask.shape[0]):
        cols=np.flatnonzero(mask[r]);rows.append((y1-r/px,(cols.min()/px+u0,cols.max()/px+u0) if len(cols) else None))
    return rows


def ledges(rows,step,yr,run,px):
    """Jumps >= step between neighbouring rows. It is a stair when the side
    that sticks out is a box face (a straight vertical edge for `run` units):
    a collar slab wider than the torso. A rounded overhang (under the bust,
    under the buttocks) sticks out with a curve, so it is not a stair."""
    n=int(round(run*px));found=[]
    for i in range(len(rows)-1):
        (ya,a),(yb,b)=rows[i],rows[i+1]
        if a is None or b is None or not (yr[0]<=ya<=yr[1] and yr[0]<=yb<=yr[1]):continue
        for side,k in (('low',0),('high',1)):
            jump=b[k]-a[k]
            if abs(jump)<step:continue
            above=[r[1][k] for r in rows[max(0,i-n+1):i+1] if r[1] is not None]
            below=[r[1][k] for r in rows[i+1:i+1+n] if r[1] is not None]
            flat=lambda v:len(v)==n and np.ptp(v)<=1/px+1e-9
            outward_below=(jump>0)==(k==1)
            straight=flat(below if outward_below else above)
            found.append(dict(y=round((ya+yb)/2,3),side=side,jump=round(float(jump),3),edge=[round(a[k],3),round(b[k],3)],stair=bool(straight)))
    return found


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('model')
    ap.add_argument('--include',default='.*');ap.add_argument('--exclude',default=DEFAULT_EXCLUDE)
    ap.add_argument('--px',type=float,default=16);ap.add_argument('--step',type=float,default=.3)
    ap.add_argument('--run',type=float,default=.375,help='straight edge length each side that makes a jump a stair')
    ap.add_argument('--y0',type=float,default=None);ap.add_argument('--y1',type=float,default=None)
    ap.add_argument('--skip-groups',default='steve,items');ap.add_argument('--save',default=None,help='write silhouettes PNG')
    a=ap.parse_args();m=geom.load(a.model)
    inc,exc=re.compile(a.include),re.compile(a.exclude) if a.exclude else None
    keep=lambda trail,e:inc.search(e['name']) and not (exc and (exc.search(e['name']) or any(exc.search(t) for t in trail[2:])))
    fs=geom.faces(m,keep=keep,skip_groups=set(filter(None,a.skip_groups.split(','))))
    if not fs:raise SystemExit('no faces selected')
    pts=np.concatenate([f['pts'] for f in fs]);lo,hi=pts.min(0),pts.max(0)
    report=dict(model=str(a.model),faces=len(fs),bounds=[lo.round(3).tolist(),hi.round(3).tolist()],step=a.step,px=a.px,run=a.run,views={})
    images=[];rows_by_view={}
    for view,axis in (('front',0),('side',2)):
        mask,frame=silhouette(fs,axis,a.px,((lo[axis],hi[axis]),(lo[1],hi[1])));rows_by_view[view]=edges(mask,frame);images.append(Image.fromarray(mask))
    # The neck/shoulder-top junction is a deliberate cap: stop just below the
    # largest front jump in the top quarter unless --y1 is given.
    top=lo[1]+.75*(hi[1]-lo[1]);cap=None
    if a.y1 is None:
        cands=ledges(rows_by_view['front'],a.step,(top,hi[1]),a.run,a.px)
        if cands:cap=max(cands,key=lambda f:abs(f['jump']))['y']
    y1=a.y1 if a.y1 is not None else (cap-1.5/a.px if cap else hi[1]-.25);report['neckCap']=cap
    bottom=lo[1]+.25*(hi[1]-lo[1])
    for view,rows in rows_by_view.items():
        # Likewise the lower end of the selection (where excluded legs begin),
        # found per view: a crotch edge may only show from the side.
        floor=None
        if a.y0 is None:
            cands=[f for f in ledges(rows,a.step,(lo[1],bottom),a.run,a.px) if abs(f['jump'])>=1]
            if cands:floor=max(cands,key=lambda f:f['y'])['y']
        yr=(a.y0 if a.y0 is not None else (floor+1.5/a.px if floor else lo[1]+.25),y1)
        found=ledges(rows,a.step,yr,a.run,a.px);stairs=[f for f in found if f['stair']]
        report['views'][view]=dict(yRange=[round(v,3) for v in yr],bottomCap=floor,stairs=len(stairs),stairList=stairs[:12],otherJumps=len(found)-len(stairs),
                                   largestOther=sorted([f for f in found if not f['stair']],key=lambda f:-abs(f['jump']))[:4])
    report['stairs']=sum(v['stairs'] for v in report['views'].values())
    if a.save:
        W=sum(i.width for i in images)+10;H=max(i.height for i in images);canvas=Image.new('L',(W,H),40);x=0
        for i in images:canvas.paste(i.convert('L'),(x,0));x+=i.width+10
        canvas.save(a.save)
    print(json.dumps(report,indent=1))
    raise SystemExit(1 if report['stairs'] else 0)


if __name__=='__main__':main()
