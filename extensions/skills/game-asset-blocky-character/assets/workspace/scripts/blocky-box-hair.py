"""Optional community-style box shell and thick hair locks.
Original geometry, using the existing Kit; no community meshes/textures copied.
Reference construction: DDLC Monika, Natsuki, Nekopara Vanilla local examples.
"""
import math
import numpy as np

def add_parts(k,C,P,decals):
    if C.get("hair_detail") == "reference":
        return add_reference_parts(k,C,P,decals)
    if C.get("hair_detail") == "fine":
        return add_fine_parts(k,C,P,decals)
    S=P["head"]; h=S/2; d=P.get("head_d",S)/2; y=P["head_y"]; top=y+S
    scale=S/8
    width=h+0.85*scale; back=d+0.9*scale
    tone=lambda i: ("hair","hair_v1","hair_v2")[i%3]
    k.box("head","Head",[-h,y,-d],[h,top,d],"hair",
          faces={"north":{"mat":"skin","decal":"face"},"down":"skin"})
    k.box("hair_box_cap","Hair",[-width,top-0.6*scale,-d-0.6*scale],
          [width,top+0.75*scale,back],"hair")
    # Closed side and rear shell. The face stays open; all hanging locks overlap it.
    for s in (-1,1):
        xs=sorted([s*(h-0.1*scale),s*width])
        k.box("hair_box_side","Hair",[xs[0],y+0.3*scale,-d-0.15*scale],
              [xs[1],top+0.15*scale,back],"hair")
    end=y+C.get("bob_drop",2.0)*-scale
    k.box("hair_box_back","Hair",[-width,end+0.9*scale,d-0.1*scale],
          [width,top+0.15*scale,back],"hair")
    # Forehead locks: 1-unit depth, alternating lengths, mildly swept to the side.
    jag=C.get("bang_jag",[0.2,0.55,0.8,0.1,0.4,0.85,0.3,0.6])
    n=len(jag)
    for i,a in enumerate(jag):
        x=(-0.5+(i+0.5)/n)*(2*h+0.5*scale)
        to=[x+0.32*scale,y+(4.1-a)*scale,-d-0.68*scale]
        k.beam("bang","Hair",[x-0.3*scale,top+0.4*scale,-d-0.34*scale],to,
               (2*h+0.5*scale)/n*1.08,0.95*scale,tone(i),facing=(0,0,-1),
               faces={"south":"hair_in"},ext=0.2*scale)
    # Back locks extend below the shell with uneven ends, rather than a curved dome.
    for i in range(9):
        x=(-4+(i))*width/4.5
        yend=end+(0.18+0.38*math.sin(i*2.4))*scale
        k.beam("hair_back_strand","Hair",[x*0.96,top-0.5*scale,back],
               [x+0.2*math.sin(i)*scale,yend,back+0.1*scale],
               1.05*scale,0.95*scale,tone(i+1),facing=(0,0,1),ext=0.22*scale)
    # Layered side locks, each with a small outward tip. No real animal ears.
    for s in (-1,1):
        for j in range(4):
            z=-d+0.15*scale+j*(2*d+0.2*scale)/4
            low=y-(0.75+0.2*math.sin(j*1.7))*scale
            p0=[s*(width-0.2*scale),top-1.1*scale,z]
            p1=[s*(width+0.2*scale),low+0.6*scale,z+0.1*scale]
            p2=[s*(width+0.42*scale),low,z+0.22*scale]
            k.beam("hair_side_strand","Hair",p0,p1,1.7*scale,0.95*scale,tone(j),
                   facing=(s,0,0),ext=0.18*scale)
            k.beam("hair_side_tip","Hair",p1,p2,1.15*scale,0.8*scale,tone(j+1),
                   facing=(s,0,0),ext=0.18*scale)
        k.beam("side_lock","Hair",[s*(h-0.05*scale),top-2*scale,-d-0.45*scale],
               [s*(h+0.1*scale),y-1.1*scale,-d-0.38*scale],
               0.9*scale,0.95*scale,"hair_low",facing=(0,0,-1),ext=0.18*scale)
    add_details(k,C,P,decals)

def add_details(k,C,P,decals):
    S=P["head"]; h=S/2; d=P.get("head_d",S)/2; y=P["head_y"]; top=y+S
    scale=S/8
    # Cat-ear-shaped tufts are continuous chestnut hair, not detachable ears.
    if C.get("hair_peaks"):
        for s in (-1,1):
            peak=[s*(h-0.25*scale),top+1.6*scale,0.35*scale]
            for z in (-0.55*scale,0.35*scale,1.25*scale):
                tip=[peak[0],peak[1],z]
                k.beam("hair_peak","Hair",[s*(h-1.9*scale),top+0.15*scale,z],
                       tip,0.95*scale,0.8*scale,"hair",facing=(0,0,-1),ext=0.25*scale)
                k.beam("hair_peak","Hair",tip,[s*(h+0.45*scale),top+0.15*scale,z],
                       0.95*scale,0.8*scale,"hair_v1",facing=(0,0,-1),ext=0.25*scale)
    if C.get("star_hairclips"):
        fine=C.get("hair_detail")=="fine"
        clip_mat="hair_clip" if fine else "red"
        clip_decal="star_red_fine" if fine else "star_red"
        clip_depth=0.98 if fine else 1.32
        for i in range(2):
            cy=y+(4.55+i*1.55)*scale
            k.box("hairclip_star","Hair",[h-1.55*scale,cy-0.75*scale,-d-clip_depth*scale],
                  [h-0.05*scale,cy+0.75*scale,-d-(clip_depth-0.03)*scale],clip_mat,
                  faces={"north":{"mat":clip_mat,"decal":clip_decal}} ,
                  hide=["south","east","west","up","down"])


def add_fine_parts(k,C,P,decals):
    """Fine bob layers using existing beam primitives and alpha-tested pointed tips."""
    S=P["head"]; h=S/2; d=P.get("head_d",S)/2; y=P["head_y"]; top=y+S
    s=S/8; width=h+0.65*s; back=d+0.8*s
    # Exposed forehead should be skin, rather than the legacy brown face-decal fill.
    decals["face"]=[r.replace("h","s") for r in decals["face"]]
    decals["star_red_fine"]=["--r---","rrrrr-","-rrr--","-r-r--","r---r-","------"]
    k.box("head","Head",[-h,y,-d],[h,top,d],"hair",
          faces={"north":{"mat":"skin","decal":"face"},"down":"skin"})
    k.box("hair_box_cap","Hair",[-width,top-0.5*s,-d-0.45*s],
          [width,top+0.62*s,back],"hair")
    for sign in (-1,1):
        xs=sorted([sign*(h-0.04*s),sign*width])
        k.box("hair_box_side","Hair",[xs[0],y+0.35*s,-d+0.08*s],
              [xs[1],top+0.08*s,back],"hair")
    end=y-C.get("bob_drop",2)*s
    k.box("hair_box_back","Hair",[-width,end+0.85*s,d-0.05*s],
          [width,top+0.08*s,back],"hair")
    tone=lambda i: ("hair","hair_v1","hair","hair_low")[i%4]
    # A strand has two inserted links plus a double-sided cutout tip.
    def strand(name,points,w,thick,mat,facing,tip_len=1.15):
        for j,(a,b) in enumerate(zip(points[:-2],points[1:-1])):
            link=k.beam(name,"Hair",a,b,w,thick,mat,facing=facing,ext=0.12*s)
            link["hide"]=["up","down"]
        a,b=points[-2],points[-1]
        delta=np.asarray(b,float)-np.asarray(a,float)
        L=float(np.linalg.norm(delta)); unit=delta/L
        joint=np.asarray(b,float)-unit*min(tip_len*s,L*0.6)
        link=k.beam(name,"Hair",a,joint.tolist(),w,thick,mat,facing=facing,ext=0.13*s)
        link["hide"]=["up","down"]
        # Local face dimensions set decal resolution; both faces share the same taper.
        W=max(2,int(round(w*4)));H=max(3,int(round((min(tip_len*s,L*0.6)+0.14*s)*4)))
        rows=[]
        for r in range(H):
            keep=max(1,int(round(W*(1-0.85*r/max(1,H-1)))))
            left=(W-keep)//2
            rows.append("-"*left+"h"*keep+"-"*(W-left-keep))
        key=name+"_tip_"+str(len(decals))
        decals[key]=rows
        tip=k.beam(name+"_tip","Hair",joint.tolist(),b,w,0.045*s,"hair_tip",
                   facing=facing,ext=0.07*s,
                   faces={"north":{"mat":"hair_tip","decal":key},
                          "south":{"mat":"hair_tip","decal":key}})
        tip["hide"]=["east","west","up","down"]
    # Eleven individually swept fringe locks. Central lock lands between the eyes.
    tips=[(-3.55,3.65),(-2.88,4.45),(-2.15,4.02),(-1.43,4.65),
          (-0.68,4.35),(0.02,3.58),(0.72,4.45),(1.46,4.02),
          (2.18,4.55),(2.88,3.95),(3.57,3.42)]
    for i,(x,drop) in enumerate(tips):
        x*=s; drop*=s
        root=[x*0.88-0.25*s+0.12*math.sin(i)*s,top+(0.28-0.06*abs(x)/s)*s,-d-0.39*s]
        mid=[x*0.96-0.12*s,y+(5.4+0.15*math.sin(i))*s,-d-0.61*s]
        bot=[x+0.08*math.sin(i*1.7)*s,y+drop,-d-0.67*s]
        strand("bang",[root,mid,bot],(0.68 if i not in (0,10) else 0.75)*s,
               0.33*s,tone(i),(0,0,-1),0.65)
    # Crown tracks sweep from an offset part to the forehead/back perimeter.
    for i in range(9):
        x=(-4+float(i))*1.0*s
        p0=[x*0.65-0.3*s,top+0.69*s,-0.4*s]
        for sign in (-1,1):
            p1=[x*0.9,top+0.68*s,sign*1.65*s]
            p2=[x,top+(0.52 if sign<0 else 0.34)*s,sign*(d+(-0.65 if sign<0 else 0.34)*s)]
            for a,b in ((p0,p1),(p1,p2)):
                crown=k.beam("hair_crown_strand","Hair",a,b,0.73*s,0.16*s,tone(i),
                             facing=(0,1,0),ext=0.14*s)
                crown["hide"]=["up","down"]
    # Two depth layers of rear locks, staggered horizontally and vertically.
    for layer,n in ((0,12),(1,10)):
        for i in range(n):
            x=(-0.5+(i+0.5)/n)*(2*width-0.15*s)
            z=back+(0.20 if layer else 0.0)*s
            low=end+(0.25+0.42*math.sin(i*2.13)+layer*0.45)*s
            strand("hair_back_strand",
                   [[x*0.96,top-0.35*s,z],[x,y+(2.1+0.48*math.sin(i*1.7+layer))*s,z+0.21*s],
                    [x+0.27*math.sin(i)*s,low,z+0.43*s]],
                   (0.82 if layer else 0.91)*s,0.34*s,tone(i+layer),(0,0,1),0.7)
    # Layered side locks finish above the arm; alternate tips turn slightly outward.
    for sign in (-1,1):
        for j in range(7):
            z=-d+0.2*s+(j+0.5)*(2*d-0.15*s)/7
            low=y+(0.3+0.2*math.sin(j*1.83))*s
            strand("hair_side_strand",
                   [[sign*(width-0.04*s),top-0.42*s,z],
                    [sign*(width+0.22*s),y+3.1*s,z+0.15*s],
                    [sign*(width+0.38*s),low,z+0.40*s]],
                   1.00*s,0.34*s,tone(j),(sign,0,0),0.65)
        # Slim cheek-framing strands avoid covering the outer eye.
        strand("side_lock",
               [[sign*(h+0.03*s),top-1.6*s,-d-0.65*s],
                [sign*(h+0.10*s),y+2.6*s,-d-0.69*s],
                [sign*(h+0.37*s),y-0.20*s,-d-0.37*s]],
               0.60*s,0.32*s,"hair_low",(0,0,-1),0.75)
    add_details(k,C,P,decals)


def add_reference_parts(k,C,P,decals):
    """Original swept medium-hair geometry, guided by Kasumi illustration and author study.
    No author cube coordinates, UVs, textures or bones are copied.
    """
    S=P["head"];h=S/2;d=P.get("head_d",S)/2;y=P["head_y"];s=S/8;top=y+S
    decals["face"]=[r.replace("h","s") for r in decals["face"]]
    # The face stays full-width around the eyes; the upper skull is genuinely narrower.
    # A tapered forehead surface replaces the former full-width upper head corners.
    k.box("head","Head",[-h,y,-d],[h,y+3.95*s,-0.85*s],"hair",
          faces={"north":{"mat":"skin","decal":"face"},"down":"skin"})
    k.box("head_forehead_core","Head",[-2.62*s,y+3.85*s,-d+0.16*s],
          [2.62*s,y+6.92*s,-0.85*s],"hair")
    fw=max(1,int(round(2*h*P["texel"])))
    fh=max(1,int(round(3.32*s*P["texel"])))
    rows=[]
    for row in range(fh):
        margin=max(0,int(round(3*(1-row/max(1,fh-1)))))
        rows.append("-"*margin+"s"*(fw-2*margin)+"-"*margin)
    decals["forehead_taper"]=rows
    k.box("head_forehead_face","Head",[-h,y+3.8*s,-d-0.025*s],
          [h,y+7.12*s,-d-0.01*s],"skin",
          faces={"north":{"mat":"skin","decal":"forehead_taper"}},
          hide=["south","east","west","up","down"])
    k.box("head_back","Head",[-3.05*s,y+0.15*s,-0.75*s],
          [3.05*s,top-0.6*s,d-0.2*s],"hair")
    k.box("hair_crown_core","Hair",[-2.3*s,top-1.0*s,-2.95*s],
          [2.3*s,top+0.18*s,3.35*s],"hair")
    for sign in (-1,1):
        k.beam("hair_crown_slope","Hair",[sign*2.35*s,top+0.45*s,0.15*s],
               [sign*4.15*s,top-0.85*s,0.15*s],2*d+0.8*s,0.7*s,
               "hair",facing=(sign,0,0),ext=0.2*s)
        xs=sorted([sign*3.25*s,sign*3.88*s])
        k.box("hair_side_core","Hair",[xs[0],y+1.9*s,-1.15*s],
              [xs[1],top-0.9*s,3.35*s],"hair")
    k.beam("hair_crown_back","Hair",[0,top+0.5*s,3.25*s],
           [0,top-0.9*s,4.1*s],6.8*s,0.65*s,"hair",
           facing=(0,0,1),ext=0.22*s)
    k.box("hair_back_core","Hair",[-3.25*s,y-0.45*s,3.15*s],
          [3.25*s,top-0.85*s,3.75*s],"hair")

    def point(p):return [p[0]*s,y+p[1]*s,p[2]*s]
    def curved(name,path,w,thick,mat,facing,tip_len=0.65):
        path=[point(p) for p in path];w*=s;thick*=s;join=min(0.18*s,thick*0.4)
        for a,b in zip(path[:-2],path[1:-1]):
            c=k.beam(name,"Hair",a,b,w,thick,mat,facing=facing,ext=join)
            c["hide"]=["up","down"]
        a,b=map(lambda p:np.asarray(p,float),path[-2:])
        delta=b-a;L=float(np.linalg.norm(delta));tip=min(tip_len*s,L*0.62)
        joint=b-delta/L*tip
        c=k.beam(name,"Hair",a.tolist(),joint.tolist(),w,thick,mat,facing=facing,ext=join)
        c["hide"]=["up","down"]
        W=max(2,int(round(w*4)));H=max(2,int(round((tip+0.16*s)*4)))
        rows=[]
        for row in range(H):
            keep=max(1,int(round(W*(1-0.88*row/max(1,H-1)))))
            left=(W-keep)//2
            rows.append("-"*left+"h"*keep+"-"*(W-left-keep))
        key=name+"_point_"+str(len(decals));decals[key]=rows
        c=k.beam(name+"_tip","Hair",joint.tolist(),b.tolist(),w,0.045*s,"hair_tip",
                 facing=facing,ext=0.08*s,
                 faces={"north":{"mat":"hair_tip","decal":key},
                        "south":{"mat":"hair_tip","decal":key}})
        c["hide"]=["east","west","up","down"]
    # Four broad curved groups sweep away from the off-centre part.
    # Side openings and the three uneven middle ends are the identity cues.
    fringe=[
        ([[1.7,8.38,-3.52],[1.28,6.3,-3.98],[0.62,5.05,-4.13],[-0.12,4.0,-4.12]],1.20,"hair"),
        ([[1.00,8.48,-3.43],[0.50,6.55,-3.93],[-0.28,5.55,-4.10],[-1.0,4.55,-4.09]],1.00,"hair_low"),
        ([[0.15,8.48,-3.42],[-0.72,6.8,-3.92],[-1.6,5.85,-4.04],[-2.24,5.02,-4.02]],1.05,"hair"),
        ([[-1.0,8.15,-3.41],[-2.25,6.6,-3.86],[-3.0,5.6,-3.98],[-3.25,4.8,-3.98]],1.05,"hair_v1")
    ]
    for path,w,mat in fringe:curved("bang_swept",path,w,0.5,mat,(0,0,-1),0.8)
    # Clip-side forelock and opposite cheek lock follow different arcs.
    curved("side_lock_clip",[[2.18,7.6,-3.6],[2.92,6.2,-3.95],[3.58,4.6,-4.1],
                        [3.86,2.2,-3.96],[3.56,0.25,-3.45]],1.05,0.65,"hair",(0,0,-1),0.85)
    curved("side_lock",[[-2.45,7.15,-3.56],[-3.42,5.7,-3.9],[-3.90,3.5,-3.96],
                        [-3.74,1.1,-3.85],[-3.05,-0.1,-3.30]],0.82,0.55,"hair_low",(0,0,-1),0.85)
    # Rear groups bow outward then turn back in, instead of making a straight curtain.
    for i in range(7):
        x=(i-3)*1.1
        out=0.35 if x>=0 else -0.35
        curved("hair_back_strand",[[x*0.88,7.2,4.05],[x,4.0,4.65],
                                   [x+out,1.2,4.85],[x+out*1.5,-1.35+0.35*math.sin(i),4.45]],
               1.22,0.60,"hair" if i%2 else "hair_low",(0,0,1),0.8)
    # Broad side layers end at shoulder height and flick away from the neck.
    for sign in (-1,1):
        for j,z in enumerate([-0.8,1.1,2.75]):
            curved("hair_side_strand",[[sign*4.03,6.3,z],[sign*4.52,3.3,z+0.25],
                                       [sign*4.82,0.45,z+0.6],[sign*(5.38-0.22*j),-0.5+0.16*j,z+0.8]],
                   1.55,0.6,"hair" if j%2 else "hair_low",(sign,0,0),0.75)
        # One smaller outward curl, visible as an isolated hook in the illustration.
        curved("hair_outcurl",[[sign*4.35,3.4,1.9],[sign*5.2,1.2,2.1],
                              [sign*6.05,0.6,2.15],[sign*6.45,1.0,2.02],[sign*6.3,1.55,1.9]],
               0.28,0.18,"hair_low",(0,0,-1),0.32)
    # Star-like hair wings sit low and spread sideways; they do not stand above the crown.
    if C.get("hair_peaks"):
        for sign in (-1,1):
            for z in (0.7,1.55,2.4):
                tip=[sign*4.85*s,y+8.25*s,z*s]
                k.beam("hair_star_wing","Hair",[sign*2.8*s,y+7.0*s,z*s],tip,
                       1.00*s,0.85*s,"hair",facing=(0,0,-1),ext=0.25*s)
                k.beam("hair_star_wing","Hair",tip,[sign*4.2*s,y+6.65*s,z*s],
                       1.00*s,0.85*s,"hair_low",facing=(0,0,-1),ext=0.25*s)
    # Small original red stars on the clip-side lock, at its actual segment surface.
    if C.get("star_hairclips"):
        decals["star_reference"]=["--r--","rrrrr","-rrr-","-r-r-","r---r"]
        for i,(x,cy,z) in enumerate([(2.96,6.18,-4.24),(3.34,5.11,-4.38)]):
            center=point([x,cy,z]);w=0.625*s
            k.box("hairclip_star","Hair",[center[0]-w/2,center[1]-w/2,center[2]-0.02*s],
                  [center[0]+w/2,center[1]+w/2,center[2]+0.02*s],"hair_clip",
                  faces={"north":{"mat":"hair_clip","decal":"star_reference"}},
                  hide=["south","east","west","up","down"])
