"""Export only the five explicitly supplied public demo sources for static hosting.
No generic project enumeration, private stores, credentials, logs or model files.
"""
from pathlib import Path
import json, urllib.request, urllib.error, zipfile
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'apps/web/public/demo-data'
RUNS={
 '355132ce-41b3-5ac2-ab11-76c786ec678d': '/media/jio-short.mp4',
 '97d1bc9b-1efc-5ece-8c8d-e0e14b40d126': '/media/prahaar-trailer.mp4',
 'de3d436e-3243-53bd-a952-cdb989de78a2': '/media/education.mp4',
 '932cae17-a4f4-5653-80d7-da7a47d0fd44': '/media/voice-excerpt.wav',
 'f2ab5388-7bf5-5dbf-ad54-d505a4b9946b': None,
}
BASE='http://127.0.0.1:8765/api/v1'
def get(path):
 with urllib.request.urlopen(BASE+path,timeout=30) as r:return json.load(r)
def clean(v):
 if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if k not in ('api_key','token','authorization','raw_response','prompt','logs','log_tail')}
 if isinstance(v,list):return [clean(x) for x in v]
 if isinstance(v,str) and ('/Users/' in v or '/private/' in v):return '[local path omitted]'
 return v

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 routes={}; assets={}; tasks=[]; projects=[]; known_projects=set()
 for rid,media in RUNS.items():
  prefix='/runs/'+rid
  for suffix in ['', '/transcript','/timeline','/issues','/prediction','/relations','/deepdive','/shots','/ocr']:
   routes[prefix+suffix]=clean(get(prefix+suffix))
  info=routes[prefix];pid=info['project']['project_id'];known_projects.add(pid)
  p=clean(get('/projects/'+pid));p['runs']=[r for r in p['runs'] if r['run_id']==rid];p['active_run_id']=rid
  projects.append(p);routes['/projects/'+pid]=p
  routes['/projects/'+pid+'/pipeline']={'project_id':pid,'state':'imported','workspaces':[]}
  routes['/jobs?project_id='+pid]={'items':[]}
  if media:assets[rid+':'+info['proxy_artifact_id']]=media
  image_ids=set()
  for sh in routes[prefix+'/shots']['items']:
   if sh.get('thumb'):image_ids.add(sh['thumb']['artifact_id'])
  for ocr in routes[prefix+'/ocr']['items']:
   if ocr.get('artifact_id'):image_ids.add(ocr['artifact_id'])
  for issue in routes[prefix+'/issues']['items']:
   for ev in issue['evidence_ids']:
    try:
     item=clean(get(prefix+'/evidence/'+ev));routes[prefix+'/evidence/'+ev]=item
     image_ids.update(f['artifact_id'] for f in item.get('frames',[]))
    except urllib.error.HTTPError:pass
  for aid in image_ids:
   name=rid+'-'+aid+'.jpg';assets[rid+':'+aid]='/app/demo-data/images/'+name
   tasks.append((prefix+'/artifacts/'+aid, OUT/'images'/name))
  files=[];report_paths=[]
  for suffix in ['transcript','prediction','issues','deepdive','relations']:
   aid='demo-'+suffix;name=suffix+'.json';dest=OUT/'reports'/rid/name;dest.parent.mkdir(parents=True,exist_ok=True)
   raw=json.dumps({'demo':'Precomputed public sample. No live analysis.', 'data':routes[prefix+'/'+suffix]},ensure_ascii=False,indent=2).encode();dest.write_bytes(raw)
   files.append({'artifact_id':aid,'name':name,'kind':'report','bytes':len(raw),'stage':suffix,'sha256':'demo-export'})
   assets[rid+':'+aid]='/app/demo-data/reports/'+rid+'/'+name;report_paths.append(dest)
  routes[prefix+'/outputs']={'items':files}
  z=OUT/'reports'/rid/'reports.zip'
  with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as f:
   for p in report_paths:f.write(p,p.name)
  assets[rid+':zip']='/app/demo-data/reports/'+rid+'/reports.zip'
  tr=routes[prefix+'/transcript']['segments']
  txt=OUT/'reports'/rid/'transcript.txt';txt.write_text('\n\n'.join(s['text'] for s in tr))
  assets[rid+':txt']='/app/demo-data/reports/'+rid+'/transcript.txt'
 def image(task):
  path,dest=task;dest.parent.mkdir(parents=True,exist_ok=True)
  if not dest.exists():
   with urllib.request.urlopen(BASE+path,timeout=30) as r:dest.write_bytes(r.read())
 with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(image,tasks))
 routes['/projects']={'items':projects}
 evaluation=clean(get('/evaluation'));evaluation['runs']=[r for r in evaluation['runs'] if r['run_id'] in RUNS];evaluation['unvalidated'].insert(0,'Hosted sample snapshots: no live analysis, audience calibration or accuracy benchmark.')
 routes['/evaluation']=evaluation
 routes['/settings']={'data_dir':'Browser demo — public sample snapshots','pipeline_command':'Run the open-source app locally for fresh analysis','cerebras':{'configured':False,'base_url':'Disabled in hosted demo','model':None},'asr_threads':'Not running','sent_to_cerebras':'Nothing from this hosted site','models':[]}
 manifest={'label':'Precomputed public samples. Browser-only interactions. No live AI or observed audience retention.','routes':routes,'assets':assets}
 (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
 print(json.dumps({'runs':len(RUNS),'public_images':len(tasks),'manifest_bytes':(OUT/'manifest.json').stat().st_size}))
if __name__=='__main__':main()
