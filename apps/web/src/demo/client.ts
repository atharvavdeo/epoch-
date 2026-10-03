import type { Prediction, Issue, Segment } from '../api';
export const DEMO = import.meta.env.VITE_DEMO === 'true';
export const DEMO_BASE = '/app/';
type Manifest = { routes: Record<string, unknown>; assets: Record<string, string> };
let data: Manifest | undefined;
let loading: Promise<Manifest> | undefined;
const changedIssues = new Map<string, Issue[]>();
const changedPredictions = new Map<string, Prediction>();
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const error = (message: string, status = 400) => response({ error: { code: 'demo_only', message } }, status);
async function manifest() {
  loading ??= fetch(`${DEMO_BASE}demo-data/manifest.json`).then(async r => {
    if (!r.ok) throw new Error('The hosted sample bundle could not be loaded.');
    data = await r.json() as Manifest;
    return data;
  });
  return loading;
}
export function demoResource(run: string, artifact: string) {
  return data?.assets[`${run}:${artifact}`] ?? `${DEMO_BASE}demo-data/unavailable`;
}
function issues(m: Manifest, run: string) {
  if (!changedIssues.has(run)) {
    let items = structuredClone((m.routes[`/runs/${run}/issues`] as { items: Issue[] }).items);
    try {
      const saved = JSON.parse(localStorage.getItem(`epoch.demo.reviews.${run}`) ?? '{}');
      items = items.map(i => ({ ...i, review_status: ['accepted','dismissed','open'].includes(saved[i.issue_id]) ? saved[i.issue_id] : i.review_status }));
    } catch { /* browser storage is optional */ }
    changedIssues.set(run, items);
  }
  return changedIssues.get(run)!;
}
function reanchor(source: Prediction, body: Record<string, unknown>): Prediction {
  const a = Number(body.retention_at_30s), b = Number(body.retention_at_end);
  if (body.acknowledged !== true || !(a > 0 && a <= 1 && b > 0 && b < a)) throw new Error('Acknowledge assumptions and use 0 < end < 30-second retention ≤ 1.');
  const p = structuredClone(source), T = p.summary.duration_s, anchor = Math.min(30, T / 2);
  // A transparent browser-only baseline: log survival interpolates through the two anchors.
  // Preserve each snapshot bin's hazard/baseline ratio; this is not the Python predictor.
  const baseline = (t: number) => Math.exp(t <= anchor ? Math.log(a)*t/anchor : Math.log(a)+(Math.log(b)-Math.log(a))*(t-anchor)/(T-anchor));
  let survival = 1, low = 1, high = 1, watch = 0, neutralWatch = 0, lowWatch = 0, highWatch = 0;
  p.per_second = p.per_second.map((old, i) => {
    const t = old.t, end = old.end_s ?? p.per_second[i+1]?.t ?? T, dt = end-t;
    const baseStart = baseline(t), neutral = baseline(end), baseHazard = -Math.log(neutral/baseStart)/dt;
    const ratio = old.baseline_hazard_per_s && old.hazard_per_s !== undefined ? old.hazard_per_s/old.baseline_hazard_per_s : 1;
    const h = baseHazard*ratio, loss = survival*(1-Math.exp(-h*dt));
    const next = survival-loss;
    const area = h > 0 ? loss/h : survival*dt;
    watch += area; neutralWatch += baseHazard > 0 ? (baseStart-neutral)/baseHazard : baseStart*dt;
    const loH = baseHazard*Math.exp(Math.log(Math.max(ratio,1e-6))*1.5), hiH = baseHazard*Math.exp(Math.log(Math.max(ratio,1e-6))*.5);
    const lowNext = low*Math.exp(-loH*dt), highNext = high*Math.exp(-hiH*dt);
    lowWatch += loH > 0 ? (low-lowNext)/loH : low*dt;
    highWatch += hiH > 0 ? (high-highNext)/hiH : high*dt;
    low = lowNext; high = highNext;
    survival = next;
    return { ...old, retention: next, lower: Math.min(low,high), upper: Math.max(low,high), neutral, loss, excess_loss: Math.max(0,loss-(baseStart-neutral)), conditional_loss:1-Math.exp(-h*dt), hazard_per_s:h, baseline_hazard_per_s:baseHazard,cumulative_watch_s:watch,neutral_cumulative_watch_s:neutralWatch };
  });
  const range = (c:number,l:number,h:number) => ({central:c,lower:Math.min(l,h),upper:Math.max(l,h)});
  p.summary.avd_s = range(watch,lowWatch,highWatch); p.summary.apv_pct = range(watch/T*100,lowWatch/T*100,highWatch/T*100);
  p.summary.end_pct = range(survival*100,low*100,high*100);p.summary.neutral_avd_s=neutralWatch;p.summary.neutral_end_pct=b*100;
  p.summary.watch_time = {avd_s:watch,neutral_avd_s:neutralWatch,duration_s:T,apv_pct:watch/T*100,delta_vs_neutral_s:watch-neutralWatch};
  p.anchors={retention_at_30s:a,retention_at_end:b};p.recomputed=true;
  p.drop_moments=[];p.summary.excess_loss_by_feature={};
  p.label='Browser demo sensitivity — saved pressure ratios with an interpolated baseline';
  p.notes.unshift('Browser demonstration only: reanchored baseline, not a new Python analysis. Saved rule findings remain unchanged; fresh attribution/drop rankings require local reanalysis.');
  return p;
}
export async function appFetch(input: string, init?: RequestInit): Promise<Response> {
  if (!DEMO) return fetch(input, init);
  const m = await manifest(), path = input.replace(/^\/api\/v1/, ''), method = init?.method ?? 'GET';
  const match = path.match(/^\/runs\/([^/]+)(?:\/(.*))?$/), run = match?.[1], action = match?.[2] ?? '';
  if (method === 'GET') {
    if (run && action === 'issues' && m.routes[path]) return response({items:issues(m,run)});
    if (run && action === 'prediction' && changedPredictions.has(run)) return response(changedPredictions.get(run));
    if (path in m.routes) return response(m.routes[path]);
    return error('This sample or artifact is not part of the hosted demo.',404);
  }
  const body = typeof init?.body === 'string' ? JSON.parse(init.body) as Record<string,unknown> : {};
  if (!run || !m.routes[`/runs/${run}`]) return error('Fresh uploads and analysis require the local app. Open a supplied sample instead.');
  const review = action.match(/^issues\/([^/]+)\/review$/);
  if (method === 'PATCH' && review) {
    if (!['accepted','dismissed','open'].includes(String(body.status))) return error('Invalid review status.');
    const items=issues(m,run), item=items.find(i=>i.issue_id===review[1]);
    if (!item) return error('Finding not found.',404);
    item.review_status=String(body.status);item.review_reason=String(body.reason ?? '') || null;
    try {localStorage.setItem(`epoch.demo.reviews.${run}`,JSON.stringify(Object.fromEntries(items.map(i=>[i.issue_id,i.review_status]))));} catch { /* optional */ }
    return response(item);
  }
  if (action === 'prediction') {
    try {const p=reanchor(m.routes[`/runs/${run}/prediction`] as Prediction,body);changedPredictions.set(run,p);return response(p);} catch(e) {return error((e as Error).message);}
  }
  if (action === 'jev-review') {
    const d=m.routes[`/runs/${run}/deepdive`] as {jev?:{decisions?:unknown[]}};
    return response({status:'demo_snapshot',reason:'Saved second opinions only. Your question is not sent to AI.',decisions:d.jev?.decisions ?? []});
  }
  if (action === 'chat') {
    const all=(m.routes[`/runs/${run}/transcript`] as {segments:Segment[]}).segments;
    const words=String(body.message ?? '').toLowerCase().match(/[\p{L}\p{N}]{3,}/gu) ?? [];
    const selection=body.selection as {start_ms:number;end_ms:number}|null;
    const scoped=selection ? all.filter(s=>s.interval.end_ms>selection.start_ms && s.interval.start_ms<selection.end_ms) : all;
    const ranked=scoped.map(s=>({s,score:words.filter(w=>s.text.toLowerCase().includes(w)).length})).sort((a,b)=>b.score-a.score).slice(0,3);
    return response({answer:'Browser demo: matching excerpts from the saved transcript are shown below. This is local text search, not a live AI answer. Use the local app for a fresh grounded interpretation.',quotes:ranked.map(({s})=>({text:s.text,verified:true,start_ms:s.interval.start_ms})),sources:ranked.map(({s,score})=>({...s.interval,score,matched:words.filter(w=>s.text.toLowerCase().includes(w))})),citations:ranked.map(({s})=>({...s.interval,why:'Saved transcript excerpt'})),edit_warnings:['Review the original source before editing.'],dropped_citations:0,model:'Browser text search',grounding:'Precomputed sample'});
  }
  if (action === 'hypothetical') return error('Fresh cut comparison needs the local predictor. You can accept findings and export the edit plan here.');
  if (action === 'scenarios') return error('Recomputing the older scenario requires the local app. Its saved view remains available.');

  return error('This operation requires local processing. The hosted demo leaves your source unchanged.');
}
