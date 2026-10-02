"""Human-readable outputs in a visible folder: <repo>/outputs/<video-slug>/.

The content-addressed work dirs stay the source of truth; this folder is a
plain copy for people (CSV/TXT/JSON + the Colab job zip). Safe to delete.
"""

from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path

from pipeline.orchestration.io import read_json, write_json, write_text
from pipeline.orchestration.settings import REPO_ROOT

OUTPUTS_ROOT = REPO_ROOT / "outputs"


def ts(ms: int | None) -> str:
    if ms is None:
        return ""
    s = ms / 1000.0
    return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"


def slug(source: dict) -> str:
    t = re.sub(r"[^a-z0-9]+", "-", source["project"]["title"].lower()).strip("-")[:60] or "video"
    return f"{t}_{source['sha256'][:8]}"


def _csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:  # BOM: opens cleanly in Excel incl. Hindi
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
    except PermissionError:  # file open in Excel (Windows locks it): keep going, say so
        print(f"  ! {path.name} is open in another program; not refreshed")


def export_outputs(ws, source: dict) -> Path:
    out = OUTPUTS_ROOT / slug(source)
    out.mkdir(parents=True, exist_ok=True)
    lines = [f"Video: {source['original_name']}", f"Title: {source['project']['title']}",
             f"Category: {source['project']['category']}  Language: {source['project']['declared_language']}",
             f"SHA-256: {source['sha256']}", f"Workspace: {ws.root}", "", "Stage status:"]
    stages = ["probe", "proxy", "audio", "video_scan", "frames", "asr", "align", "ocr", "visual_job", "visual",
              "embed", "narrative", "score", "export"]
    recs = {n: ws.current(n) for n in stages}
    for n in stages:
        r = recs[n]
        lines.append(f"  {n:<12} {r.status if r else 'not run'}"
                     + (f"  ({r.data.get('elapsed_s')} s)" if r and r.data.get("elapsed_s") is not None else ""))

    if recs["probe"]:
        p = read_json(recs["probe"].path("probe.json"))
        write_json(out / "01_media_probe.json", p)
        lines += ["", f"Duration: {ts(p['duration_ms'])}  ({p['metadata']['width']}x{p['metadata']['height']}, "
                      f"{p['metadata']['fps_num']}/{p['metadata']['fps_den']} fps, VFR={p['metadata']['vfr']})"]
    if recs["proxy"]:
        if not (out / "proxy_720p.mp4").exists():
            shutil.copyfile(recs["proxy"].path("proxy.mp4"), out / "proxy_720p.mp4")
    if recs["video_scan"]:
        vs = recs["video_scan"]
        cuts = read_json(vs.path("scan.json"))["cuts"]
        _csv(out / "02_cuts.csv", ["n", "time", "ms", "detector_score"],
             [[i + 1, ts(c["at_ms"]), c["at_ms"], c.get("score")] for i, c in enumerate(cuts)])
        shots = read_json(vs.path("shots.json"))
        _csv(out / "03_shots.csv", ["n", "start", "end", "duration_s", "motion_mean", "luma_mean", "saturation_mean",
                                     "blur_lapvar_mean", "start_boundary", "end_boundary"],
             [[i + 1, ts(s["start_ms"]), ts(s["end_ms"]), round((s["end_ms"] - s["start_ms"]) / 1000, 2),
               s["metrics"].get("motion_mean"), s["metrics"].get("luma_mean"), s["metrics"].get("sat_mean"),
               s["metrics"].get("blur_lapvar_mean"), s["start_boundary_source"], s["end_boundary_source"]]
              for i, s in enumerate(shots)])
        f = read_json(vs.path("filters.json"))
        _csv(out / "04_black_and_freeze.csv", ["kind", "start", "end", "duration_s"],
             [[k, ts(x["start_ms"]), ts(x["end_ms"]), round((x["end_ms"] - x["start_ms"]) / 1000, 2)]
              for k in ("black", "freeze") for x in f[k]])
        durs = [(s["end_ms"] - s["start_ms"]) / 1000 for s in shots]
        lines += [f"Cuts: {len(cuts)}   Shots: {len(shots)}   mean shot {sum(durs) / len(durs):.2f} s   "
                  f"longest {max(durs):.1f} s", f"Black intervals: {len(f['black'])}   Still/freeze intervals: {len(f['freeze'])}"]
    if recs["audio"]:
        a = read_json(recs["audio"].path("audio.json"))
        summary = {k: a.get(k) for k in ("status", "sample_peak", "silence", "clipping_windows")}
        summary["loudness"] = {k: v for k, v in (a.get("loudness") or {}).items() if not k.startswith("short_term")}
        write_json(out / "05_audio_summary.json", summary)
        lud = summary["loudness"]
        lines.append(f"Audio: {a.get('status')}  integrated {lud.get('integrated_lufs')} LUFS  true peak "
                     f"{lud.get('true_peak_dbfs')} dBFS  silences {len(a.get('silence', []))}  "
                     f"clipped windows {len(a.get('clipping_windows', []))}")
    if recs["asr"]:
        vad = read_json(recs["asr"].path("vad.json"))
        _csv(out / "06_speech_regions.csv", ["start", "end", "duration_s"],
             [[ts(v["start_ms"]), ts(v["end_ms"]), round((v["end_ms"] - v["start_ms"]) / 1000, 2)] for v in vad["speech"]])
        lines.append(f"Speech present: {100 * vad['speech_fraction']:.1f}% of audio")
    if recs["align"]:
        t = read_json(recs["align"].path("transcript.json"))
        write_text(out / "07_transcript.txt", "\n".join(
            f"[{ts(s['interval']['start_ms'])} - {ts(s['interval']['end_ms'])}] ({s['language']}, {s['precision']}) {s['text']}"
            for s in t["segments"]) + "\n")
        write_json(out / "07_transcript_words.json", {"segments": t["segments"], "words": t["words"], "stats": t["stats"]})
        st = t["stats"]
        lines.append(f"Transcript: {len(t['segments'])} segments, words aligned {st['aligned_words']}/"
                     f"{st['aligned_words'] + st['unaligned_words']}")
    if recs["visual_job"]:
        vj = recs["visual_job"]
        s = read_json(vj.path("job_summary.json"))
        (out / "colab").mkdir(exist_ok=True)
        dst = out / "colab" / s["zip"]
        if not dst.exists():
            shutil.copyfile(vj.path(s["zip"]), dst)
        lines += ["", f"COLAB JOB: colab/{s['zip']}  ({s['bytes'] / 1e6:.1f} MB, {s['clips']} clips)",
                  "  -> upload to Google Drive: MyDrive/epoch/jobs/ and follow COLAB_RUN.md"]
    write_text(out / "README.txt", "\n".join(lines) + "\n")
    return out
