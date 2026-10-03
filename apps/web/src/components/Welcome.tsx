import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { IconArrow, IconChart, IconList, IconUpload } from "./Icons";

const KEY = "epoch.introSeen";
export const introSeen = () => { try { return localStorage.getItem(KEY) === "1"; } catch { return true; } };
export const setIntroSeen = (v: boolean) => { try { if (v) localStorage.setItem(KEY, "1"); else localStorage.removeItem(KEY); } catch { /* storage blocked */ } };

const STEPS: { icon: ReactNode; title: string; line: string }[] = [
  { icon: <IconUpload size={30} />, title: "Upload a video, voice note or script", line: "Everything runs on this computer." },
  { icon: <IconChart size={30} />, title: "We find where viewers may drop and why", line: "Each moment links to the exact words, sound or shot." },
  { icon: <IconList size={30} />, title: "Fix it with an edit plan", line: "Keep what works, change what doesn't." },
];

/** First-visit welcome: three short steps, progress dots, one primary action. */
export function Welcome({ onClose }: { onClose: () => void }) {
  const nav = useNavigate();
  const [i, setI] = useState(0);
  const done = (to?: string) => { setIntroSeen(true); onClose(); if (to) nav(to); };
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") setI((n) => Math.min(STEPS.length - 1, n + 1));
      if (e.key === "ArrowLeft") setI((n) => Math.max(0, n - 1));
      if (e.key === "Escape") done();
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  });
  const s = STEPS[i];
  const last = i === STEPS.length - 1;
  return (
    <div className="welcome" role="dialog" aria-modal="true" aria-label="Welcome to Epoch">
      <button className="quiet welcome-skip" onClick={() => done()}>Skip</button>
      <div className="welcome-body">
        <div className="welcome-brand"><span className="brand-mark" aria-hidden />Epoch</div>
        <div className="welcome-step" key={i}>
          <span className="welcome-icon">{s.icon}</span>
          <span className="welcome-n num">Step {i + 1} of {STEPS.length}</span>
          <h1>{s.title}</h1>
          <p>{s.line}</p>
        </div>
        <div className="welcome-dots" role="tablist" aria-label="Steps">
          {STEPS.map((_, k) => <button key={k} role="tab" aria-selected={k === i} aria-label={`Step ${k + 1}`} className={k === i ? "on" : ""} onClick={() => setI(k)} />)}
        </div>
        <div className="welcome-actions">
          {last ? <button className="hero" autoFocus onClick={() => done("/new")}>Start your first analysis</button>
            : <button className="hero" autoFocus onClick={() => setI(i + 1)}>Next <IconArrow size={16} /></button>}
        </div>
      </div>
    </div>
  );
}
