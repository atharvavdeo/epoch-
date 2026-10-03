import type { ReactNode } from "react";
import { Link } from "react-router";
import { IconChart, IconGrid, IconList, IconPlay, IconPlus, IconSettings } from "./Icons";

type Area = "projects" | "new" | "review" | "plan" | "evaluation" | "settings";

/** Floating bottom navigation: icon + label. The page header owns the one primary action, so the dock stays quiet. */
export function Dock({ active, runId }: { active: Area; runId?: string }) {
  const last = runId ?? (() => { try { return localStorage.getItem("epoch.lastRun") ?? undefined; } catch { return undefined; } })();
  if (runId) { try { localStorage.setItem("epoch.lastRun", runId); } catch { /* storage blocked */ } }
  const item = (to: string | null, key: Area, icon: ReactNode, label: string) => to
    ? <Link to={to} className={active === key ? "on" : ""} aria-current={active === key ? "page" : undefined} title={label}>{icon}<span>{label}</span></Link>
    : <span className="off" title="Open a review first" aria-disabled="true">{icon}<span>{label}</span></span>;
  return (
    <nav className="dock" aria-label="Main">
      {item("/", "projects", <IconGrid />, "Projects")}
      {item(last ? `/runs/${last}` : null, "review", <IconPlay />, "Review")}
      {item(last ? `/runs/${last}/plan` : null, "plan", <IconList />, "Edit plan")}
      {item("/evaluation", "evaluation", <IconChart />, "Evaluation")}
      {item("/settings", "settings", <IconSettings />, "Settings")}
      <span className="dock-sep" aria-hidden />
      <Link to="/new" className={`dock-new ${active === "new" ? "on" : ""}`} title="New analysis"><IconPlus /><span>New</span></Link>
    </nav>
  );
}
