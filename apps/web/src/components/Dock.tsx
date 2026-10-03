import { Link } from "react-router";

type Area = "projects" | "new" | "review" | "plan" | "evaluation" | "settings";

/** Floating bottom dock (UI_REFERENCE §3.8): small main navigation + one coral hero action (New analysis). */
export function Dock({ active, runId }: { active: Area; runId?: string }) {
  const last = runId ?? (() => { try { return localStorage.getItem("epoch.lastRun") ?? undefined; } catch { return undefined; } })();
  if (runId) { try { localStorage.setItem("epoch.lastRun", runId); } catch { /* storage blocked */ } }
  const item = (to: string | null, key: Area, label: string) => to
    ? <Link to={to} className={active === key ? "on" : ""} aria-current={active === key ? "page" : undefined}>{label}</Link>
    : <span className="off" title="Open a review first">{label}</span>;
  return (
    <nav className="dock" aria-label="Main">
      {item("/", "projects", "Projects")}
      {item(last ? `/runs/${last}` : null, "review", "Review")}
      {item(last ? `/runs/${last}/plan` : null, "plan", "Edit plan")}
      {item("/evaluation", "evaluation", "Evaluation")}
      {item("/settings", "settings", "Settings")}
      {/* one coral action per screen: the dock CTA is coral only where starting an analysis is the next step */}
      <Link to="/new" className={`${active === "projects" || active === "evaluation" || active === "settings" ? "hero" : "quiet-cta"} ${active === "new" ? "on" : ""}`}>+ New analysis</Link>
    </nav>
  );
}
