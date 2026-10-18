"""Inventory extracted bbmodels, extending the existing geo/YSM surveys.

Counts stored geometry and actual per-face UV fields, not rendered characters.
Inline and separate group metadata are both supported. No source assets are
copied into the report; only hashes, numbers and structural metadata are kept.
"""
import argparse,base64,collections,csv,hashlib,io,json,statistics
from pathlib import Path
from PIL import Image

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('output');ap.add_argument('roots',nargs='+');a=ap.parse_args()
 rows=[];errors=[]
 for rawroot in a.roots:
  root=Path(rawroot)
  for file in sorted(root.rglob('*.bbmodel')):
   try:
    raw=file.read_bytes();m=json.loads(raw.decode('utf-8-sig'));groups={g['uuid']:g for g in m.get('groups',[])};maxdepth=0;inline=False
    def walk(ns,depth=0):
     nonlocal maxdepth,inline
     for n in ns:
      if isinstance(n,dict):
       inline|='origin' in n or 'name' in n;groups[n['uuid']]={**groups.get(n['uuid'],{}),**n};maxdepth=max(maxdepth,depth+1);walk(n.get('children',[]),depth+1)
    walk(m.get('outliner',[]));es=m.get('elements',[]);cubes=[e for e in es if e.get('type','cube')=='cube'];meshes=[e for e in es if e.get('type')=='mesh']
    planes=inflated_planes=negative=rotated=0
    for e in cubes:
     size=[abs(b-a+2*(e.get('inflate',0) or 0)) for a,b in zip(e['from'],e['to'])]
     plane=min(size)<1e-6;planes+=plane;inflated_planes+=plane and min(abs(b-a) for a,b in zip(e['from'],e['to']))>1e-6
     negative+=(e.get('inflate',0) or 0)<0;rotated+=any(abs(x)>1e-7 for x in e.get('rotation',[]))
    used=null=zerouv=rotateduv=0
    for e in es:
     for f in e.get('faces',{}).values():
      if f.get('texture') is None:null+=1;continue
      used+=1;uv=f.get('uv');rotateduv+=bool(f.get('rotation'))
      if isinstance(uv,list) and len(uv)==4:zerouv+=abs(uv[2]-uv[0])<1e-9 or abs(uv[3]-uv[1])<1e-9
      elif isinstance(uv,dict) and uv:
       ps=list(uv.values());zerouv+=min(max(p[i] for p in ps)-min(p[i] for p in ps) for i in [0,1])<1e-9
    textures=[]
    for t in m.get('textures',[]):
     d=dict(name=t.get('name'),uv=[t.get('uv_width',m.get('resolution',{}).get('width')),t.get('uv_height',m.get('resolution',{}).get('height'))])
     if str(t.get('source','')).startswith('data:image/'):
      png=base64.b64decode(t['source'].split(',',1)[1]);im=Image.open(io.BytesIO(png));d.update(image=list(im.size),sha256=hashlib.sha256(png).hexdigest())
     textures.append(d)
    row=dict(scope=root.name,file=file.relative_to(root).as_posix(),sha256=hashlib.sha256(raw).hexdigest(),format=m.get('meta',{}).get('model_format'),
     elements=len(es),cubes=len(cubes),meshes=len(meshes),groups=len(groups),groupDepth=maxdepth,inlineGroups=inline,
     rotatedGroups=sum(any(abs(x)>1e-7 for x in g.get('rotation',[])) for g in groups.values()),rotatedCubes=rotated,
     planeCubes=planes,planesFromInflate=inflated_planes,negativeInflate=negative,texturedFaces=used,disabledFaces=null,
     zeroSizeUVFaces=zerouv,rotatedUVFaces=rotateduv,boxUVCubes=sum(bool(e.get('box_uv',m.get('meta',{}).get('box_uv'))) for e in cubes),
     animations=len(m.get('animations',[])),textures=textures)
    rows.append(row)
   except Exception as e:errors.append(dict(file=str(file),error=str(e)))
 def summarize(subset):
  return dict(files=len(subset),elements=sum(r['elements'] for r in subset),cubes=sum(r['cubes'] for r in subset),meshes=sum(r['meshes'] for r in subset),
   planeCubes=sum(r['planeCubes'] for r in subset),planesFromInflate=sum(r['planesFromInflate'] for r in subset),negativeInflate=sum(r['negativeInflate'] for r in subset),
   zeroSizeUVFaces=sum(r['zeroSizeUVFaces'] for r in subset),texturedFaces=sum(r['texturedFaces'] for r in subset),
   filesWithPlanes=sum(r['planeCubes']>0 for r in subset),filesWithZeroUV=sum(r['zeroSizeUVFaces']>0 for r in subset),
   filesWithMeshes=sum(r['meshes']>0 for r in subset),filesWithAnimations=sum(r['animations']>0 for r in subset),
   medianElements=statistics.median(r['elements'] for r in subset),maxElements=max(r['elements'] for r in subset),maxGroupDepth=max(r['groupDepth'] for r in subset))
 subgroups=collections.defaultdict(list)
 for r in rows:subgroups[r['scope']+'/'+r['file'].split('/')[0]].append(r)
 report=dict(summary=summarize(rows),byCollection={k:summarize(v) for k,v in subgroups.items()},models=rows,errors=errors,
  semantics='Stored elements/variants, not unique characters or visible default pose. GLB/HTML are alternate exports and not counted again.')
 out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 fields=[k for k in rows[0] if k!='textures']
 with out.with_suffix('.csv').open('w',newline='',encoding='utf-8-sig') as stream:
  writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
 print(json.dumps(dict(summary=report['summary'],byCollection=report['byCollection'],errors=errors),ensure_ascii=True))

if __name__=='__main__':main()
