import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { Dock } from "../components/Dock";
import { useNavigate } from "react-router";
import { setIntroSeen } from "../components/Welcome";

const KEY = "epoch.prefs";
type Prefs = { creator: string; category: string; language: string; transcriptLayers: string };
const load = (): Prefs => {
  try { return { creator: "", category: "education", language: "en", transcriptLayers: "structure+findings", ...JSON.parse(localStorage.getItem(KEY) ?? "{}") }; }
  catch { return { creator: "", category: "education", language: "en", transcriptLayers: "structure+findings" }; }
};

/** Useful local settings, not a social profile. Secrets are configured in .env and never shown here. */
export default function Settings() {
  const q = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [p, setP] = useState<Prefs>(load);
  const [saved, setSaved] = useState(false);
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(p)); setSaved(true); } catch { setSaved(false); } };
  const s = q.data;
  const nav = useNavigate();
  return (
    <div className="shell">
      <div className="header"><span /><div className="title"><h1>Settings</h1></div><span /></div>
      <div className="home">
        <div className="card">
          <div className="section-title"><h3>Creator defaults</h3><span className="sub">pre-fill New analysis</span></div>
          <div style={{ display: "grid", gap: 10, maxWidth: 460 }}>
            <label>Creator name<br /><input value={p.creator} onChange={(e) => setP({ ...p, creator: e.target.value })} style={{ width: "100%" }} /></label>
            <label>Default category<br /><select value={p.category} onChange={(e) => setP({ ...p, category: e.target.value })}>
              <option value="education">education</option><option value="tech_review">tech review</option><option value="other">other</option></select></label>
            <label>Default language<br /><select value={p.language} onChange={(e) => setP({ ...p, language: e.target.value })}>
              <option value="en">English</option><option value="hi">Hindi</option><option value="mixed">Hinglish / mixed</option></select></label>
            <div className="actions"><button className="hero" onClick={save}>Save</button>
              <button className="quiet" onClick={() => { setIntroSeen(false); nav("/"); }}>Show intro again</button>{saved && <span className="muted">Saved in this browser.</span>}</div>
          </div>
        </div>
        <div className="card">
          <div className="section-title"><h3>Connections & storage</h3></div>
          {!s ? <div className="skel-block"><span className="skel" style={{ width: "80%", height: 14 }} /><span className="skel" style={{ width: "60%", height: 14 }} /></div> : (
            <div className="kv" style={{ gridTemplateColumns: "170px 1fr" }}>
              <span className="muted">Local data folder</span><span className="mono">{s.data_dir}</span>
              <span className="muted">Cerebras API</span>
              <span>{s.cerebras.configured ? <span className="pill supported">key configured</span> : <span className="pill high">no key</span>}
                {" "}<span className="faint">{s.cerebras.base_url} · model {s.cerebras.model ?? "auto (probe)"}</span>
                <div className="faint" style={{ fontSize: 13 }}>Set CEREBRAS_API_KEY in the git-ignored .env file. The key is never shown or stored here.</div></span>
              <span className="muted">Sent to Cerebras</span><span style={{ fontSize: 14 }}>{s.sent_to_cerebras}</span>
              <span className="muted">Jev / TypeSafe</span><span style={{ fontSize: 14 }}>Optional cloud editorial second opinion. When TYPESAFE_API_KEY is configured, the title, bounded transcript passages and your editorial question are sent to TypeSafe. Video, audio and frames are not sent. Keys stay in the git-ignored .env file.</span>
              <span className="muted">ASR CPU threads</span><span>{s.asr_threads} <span className="faint">(EPOCH_ASR_THREADS in .env)</span></span>
              <span className="muted">Local models</span>
              <span>{s.models.map((m) => <div key={m.role} style={{ fontSize: 13 }}>
                {m.present ? "Present" : "Missing"} · {m.role}: <span className="mono">{m.model_id}@{m.revision.slice(0, 8)}</span></div>)}</span>
              <span className="muted">Visual model</span><span style={{ fontSize: 14 }}>Qwen3.5-9B, runs only on Colab via the job zip. Never on this laptop.</span>
            </div>)}
        </div>
      </div>
      <Dock active="settings" />
    </div>
  );
}
