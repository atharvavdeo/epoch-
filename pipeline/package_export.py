"""export stage: assemble the immutable analysis package (Schema §3).

<asset8>_<run_id>.retention.zip with manifest.json, data/*.json(l), media/proxy.mp4,
frames/<frame_id>.jpg (only frames that evidence or observations cite),
provenance/*. run_id is derived from the export fingerprint, so the same
inputs re-export to the same bytes (idempotent import) and any change gives
a new run (lineage via parent_run_id). The ZIP is validated with the same
validator the website importer uses before the stage succeeds.
"""

from __future__ import annotations

import bisect
import json
import platform
import shutil
import subprocess
import zipfile
from pathlib import Path

from contracts.common import PRODUCER_VERSION, SCHEMA_VERSION, artifact_id, det_uuid, fingerprint, sha256_file, utc_now
from contracts.package import PackageError, validate_package
from pipeline.model_registry import MODELS
from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.settings import REPO_ROOT, lock_path
from pipeline.orchestration.stage import StageContext, StageError, StageResult, StageSpec
from pipeline.outputs import OUTPUTS_ROOT, slug

REQUIRED_VIDEO_STAGES = ["probe", "proxy", "audio", "video_scan", "frames", "asr", "align", "visual", "embed", "narrative",
                         "predict", "score"]
SIGNAL_KEY_FEATURE = {"pause": ("F39", "audio", "pause", "ms"), "clip": ("F46", "audio", "clipping_fraction", "ratio"),
                      "black": ("F06", "visual", "black_interval", "ms"), "shot": ("F04", "visual", "long_shot", "ms"),
                      "wpm": ("F40", "speech", "speech_rate", "words/min")}


def code_revision() -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "contracts", "pipeline", "epoch_vlm", "prompts"],
                               cwd=REPO_ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        rev, dirty = "", "x"
    if rev and not dirty:
        return rev
    tree = fingerprint([[str(p.relative_to(REPO_ROOT).as_posix()), sha256_file(p)] for d in ("contracts", "pipeline", "epoch_vlm", "prompts")
                        for p in sorted((REPO_ROOT / d).rglob("*")) if p.is_file() and "__pycache__" not in p.parts])
    return f"uncommitted:{tree}"


def export_spec(source: dict) -> StageSpec:
    return StageSpec(name="export", version="4", deps=("probe", "proxy", "score"),
                     optional_deps=("audio", "video_scan", "frames", "asr", "align", "ocr", "visual_job", "visual", "embed",
                                    "narrative", "predict"),
                     config={"schema": SCHEMA_VERSION, "producer": PRODUCER_VERSION},
                     extra={"project": {k: source["project"][k] for k in ("project_id", "title", "category", "declared_language")},
                            "asset_id": source["asset_id"]})


def _ms(iv: dict) -> dict:
    return {"start_ms": int(iv["start_ms"]), "end_ms": int(iv["end_ms"])}


def export_stage(source: dict, ws):
    def fn(ctx: StageContext) -> StageResult:
        d = ctx.deps
        run_id = det_uuid("run", ctx.fingerprint)
        probe = read_json(d["probe"].path("probe.json"))
        T = probe["duration_ms"]
        now = utc_now()
        pkg = ctx.out / "pkg"
        if pkg.exists():
            shutil.rmtree(pkg)
        (pkg / "data").mkdir(parents=True)
        files: list[dict] = []

        def put(rel: str, src: Path | None = None, *, obj=None, rows=None, kind: str, stage: str):
            dst = pkg / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src is not None:
                shutil.copyfile(src, dst)
            elif rows is not None:
                dst.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
                                       for r in rows), encoding="utf-8")
            else:
                dst.write_text(json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
            sha = sha256_file(dst)
            rec = d.get(stage)
            files.append({"artifact_id": artifact_id(rel, sha), "kind": kind, "relative_path": rel, "sha256": sha,
                          "bytes": dst.stat().st_size, "producer_stage_id": f"{stage}:{rec.fp16}" if rec else stage,
                          "input_fingerprint": rec.fingerprint if rec else ctx.fingerprint, "created_at": now})
            return files[-1]

        def R(rows):  # stamp run_id on stage records, drop private keys
            return [{"run_id": run_id, **{k: v for k, v in r.items() if not k.startswith("_")}} for r in rows]

        missing: dict[str, str] = {}
        for s in REQUIRED_VIDEO_STAGES:
            rec = ws.current(s)
            if rec is None or rec.status not in ("complete", "partial"):
                missing[s] = ("awaiting Colab visual result (attach-visual)" if s == "visual"
                              else f"stage {s} {'not run' if rec is None else rec.status}")
        # ---------------------------------------------------------- media + records
        prox = put("media/proxy.mp4", d["proxy"].path("proxy.mp4"), kind="proxy", stage="proxy")
        tr = read_json(d["align"].path("transcript.json")) if "align" in d else None
        evidence: dict[str, dict] = {}
        signals: list[dict] = []
        observations, frames_needed, frame_meta = [], {}, {}
        if "visual" in d:
            vis = read_json(d["visual"].path("visual.json"))
            observations = vis["observations"]
            signals += vis["signals"]
            for e in vis["evidence"]:
                evidence[e["evidence_id"]] = e
            job = read_json(d["visual_job"].path("bundle/job.json"))
            for c in job["clips"]:
                for f in c["frames"]:
                    frame_meta[f["frame_id"]] = c["clip_id"]
            for o in observations:
                for fid in o["sampled_frame_ids"]:
                    frames_needed[fid] = True
            for e in vis["evidence"]:
                if e["kind"] == "frame":
                    frames_needed[e["ref_id"]] = True
        nar = read_json(d["narrative"].path("narrative.json")) if "narrative" in d else None
        if nar:
            for e in nar["evidence"]:
                evidence.setdefault(e["evidence_id"], e)
            signals += nar["signals"]
        # measurement evidence keys -> registered Signal records
        for e in list(evidence.values()):
            if e["kind"] == "signal" and not _is_uuid(e["ref_id"]):
                key = e["ref_id"].split(":")[0]
                feat, modality, name, unit = SIGNAL_KEY_FEATURE[key]
                sid = det_uuid("signal", source["sha256"], e["ref_id"])
                iv = e["interval"]
                value = iv["end_ms"] - iv["start_ms"] if unit == "ms" else None
                text = e.get("_text", "")
                if key == "wpm":
                    value = int("".join(ch for ch in text.split()[0] if ch.isdigit()) or 0)
                if key == "clip":
                    value = round(float(text.split()[-1].rstrip("%")) / 100, 6) if text.endswith("%") else None
                signals.append({"signal_id": sid, "feature_id": feat, "interval": iv, "modality": modality, "name": name,
                                "value": value, "unit": unit, "method": "deterministic measurement", "evidence_ids": [],
                                "validity": "measured" if value is not None else "unknown",
                                "unknown_reason": None if value is not None else "value not parsed"})
                e["ref_id"] = sid
        signals += measurement_signals(source, d, T)

        # Shot thumbnails + stills inside black/freeze intervals: the review UI's shot strip and visual-fault
        # evidence need pictures even when no VLM result is attached. Nearest 1 fps grid frame, no new decoding.
        if "frames" in d and "video_scan" in d and "visual_job" in d:
            grid_ms = sorted((g["at_ms"], g["frame_id"]) for g in read_json(d["frames"].path("grid.json")))
            times = [t for t, _ in grid_ms]

            def nearest(ms: int) -> str:
                i = bisect.bisect_left(times, ms)
                cands = [grid_ms[j] for j in (i - 1, i) if 0 <= j < len(grid_ms)]
                return min(cands, key=lambda tf: abs(tf[0] - ms))[1]

            for s in read_json(d["video_scan"].path("shots.json")):
                frames_needed[nearest((s["start_ms"] + s["end_ms"]) // 2)] = True
            filt = read_json(d["video_scan"].path("filters.json"))
            for iv in (filt.get("black", []) + filt.get("freeze", []))[:60]:
                frames_needed[nearest((iv["start_ms"] + iv["end_ms"]) // 2)] = True

        frames_rows = []
        if frames_needed and "frames" in d:
            grid = {g["frame_id"]: g for g in read_json(d["frames"].path("grid.json"))}
            bundle_frames = d["visual_job"].path("bundle/frames") if "visual_job" in d else None
            for fid in sorted(frames_needed):
                g = grid.get(fid)
                src_img = (bundle_frames / f"{fid}.jpg") if bundle_frames else None
                if g is None or src_img is None or not src_img.exists():
                    continue
                art = put(f"frames/{fid}.jpg", src_img, kind="frame_image", stage="frames")
                frames_rows.append({**{k: g[k] for k in ("frame_id", "at_ms", "source_pts", "time_base_num", "time_base_den",
                                                         "width", "height", "source_width", "source_height", "sampling_reason",
                                                         "crop_box", "transformations")},
                                    "artifact_id": art["artifact_id"], "clip_id": frame_meta.get(fid)})
            present = {f["frame_id"] for f in frames_rows}
            for e in list(evidence.values()):
                if e["kind"] == "frame" and e["ref_id"] not in present:
                    del evidence[e["evidence_id"]]
            for o in observations:
                o["evidence_ids"] = [x for x in o["evidence_ids"] if x in evidence]
        shots_rows = []
        if "video_scan" in d:
            for s in read_json(d["video_scan"].path("shots.json")):
                shots_rows.append({"shot_id": det_uuid("shot", source["sha256"], s["start_ms"]), "interval": _ms(s),
                                   "start_boundary_source": s["start_boundary_source"], "end_boundary_source": s["end_boundary_source"],
                                   "metrics": s["metrics"], "boundary_confidence": s.get("boundary_score"), "scene_id": None})
        ocr_rows = []
        if "ocr" in d:
            from pipeline.speech.common import language_hint

            for t in read_json(d["ocr"].path("ocr_tracks.json")):
                ocr_rows.append({"track_id": det_uuid("ocr", source["sha256"], t["start_ms"], t["text"]), "interval": _ms(t),
                                 "text": t["text"], "language": language_hint(t["text"], source["project"]["declared_language"]),
                                 "samples": [{k: s[k] for k in ("frame_id", "quad", "observed_text", "confidence")} for s in t["samples"]],
                                 "visibility_precision": "sampled", "detector_confidence": t["detector_confidence"]})
        score = read_json(d["score"].path("score.json"))
        coverage = coverage_records(T, score, d)

        issues = nar["issues"] if nar else []
        suggestions = nar["suggestions"] if nar else []
        promises = nar["promises"] if nar else []
        for i in issues:
            i["evidence_ids"] = [e for e in i["evidence_ids"] if e in evidence]
        issues = [i for i in issues if i["evidence_ids"]]
        keep_iss = {i["issue_id"] for i in issues}
        suggestions = [s for s in suggestions if all(x in keep_iss for x in s["issue_ids"])]
        risk_rows = [{**b, "contributing_issue_ids": [x for x in b["contributing_issue_ids"] if x in keep_iss]} for b in score["risk"]]
        ev_rows = [{k: v for k, v in e.items() if not k.startswith("_")} for e in evidence.values()]

        put("data/transcript.jsonl", rows=R(tr["segments"]) if tr else [], kind="data", stage="align")
        put("data/words.jsonl", rows=tr["words"] if tr else [], kind="data", stage="align")
        put("data/shots.jsonl", rows=R(shots_rows), kind="data", stage="video_scan")
        put("data/frames.jsonl", rows=frames_rows, kind="data", stage="frames")
        if "ocr" in d:
            put("data/ocr.jsonl", rows=R(ocr_rows), kind="data", stage="ocr")
        else:
            missing.setdefault("ocr", "OCR disabled (D18): text inspected by the VLM on sampled frames")
        put("data/signals.jsonl", rows=R(signals), kind="data", stage="score")
        put("data/observations.jsonl", rows=R(observations), kind="data", stage="visual")
        put("data/evidence.jsonl", rows=R(ev_rows), kind="data", stage="narrative")
        put("data/promises.jsonl", rows=R(promises), kind="data", stage="narrative")
        put("data/issues.jsonl", rows=R(issues), kind="data", stage="narrative")
        put("data/suggestions.jsonl", rows=R(suggestions), kind="data", stage="narrative")
        put("data/risk.jsonl", rows=R(risk_rows), kind="data", stage="score")
        # scenario ids are scoped to the run: two runs of one video can share identical scoring inputs, and the
        # website stores scenarios across runs (a shared id collided on import)
        put("data/scenarios.jsonl", rows=[{**s, "base_run_id": run_id, "scenario_id": det_uuid("scenario", run_id, s["scenario_id"])}
                                          for s in score["scenarios"]], kind="data", stage="score")
        if "predict" in d:
            pr = read_json(d["predict"].path("prediction.json"))
            put("data/predictions.jsonl", rows=[{**pr, "run_id": run_id}], kind="data", stage="predict")
        put("data/coverage.jsonl", rows=R(coverage), kind="data", stage="score")

        project = {**{k: source["project"][k] for k in ("project_id", "title", "category", "declared_language", "created_at",
                                                        "updated_at", "description")}, "active_run_id": None}
        meta = probe["metadata"]
        asset = {"asset_id": source["asset_id"], "project_id": source["project"]["project_id"], "kind": "video",
                 "sha256": source["sha256"], "original_name": source["original_name"], "bytes": source["bytes"],
                 "duration_ms": T, "time_origin": "source_pts", "metadata": meta, "parent_asset_id": None,
                 "original_media_artifact_id": None}
        put("data/project.json", obj=project, kind="data", stage="probe")
        put("data/asset.json", obj=asset, kind="data", stage="probe")

        stages, events = [], []
        for name in REQUIRED_VIDEO_STAGES + ["visual_job", "ocr"]:
            rec = ws.current(name)
            if rec is None:
                stages.append({"stage_id": f"{name}:none", "name": name, "status": "skipped" if name == "ocr" else "pending",
                               "fingerprint": None, "attempt_count": 0, "artifact_ids": [], "dependencies": [],
                               "started_at": None, "finished_at": None, "error": None, "versions": None, "config": None})
                continue
            stages.append({"stage_id": f"{name}:{rec.fp16}", "name": name, "status": rec.status, "fingerprint": rec.fingerprint,
                           "attempt_count": rec.data.get("attempt_count", 1),
                           "artifact_ids": [f["artifact_id"] for f in files if f["producer_stage_id"] == f"{name}:{rec.fp16}"],
                           "dependencies": sorted(rec.data.get("dependencies", {})), "started_at": rec.data.get("started_at"),
                           "finished_at": rec.data.get("finished_at"), "error": rec.data.get("error"),
                           "versions": {k: str(v) for k, v in (rec.data.get("versions") or {}).items()} or {"stage": rec.data.get("version", "1")},
                           "config": rec.data.get("config") or {}})
        nar_llm = (nar or {}).get("llm", {})
        vis_info = read_json(d["visual"].path("visual.json")) if "visual" in d else None
        models = [{"role": k, "model_id": m["repo"], "revision": m["revision"], "weight_digest": _manifest_digest(k),
                   "dtype": m["dtype"], "device": m["device"]} for k, m in MODELS.items()]
        if vis_info:
            vm = vis_info["model"]
            models.append({"role": "vlm", "model_id": vm["repo"], "revision": vm["revision"], "weight_digest": vm.get("manifest_digest"),
                           "dtype": vm.get("dtype", "bfloat16"), "device": "colab-gpu"})
        locks = [{"name": f"{e}.txt", "sha256": sha256_file(lock_path(e))} for e in ("media", "asr", "ocr", "api", "vlm")
                 if lock_path(e).exists()]
        prompts = [{"prompt_id": p.stem, "sha256": sha256_file(p)} for p in sorted((REPO_ROOT / "prompts").glob("*.md"))]
        provenance = {"code_revision": code_revision(), "environment_locks": locks, "models": models, "prompts": prompts,
                      "hardware": {"local": platform.processor() or platform.machine(), "os": platform.platform(),
                                   "vlm": (vis_info or {}).get("qualification", {}).get("key") and vis_info.get("profile")},
                      "precision": "local fp32 cpu; vlm bf16" if vis_info else "local fp32 cpu",
                      "sampling_profile": {"frames": "1fps+cut boundaries", "vlm": "20s clips <=32 frames 448px", "risk_bin_ms": 5000},
                      "detector_config": {"text_inspection": "ocr" if "ocr" in d else "vlm-sampled (no OCR, D18)"},
                      "scoring_version": score["scenarios"][0]["formula_version"] if score["scenarios"] else "scenario-survival-v1",
                      "source_rights_note": "Operator-supplied media analysed locally for evaluation; not redistributed.",
                      "external_service_model": nar_llm.get("model")}
        cov_summary = {m: {"observed_ms": sum(c["interval"]["end_ms"] - c["interval"]["start_ms"] for c in coverage
                                              if c["modality"] == m and c["status"] == "observed")} for m in ("speech", "visual", "audio", "text")}
        run = {"run_id": run_id, "project_id": source["project"]["project_id"], "asset_id": source["asset_id"],
               "status": "partial" if missing else "complete", "schema_version": SCHEMA_VERSION,
               "config_hash": fingerprint({s["name"]: s["config"] for s in stages}), "input_fingerprint": ctx.fingerprint,
               "model_profile": (vis_info or {}).get("profile") or "local-only (no VLM)", "created_at": now, "stages": stages,
               "coverage_summary": cov_summary, "provenance": provenance,
               "parent_run_id": _previous_run(ws, run_id), "source_edit_plan_id": None, "finished_at": now}
        put("data/run.json", obj=run, kind="data", stage="score")
        put("provenance/config.json", obj={s["name"]: s["config"] for s in stages}, kind="provenance", stage="score")
        put("provenance/models.json", obj=models, kind="provenance", stage="score")
        put("provenance/prompts.json", obj=prompts, kind="provenance", stage="score")
        put("provenance/llm_usage.json", obj=nar_llm, kind="provenance", stage="narrative")
        put("provenance/dismissed_candidates.json", obj={"dismissed": (nar or {}).get("dismissed", []),
                                                         "unadjudicated": (nar or {}).get("unadjudicated", [])},
            kind="provenance", stage="narrative")
        for e in ("media", "asr", "ocr", "api", "vlm"):
            if lock_path(e).exists():
                put(f"provenance/environment-locks/{e}.txt", lock_path(e), kind="lock", stage="score")
        events = (ws.root / "journal.jsonl").read_text(encoding="utf-8").splitlines() if (ws.root / "journal.jsonl").exists() else []
        put("provenance/stage-events.jsonl", rows=[json.loads(x) for x in events if x.strip()], kind="provenance", stage="score")
        errs = [s["error"] for s in stages if s.get("error")]
        put("provenance/errors.jsonl", rows=errs, kind="provenance", stage="score")

        manifest = {"schema_version": SCHEMA_VERSION, "package_id": det_uuid("package", run_id),
                    "project_id": source["project"]["project_id"], "asset_id": source["asset_id"], "run_id": run_id,
                    "created_at": now, "package_kind": "partial_analysis" if missing else "analysis",
                    "source_sha256": source["sha256"], "files": files,
                    "required_stage_names": REQUIRED_VIDEO_STAGES,
                    "completed_stage_names": [s for s in REQUIRED_VIDEO_STAGES if s not in missing],
                    "missing_stage_names": sorted(missing), "missing_stage_reasons": missing,
                    "exported_by_version": PRODUCER_VERSION}
        write_json(pkg / "manifest.json", manifest)
        zname = f"{source['asset_id'][:8]}_{run_id}.retention.zip"
        zpath = ctx.out / zname
        with zipfile.ZipFile(zpath, "w") as z:
            z.write(pkg / "manifest.json", "manifest.json", compress_type=zipfile.ZIP_DEFLATED)
            for f in files:
                comp = zipfile.ZIP_STORED if f["relative_path"].endswith((".jpg", ".mp4")) else zipfile.ZIP_DEFLATED
                z.write(pkg / f["relative_path"], f["relative_path"], compress_type=comp)
        shutil.rmtree(pkg)
        try:
            vp = validate_package(zpath)
        except PackageError as exc:
            raise StageError("export_invalid", f"package failed self-validation [{exc.code}]: {exc.message}") from exc
        out_dir = OUTPUTS_ROOT / slug(source) / "package"
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(zpath, out_dir / zname)
        ctx.log(f"package {zname} ({zpath.stat().st_size / 1e6:.1f} MB) kind={manifest['package_kind']} "
                f"issues={len(vp.records['issues'])} missing={sorted(missing)}")
        return StageResult("complete", {"zip": zname, "run_id": run_id, "package_kind": manifest["package_kind"],
                                        "issues": len(issues)})

    return fn


def _is_uuid(s: str) -> bool:
    import re

    return bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", s))


def _manifest_digest(name: str) -> str | None:
    try:
        from pipeline.local_models import manifest

        return manifest(name)["manifest_digest"]
    except Exception:
        return None


def _previous_run(ws, run_id: str) -> str | None:
    rows = [json.loads(x) for x in (ws.root / "journal.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()] \
        if (ws.root / "journal.jsonl").exists() else []
    prev = [r for r in rows if r.get("stage") == "export" and r.get("event") == "finish"]
    for r in reversed(prev):
        rid = det_uuid("run", r["fingerprint"])
        if rid != run_id:
            return rid
    return None


def coverage_records(T: int, score: dict, d: dict) -> list[dict]:
    """Per-modality coverage (Coverage contract) from the score stage's spans."""
    out = []
    spans = score["coverage_spans"]
    notes = score["coverage_notes"]
    mod_track = {"speech": "narrative", "visual": "visual", "audio": "pacing", "text": "text"}
    for modality, track in mod_track.items():
        obs = sorted(tuple(x) for x in spans.get(track, []))
        cur = 0
        for a, b in obs:
            if a > cur:
                out.append({"modality": modality, "interval": {"start_ms": cur, "end_ms": a}, "status": "unknown",
                            "sampling_profile": track, "evidence_ids": [], "reason": notes.get(track, "not inspected")})
            if b > max(a, cur):
                out.append({"modality": modality, "interval": {"start_ms": max(a, cur), "end_ms": b}, "status": "observed",
                            "sampling_profile": notes.get(track, track)[:200], "evidence_ids": [], "reason": None})
            cur = max(cur, b)
        if cur < T:
            out.append({"modality": modality, "interval": {"start_ms": cur, "end_ms": T}, "status": "unknown",
                        "sampling_profile": track, "evidence_ids": [], "reason": notes.get(track, "not inspected")})
    return out


def measurement_signals(source: dict, d: dict, T: int) -> list[dict]:
    sig = []

    def add(feat, name, iv, value, unit, modality, method):
        sig.append({"signal_id": det_uuid("signal", source["sha256"], feat, name, iv["start_ms"], iv["end_ms"]),
                    "feature_id": feat, "interval": _ms(iv), "modality": modality, "name": name, "value": value, "unit": unit,
                    "method": method, "evidence_ids": [], "validity": "measured", "unknown_reason": None})

    whole = {"start_ms": 0, "end_ms": T}
    if "video_scan" in d:
        scan = read_json(d["video_scan"].path("scan.json"))
        filt = read_json(d["video_scan"].path("filters.json"))
        s = scan["samples"]
        series = lambda k: {"t_ms": s["t_ms"], "v": s[k]}  # noqa: E731
        add("F11", "motion_energy", whole, series("motion"), "mean abs frame diff (0-1)", "visual", "2 fps 64x36 gray diff")
        add("F23", "luma_mean", whole, series("luma_mean"), "0-1", "visual", "2 fps luma")
        add("F24", "saturation_mean", whole, series("sat_mean"), "0-1", "visual", "2 fps HSV saturation")
        add("F26", "blur_laplacian_var", whole, series("blur_lapvar"), "variance", "visual", "2 fps central-crop Laplacian")
        for w0 in range(0, T, 10_000):
            w1 = min(T, w0 + 10_000)
            add("F01", "cuts_per_10s", {"start_ms": w0, "end_ms": w1},
                sum(1 for c in scan["cuts"] if w0 <= c["at_ms"] < w1), "count", "visual", "PySceneDetect AdaptiveDetector")
        for b in filt["black"]:
            add("F06", "black", b, b["end_ms"] - b["start_ms"], "ms", "visual", "ffmpeg blackdetect")
        for f in filt["freeze"]:
            add("F07", "freeze", f, f["end_ms"] - f["start_ms"], "ms", "visual", "ffmpeg freezedetect")
    if "audio" in d:
        a = read_json(d["audio"].path("audio.json"))
        if a.get("loudness"):
            lo = a["loudness"]
            add("F41", "loudness", whole, {k: lo.get(k) for k in ("integrated_lufs", "lra_lu", "true_peak_dbfs")}, "LUFS/dBFS",
                "audio", "ffmpeg ebur128")
            add("F41", "short_term_loudness", whole, {"t_ms": lo["short_term_t_ms"], "v": lo["short_term_lufs"]}, "LUFS",
                "audio", "ffmpeg ebur128 (3 s window, 1 Hz)")
        for s in a.get("silence", []):
            add("F39", "waveform_silence", s, s["end_ms"] - s["start_ms"], "ms", "audio", "ffmpeg silencedetect -50 dB")
    if "asr" in d:
        vad = read_json(d["asr"].path("vad.json"))
        add("F38", "speech_presence", whole, {"fraction": vad["speech_fraction"],
                                              "intervals": [[v["start_ms"], v["end_ms"]] for v in vad["speech"]]},
            "fraction", "audio", "silero VAD (faster-whisper)")
    return sig
