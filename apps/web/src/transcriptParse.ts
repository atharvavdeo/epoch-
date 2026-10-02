// Preview-only parser for transcript files (.srt/.vtt keep timestamps; .txt/.md get an estimated timeline).
// The pipeline re-parses the saved original text itself (pipeline/script/parse.py); this mirrors its rules.

export type ParsedTranscript = { source_name: string; timed: boolean; segments: { start_ms: number; end_ms: number; text: string }[];
  words: number; duration_ms: number; warnings: string[]; raw: string };

export const ESTIMATED_WPM = 150;

const ts = (s: string) => {
  const m = s.trim().match(/(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})/);
  if (!m) return null;
  return ((+(m[1] ?? 0) * 60 + +m[2]) * 60 + +m[3]) * 1000 + +m[4].padEnd(3, "0");
};

export function parseTranscriptFile(name: string, raw: string): ParsedTranscript {
  const text = raw.replace(/\r\n?/g, "\n").replace(/^﻿/, "");
  const warnings: string[] = [];
  const timedFile = /\.(srt|vtt)$/i.test(name) || /-->/.test(text);
  let segments: ParsedTranscript["segments"] = [];
  if (timedFile) {
    for (const block of text.split(/\n\s*\n/)) {
      const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
      const k = lines.findIndex((l) => l.includes("-->"));
      if (k < 0) continue;
      const [a, b] = lines[k].split("-->").map((x) => ts(x));
      const body = lines.slice(k + 1).join(" ").replace(/<[^>]+>/g, "").trim();
      if (a === null || b === null || !body) continue;
      if (b <= a) { warnings.push(`cue at ${lines[k]} has end ≤ start; skipped`); continue; }
      segments.push({ start_ms: a, end_ms: b, text: body });
    }
    segments.sort((p, q) => p.start_ms - q.start_ms);
    if (!segments.length) warnings.push("no timed cues found");
  } else {
    const paras = text.replace(/^#+\s*/gm, "").split(/\n\s*\n|(?<=[.!?])\s+(?=[A-Zऀ-ॿ])/).map((p) => p.replace(/\s+/g, " ").trim()).filter(Boolean);
    let t = 0;
    for (const p of paras) {
      const n = p.split(" ").length;
      const d = Math.max(1000, Math.round((n / ESTIMATED_WPM) * 60000));
      segments.push({ start_ms: t, end_ms: t + d, text: p });
      t += d;
    }
    if (segments.length) warnings.push(`timeline estimated at ${ESTIMATED_WPM} words per minute; every timestamp is approximate`);
  }
  const words = segments.reduce((n, s) => n + s.text.split(/\s+/).filter(Boolean).length, 0);
  return { source_name: name, timed: timedFile && segments.length > 0, segments, words,
    duration_ms: segments.length ? segments[segments.length - 1].end_ms : 0, warnings, raw: text };
}
