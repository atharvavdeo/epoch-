import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";

export function Outputs({ runId }: { runId: string }) {
  const q = useQuery({ queryKey: ["outputs", runId], queryFn: () => api.outputs(runId) });
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const files = q.data?.items ?? [];
  const file = files.find(f => f.artifact_id === selected);
  const textPreview = !!file && /\.(json|jsonl|txt|csv|srt|vtt)$/.test(file.name);
  const preview = useQuery({ queryKey: ["output-preview", runId, selected], enabled: textPreview,
    queryFn: async () => {
      const r = await fetch(api.outputUrl(runId, selected!));
      if (!r.ok) throw new Error("Could not load output");
      const text = await r.text();
      try { return JSON.stringify(JSON.parse(text), null, 2); } catch { return text; }
    } });
  return <div>
    <h3>Every output from this run</h3>
    <p className="muted">Measurements, transcript, reasoning, estimates, sampled frames and provenance are preserved with this run. Missing stages remain listed in Method and data.</p>
    <div className="actions">
      <a href={api.outputsZipUrl(runId)}><button className="hero">Download all outputs</button></a>
      <input aria-label="Filter outputs" placeholder="Find a file or stage…" value={filter} onChange={e => setFilter(e.target.value)} />
    </div>
    {q.isLoading && <p>Loading outputs…</p>}
    {q.error && <p className="err">{(q.error as Error).message}</p>}
    <p className="faint">{files.length} files · {(files.reduce((n, f) => n + f.bytes, 0) / 1048576).toFixed(1)} MB</p>
    <div style={{ maxHeight: 500, overflow: "auto" }}>
      <table style={{ width: "100%" }}><thead><tr><th>Output</th><th>Size</th><th>Actions</th></tr></thead>
        <tbody>{files.filter(f => `${f.name} ${f.stage}`.toLowerCase().includes(filter.toLowerCase())).map(f => <tr key={f.artifact_id}>
          <td style={{ wordBreak: "break-word", padding: 8 }}>{f.name}<div className="faint">{f.stage}</div></td>
          <td>{f.bytes < 1048576 ? `${(f.bytes / 1024).toFixed(1)} KB` : `${(f.bytes / 1048576).toFixed(1)} MB`}</td>
          <td><a href={api.outputUrl(runId, f.artifact_id)}><button className="quiet">Download</button></a>
            {(/\.(jpg|mp4|wav)$/.test(f.name) || /\.(json|jsonl|txt|csv|srt|vtt)$/.test(f.name) && f.bytes <= 2_000_000) && <button className="quiet" onClick={() => setSelected(f.artifact_id)}>Preview</button>}</td>
        </tr>)}</tbody></table>
    </div>
    {selected && <div style={{ marginTop: 24 }}><div className="actions"><h4>{files.find(f => f.artifact_id === selected)?.name}</h4>
      <button onClick={() => setSelected(null)}>Close preview</button></div>
      {file?.name.endsWith(".jpg") && <img src={api.outputUrl(runId, selected)} alt={file.name} style={{ maxWidth: "100%", maxHeight: 500 }} />}
      {file?.name.endsWith(".mp4") && <video key={selected} controls src={api.outputUrl(runId, selected)} style={{ width: "100%", maxHeight: 500 }} />}
      {file?.name.endsWith(".wav") && <audio key={selected} controls src={api.outputUrl(runId, selected)} />}
      {textPreview && (preview.error ? <p className="err">{(preview.error as Error).message}</p> : <pre style={{ maxHeight: 500, overflow: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{preview.isLoading ? "Loading…" : preview.data}</pre>)}
    </div>}
  </div>;
}
