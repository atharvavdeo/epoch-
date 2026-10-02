import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, fmt } from "../api";
import { Dock } from "../components/Dock";
import { issueLabel } from "../components/Timeline";

const pct = (v: number | undefined) => (v === undefined ? "not inspected" : `${Math.round(v * 100)}%`);

/** What was tested, on which videos, and what remains unvalidated. Reviewer decisions are the only labels. */
export default function Evaluation() {
  const q = useQuery({ queryKey: ["evaluation"], queryFn: api.evaluation });
  const runs = q.data?.runs ?? [];
  const types: Record<string, { total: number; accepted: number; dismissed: number; open: number }> = {};
  for (const r of runs) for (const [t, v] of Object.entries(r.issues.by_type)) {
    const a = (types[t] ??= { total: 0, accepted: 0, dismissed: 0, open: 0 });
    a.total += v.total; a.accepted += v.accepted ?? 0; a.dismissed += v.dismissed ?? 0; a.open += v.open ?? 0;
  }
  return (
    <div className="shell">
      <div className="header"><span /><div className="title"><h1>Evaluation</h1>
        <div className="sub">What was tested, on which videos, and what is still unvalidated</div></div><span /></div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="section-title"><h3>Not validated yet</h3><span className="sub">read this before trusting any number</span></div>
        <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>{(q.data?.unvalidated ?? []).map((u) => <li key={u}>{u}</li>)}</ul>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="section-title"><h3>Reviewer decisions by finding type</h3>
          <span className="sub">accepted = useful, dismissed = false positive or not worth editing; open = not reviewed</span></div>
        {!Object.keys(types).length ? <p className="muted">No findings yet.</p> : (
          <table className="cmp">
            <thead><tr><th>Finding type</th><th>Total</th><th>Accepted</th><th>Dismissed</th><th>Not reviewed</th><th>Precision so far</th></tr></thead>
            <tbody>{Object.entries(types).sort((a, b) => b[1].total - a[1].total).map(([t, v]) => {
              const reviewed = v.accepted + v.dismissed;
              return <tr key={t}><td>{issueLabel(t)}</td><td>{v.total}</td><td>{v.accepted}</td><td>{v.dismissed}</td><td>{v.open}</td>
                <td>{reviewed ? `${Math.round((100 * v.accepted) / reviewed)}% of ${reviewed} reviewed` : "no reviews yet"}</td></tr>;
            })}</tbody>
          </table>)}
      </div>

      <div className="card">
        <div className="section-title"><h3>Videos analysed</h3><span className="sub">{runs.length} run(s)</span></div>
        {q.isLoading && <p className="muted">Loading…</p>}
        <table className="cmp">
          <thead><tr><th>Video</th><th>Kind</th><th>Length</th><th>Coverage (speech / visual / text)</th><th>Findings</th><th>Slowest stages</th></tr></thead>
          <tbody>{runs.map((r) => {
            const slow = Object.entries(r.stage_seconds).filter(([, s]) => s !== null).sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0)).slice(0, 3);
            return (
              <tr key={r.run_id}>
                <td><Link to={`/runs/${r.run_id}`}>{r.project_title || r.run_id.slice(0, 8)}</Link>
                  <div className="faint" style={{ fontSize: 12 }}>{r.category} · {r.language} · {r.created_at.slice(0, 16).replace("T", " ")}</div></td>
                <td>{r.package_kind === "analysis" ? "complete" : "partial"}{Object.keys(r.missing).length ?
                  <div className="faint" style={{ fontSize: 12 }}>missing: {Object.keys(r.missing).join(", ")}</div> : null}</td>
                <td className="mono">{fmt(r.duration_ms).replace(/\.\d$/, "")}</td>
                <td>{pct(r.coverage.speech)} / {pct(r.coverage.visual)} / {pct(r.coverage.text)}</td>
                <td>{r.issues.total} <span className="faint">({r.issues.supported} supported, {r.issues.accepted} accepted, {r.issues.dismissed} dismissed)</span></td>
                <td style={{ fontSize: 13 }}>{slow.map(([n, s]) => `${n} ${Math.round((s ?? 0) / 60)} min`).join(" · ") || "—"}</td>
              </tr>);
          })}</tbody>
        </table>
        <p className="faint" style={{ fontSize: 13 }}>Stage times are from each run's own records (Windows laptop CPU for local stages).
          Cached stages show the time of the run that produced them.</p>
      </div>
      <Dock active="evaluation" />
    </div>
  );
}
