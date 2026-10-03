import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmt, type OcrTrack } from "../api";
import { usePlayhead } from "../store";

// ---- helpers ----------------------------------------------------------------

const FRAME_W = 448;
const FRAME_H = 252;

/** Colour per confidence band */
function quadColour(conf: number): string {
  if (conf >= 0.85) return "rgba(74,222,128,0.85)";  // green – high
  if (conf >= 0.65) return "rgba(250,204,21,0.85)";  // yellow – medium
  return "rgba(248,113,113,0.85)";                   // red – low
}

/** Draw quad outlines on a canvas that sits over the <img>. */
function QuadCanvas({ quads, conf, w, h }: { quads: number[][][]; conf: number; w: number; h: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = quadColour(conf);
    ctx.lineWidth = 2;
    for (const q of quads) {
      if (q.length < 3) continue;
      ctx.beginPath();
      ctx.moveTo(q[0][0] * w, q[0][1] * h);
      for (let i = 1; i < q.length; i++) ctx.lineTo(q[i][0] * w, q[i][1] * h);
      ctx.closePath();
      ctx.stroke();
    }
  }, [quads, conf, w, h]);
  return (
    <canvas
      ref={ref}
      width={w}
      height={h}
      style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}
    />
  );
}

// ---- per-frame card ---------------------------------------------------------

interface FrameGroup {
  artifact_id: string;
  at_ms: number;
  tracks: OcrTrack[];
}

function FrameCard({ runId, group }: { runId: string; group: FrameGroup }) {
  const { focus } = usePlayhead();
  const [loaded, setLoaded] = useState(false);
  const [height, setHeight] = useState(FRAME_H / 2);

  // Collect all quads that belong to this frame
  const allQuads = group.tracks.flatMap((t) => t.quads ?? []);
  // Use worst (lowest) confidence for the colour of quads on this frame
  const minConf = Math.min(...group.tracks.map((t) => t.confidence));
  const texts = [...new Set(group.tracks.map((t) => t.text))].join(" · ");

  return (
    <button
      className="ocr-card"
      title={`Jump to ${fmt(group.at_ms)}`}
      onClick={() => focus({ start_ms: group.at_ms, end_ms: group.at_ms + 1000 }, null)}
    >
      <div className="ocr-still" style={{ position: "relative", width: FRAME_W / 2, height }}>
        <img
          loading="lazy"
          src={api.artifactUrl(runId, group.artifact_id)}
          alt={`frame at ${fmt(group.at_ms)}`}
          width={FRAME_W / 2}
          height={height}
          onLoad={(e) => { setHeight(FRAME_W / 2 * e.currentTarget.naturalHeight / e.currentTarget.naturalWidth); setLoaded(true); }}
          style={{ display: "block" }}
        />
        {loaded && allQuads.length > 0 && (
          <QuadCanvas quads={allQuads} conf={minConf} w={FRAME_W / 2} h={height} />
        )}
      </div>
      <div className="ocr-meta">
        <span className="mono faint" style={{ fontSize: 12 }}>{fmt(group.at_ms)}</span>
        <span className="ocr-text" title={texts}>{texts.length > 80 ? texts.slice(0, 78) + "…" : texts}</span>
      </div>
    </button>
  );
}

// ---- main view --------------------------------------------------------------

export function OcrFramesView({ runId }: { runId: string }) {
  const q = useQuery({ queryKey: ["ocr", runId], queryFn: () => api.ocr(runId) });
  const { currentMs } = usePlayhead();
  const [search, setSearch] = useState("");

  const tracks = q.data?.items ?? [];

  // Group tracks by artifact_id (one card per unique frame still)
  const groups = useMemo<FrameGroup[]>(() => {
    const map = new Map<string, FrameGroup>();
    for (const t of tracks) {
      if (!t.artifact_id) continue;
      const existing = map.get(t.artifact_id);
      if (existing) {
        existing.tracks.push(t);
      } else {
        map.set(t.artifact_id, {
          artifact_id: t.artifact_id,
          at_ms: t.at_ms,
          tracks: [t],
        });
      }
    }
    return [...map.values()].sort((a, b) => a.at_ms - b.at_ms);
  }, [tracks]);

  // Highlight the group closest to the current playhead
  const activeIdx = useMemo(() => {
    if (!groups.length) return 0;
    let best = 0;
    let bestDist = Infinity;
    for (let i = 0; i < groups.length; i++) {
      const d = Math.abs(groups[i].at_ms - currentMs);
      if (d < bestDist) { bestDist = d; best = i; }
    }
    return best;
  }, [groups, currentMs]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return groups;
    return groups.filter((g) => g.tracks.some((t) => t.text.toLowerCase().includes(q)));
  }, [groups, search]);

  // Scroll active card into view
  const activeRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [activeIdx]);

  if (q.isLoading) return <p className="muted">Loading OCR frames…</p>;
  if (q.error) return <p className="note">OCR frame data could not be loaded. Check the backend and retry.</p>;
  if (!tracks.length) return (
    <p className="muted">
      No on-screen text was detected in this run, or OCR was not requested.{" "}
      <span className="faint">Check the "On-screen text" row in Run details.</span>
    </p>
  );

  return (
    <div className="ocr-frames-view">
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <span className="faint" style={{ fontSize: 13 }}>
          {groups.length} frames · {tracks.length} text tracks · confidence ≥ 0.5
        </span>
        <input
          className="search-input"
          type="search"
          aria-label="Filter on-screen text"
          placeholder="Filter by text…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ marginLeft: "auto", width: 200 }}
        />
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 16, fontSize: 12, marginBottom: 10 }}>
        <span style={{ color: "rgb(74,222,128)" }}>■ conf ≥ 0.85</span>
        <span style={{ color: "rgb(250,204,21)" }}>■ conf 0.65–0.85</span>
        <span style={{ color: "rgb(248,113,113)" }}>■ conf &lt; 0.65</span>
      </div>

      <div className="ocr-strip">
        {filtered.map((g) => {
          const globalIdx = groups.indexOf(g);
          return (
            <div key={g.artifact_id} ref={globalIdx === activeIdx ? activeRef : undefined}
              className={globalIdx === activeIdx ? "ocr-wrap active" : "ocr-wrap"}>
              <FrameCard runId={runId} group={g} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
