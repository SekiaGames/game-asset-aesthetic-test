"""Reusable stage vest trim, armbands, knee socks and waist ribbon.
Features are driven by character configuration; proportions come from BODY/PRESETS.
"""
import copy
import math
import numpy as np
from scipy.spatial.transform import Rotation

def add_parts(k,C,B,P):
    if not C.get("stage_outfit"): return
    s=P["head"]/8
    top=B["chest_top"]; z=-B["half_d"]-0.07
    waist=next(c for c in k.cubes if c["name"]=="waist")
    low=waist["from"][1]+0.35*s
    # Black vertical trims and white centre ruffle on the fitted vest.
    for x in (-1.75*s,1.75*s):
        k.box("vest_trim","UpperBody",[x-0.28*s,low,z-0.035],[x+0.28*s,top-0.45*s,z],"black",
              hide=["south","east","west","up","down"])
        for cy in (top-1.8*s,low+1.4*s):
            k.box("vest_star","UpperBody",[x-0.63*s,cy-0.63*s,z-0.07],
                  [x+0.63*s,cy+0.63*s,z-0.055],"gold",
                  faces={"north":{"mat":"gold","decal":"star_cut"}},
                  hide=["south","east","west","up","down"])
    k.box("vest_ruffle","UpperBody",[-0.35*s,low,z-0.12],[0.35*s,top-0.8*s,z-0.02],"frill")
    for side,sign in (("Right",1),("Left",-1)):
        grp=side+"Arm"; arm=next(c for c in k.cubes if c["name"] in ("arm_"+side[0],"upper_arm_"+side[0]))
        a,b=arm["from"],arm["to"]; cy=a[1]+0.76*(b[1]-a[1])
        for name,dy0,dy1,mat in [("sleeve_band",-0.65,0.65,"sleeve"),
                               ("sleeve_frill",-0.98,-0.58,"frill"),
                               ("sleeve_frill",0.58,0.98,"frill")]:
            k.box(name,grp,[a[0]-0.16*s,cy+dy0*s,a[2]-0.14*s],
                  [b[0]+0.16*s,cy+dy1*s,b[2]+0.14*s],mat)
        wrist=next((c for c in k.cubes if c["name"]=="forearm_"+side[0]),arm)
        wa,wb=wrist["from"],wrist["to"]; wy=wa[1]+0.9*s
        k.box("bracelet",wrist["group"],[wa[0]-0.035*s,wy,wa[2]-0.035*s],
              [wb[0]+0.035*s,wy+0.28*s,wb[2]+0.035*s],"gold")
    # Colour split preserves the original leg geometry and pivot, including angled strips.
    sock_top=8.5*s if P["body"]=="jenny" else 14*s
    for cube in list(k.cubes):
        if not cube["name"].startswith(("leg_","thigh_","shin_")): continue
        if cube["from"][1]>=sock_top: continue
        lower=copy.deepcopy(cube)
        lower["name"]=k.name("sock")
        lower["to"][1]=min(sock_top,cube["to"][1])
        lower["mat"]="sock"
        cube["from"][1]=sock_top
        if cube["from"][1]<cube["to"][1]: k.cubes.append(lower)
        else:
            cube["mat"]="sock"; cube["from"]=lower["from"]
    for side,sign in (("Right",1),("Left",-1)):
        shoe=next(c for c in k.cubes if c["name"]=="shoe_"+side[0])
        grp=shoe["group"]; xs=[shoe["from"][0],shoe["to"][0]]
        leg=next(c for c in k.cubes if c["name"] in ("leg_"+side[0],"thigh_"+side[0]))
        zsock=leg["from"][2]-0.07; cx=(leg["from"][0]+leg["to"][0])/2
        k.box("boot_cuff",grp,[xs[0],2*s,-1.7*s],[xs[1],3.7*s,2.12*s],"shoe",faces={
            "north":{"mat":"shoe","decal":"boot_edge"}})
        k.box("boot_frill",grp,[xs[0]-0.07*s,1.85*s,-1.77*s],
              [xs[1]+0.07*s,2.3*s,2.2*s],"frill")
        k.box("sock_star",leg["group"],[cx-1.25,sock_top-2.5,zsock-0.02],
              [cx+1.25,sock_top,zsock],"gold",
              faces={"north":{"mat":"gold","decal":"star_large"}},
              hide=["south","east","west","up","down"])
    # Waist bow is offset to the character's left, as in the original illustration.
    cy=waist["from"][1]+0.65*s; cx=-1.5*s; zz=-B["half_d"]-0.38*s
    k.box("waist_bow_knot","UpBody",[cx-0.35*s,cy-0.35*s,zz-0.4*s],
          [cx+0.35*s,cy+0.35*s,zz],"red")
    for sign in (-1,1):
        ax,bx=sorted([cx+sign*0.25*s,cx+sign*1.8*s])
        k.box("waist_bow_loop","UpBody",[ax,cy-0.55*s,zz-0.26*s],
              [bx,cy+0.65*s,zz+0.05*s],"red",
              rotation=[0,0,sign*24],origin=[cx,cy,zz])
        k.beam("waist_bow_tail","UpBody",[cx+sign*0.22*s,cy,zz-0.12*s],
               [cx+sign*0.8*s,cy-2.4*s,zz-1.65*s],0.72*s,0.18*s,
               "red_dark",facing=(0,0,-1),ext=0.18*s)


def fit_chest(k,C,B):
    """Drape the stage vest's surface details over the existing tri chest profile."""
    center=B.get("bust_center")
    if not C.get("stage_outfit") or not center:return
    top,fold=center[:2]
    bottom=(top[0]-5.0,top[1])
    knots=sorted([bottom,fold,top,(B["chest_top"]+1.0,top[1])])
    def z(y):
        return float(np.interp(y,[a for a,b in knots],[b for a,b in knots]))
    def parts(y0,y1):
        return [y1]+[a for a,b in reversed(knots) if y0+1e-5<a<y1-1e-5]+[y0]
    # Surface strips follow each linear cloth panel, keeping their widths and materials.
    for c in list(k.cubes):
        if c["name"].startswith(("vest_trim","vest_ruffle")):
            k.cubes.remove(c)
            x=(c["from"][0]+c["to"][0])/2
            width=c["to"][0]-c["from"][0]
            ys=parts(c["from"][1],c["to"][1])
            for ya,yb in zip(ys,ys[1:]):
                piece=k.beam(c["name"]+"_fit",c["group"],[x,ya,z(ya)-0.09],
                             [x,yb,z(yb)-0.09],width,0.045,c["mat"],
                             facing=(0,0,-1),ext=0.035)
                if c["name"].startswith("vest_trim"):piece["hide"]=["south","east","west","up","down"]
        elif c["name"].startswith("vest_star"):
            k.cubes.remove(c)
            x=(c["from"][0]+c["to"][0])/2
            cy=(c["from"][1]+c["to"][1])/2
            half=(c["to"][1]-c["from"][1])/2
            if abs(cy-fold[0])<half+0.06:cy=fold[0]-half-0.08
            piece=k.beam(c["name"]+"_fit",c["group"],[x,cy+half,z(cy+half)-0.14],
                         [x,cy-half,z(cy-half)-0.14],c["to"][0]-c["from"][0],0.025,
                         c["mat"],facing=(0,0,-1),faces=c.get("faces"),ext=0.0)
            piece["hide"]=["south","east","west","up","down"]
        elif c["name"].startswith("bow_tail"):
            k.cubes.remove(c)
            x=(c["from"][0]+c["to"][0])/2
            y0,y1=c["from"][1],c["to"][1]
            piece=k.beam(c["name"]+"_fit",c["group"],[x,y1,z(y1)-0.57],
                         [x+math.copysign(0.12,x),y0,z(y0)-0.57],
                         c["to"][0]-c["from"][0],0.085,c["mat"],facing=(0,0,-1),ext=0.04)
        elif c["name"].startswith(("bow_knot","bow_loop","bow_gem")):
            c["from"][2]-=0.25;c["to"][2]-=0.25
        elif c["name"].startswith("collar_front"):
            c["from"][2]-=0.22;c["to"][2]-=0.22
    # Waist bow loops hinge at their original attachment and follow the lower cloth slope.
    alpha=math.degrees(math.atan2(fold[1]-bottom[1],fold[0]-bottom[0]))
    for c in k.cubes:
        if c["name"].startswith("waist_bow_loop"):
            beta=c.get("rotation",[0,0,0])[2]
            R=Rotation.from_euler("X",alpha,degrees=True).as_matrix() @ Rotation.from_euler("Z",beta,degrees=True).as_matrix()
            c["rotation"]=Rotation.from_matrix(R).as_euler("ZYX",degrees=True)[::-1].tolist()
