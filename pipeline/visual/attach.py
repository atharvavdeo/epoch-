"""visual stage: import a Colab *.visualresult.zip as evidence (local).

Defence in depth: the laptop re-checks protocol, job fingerprint, runtime
digest, asset hash and that the model is a pinned production profile (FAKE
and smoke-test models are rejected), then re-validates every clip output
with the same schema before converting it into Observation/Signal/Evidence/
Coverage records. Failed or missing clips become visual *unknown*, never clean.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from contracts.common import det_uuid, evidence_id, sha256_file
from epoch_vlm import RESULT_PROTOCOL
from epoch_vlm.schema import validate
from pipeline.model_registry import VLM_PROFILES
from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.stage import StageContext, StageError, StageResult, StageSpec

SAMPLING_PROFILE = "vlm:20s-clips,1fps+cut-boundaries,<=32 frames,448px"


def visual_spec(source: dict, result_zip: Path) -> StageSpec:
    return StageSpec(name="visual", version="1", deps=("visual_job", "probe"),
                     extra={"result_sha256": sha256_file(result_zip), "asset_sha256": source["sha256"]})


def select_job_for_result(ws, result_zip: Path) -> str:
    """Point visual_job at the job this result was produced from.

    A result stays valid for the exact job it ran on even if a newer job
    (e.g. with transcript context) was built later; the run records which.
    """
    with zipfile.ZipFile(result_zip) as z:
        fp = json.loads(z.read("result.json"))["job_fingerprint"]
    d = ws.root / "stages" / "visual_job" / fp[:16]
    if not (d / "stage.json").exists():
        raise StageError("unknown_job", f"no visual job {fp[:16]} exists in this workspace; the result is for another video "
                         "or a deleted job")
    ws._set_current("visual_job", fp[:16])
    return fp


def _obs_interval(frames: list[dict], core: dict) -> dict | None:
    core_frames = [f for f in frames if core["start_ms"] <= f["at_ms"] < core["end_ms"]]
    if not core_frames:
        return None  # rule 8: findings must rest on core frames
    a = min(f["at_ms"] for f in core_frames)
    b = min(core["end_ms"], max(f["at_ms"] for f in core_frames) + 1000)
    return {"start_ms": a, "end_ms": max(b, a + 1)}


def import_result(source: dict, job: dict, result: dict) -> dict:
    asset = source["asset_id"]
    observations, signals, evidence, coverage, dropped = [], [], {}, [], []
    clip_summaries = []
    job_clips = {c["clip_id"]: c for c in job["clips"]}
    model_rev = f"{result['model']['repo']}@{result['model']['revision']}"

    def frame_ev(f: dict, core: dict) -> str:
        eid = evidence_id("frame", f["frame_id"], asset)
        evidence.setdefault(eid, {"evidence_id": eid, "asset_id": asset, "kind": "frame", "ref_id": f["frame_id"],
                                  "interval": {"start_ms": f["at_ms"], "end_ms": f["at_ms"] + 1}, "precision": "frame",
                                  "provenance_stage_id": "frames", "quote": None})
        return eid

    def add_obs(clip_id, unit, kind, idx, statement, frames, core, modality, status, unknown_reason=None):
        iv = _obs_interval(frames, core) if frames else {"start_ms": core["start_ms"], "end_ms": core["end_ms"]}
        if iv is None:
            dropped.append({"clip": clip_id, "item": kind, "reason": "cites only context frames", "statement": statement})
            return None
        oid = det_uuid("observation", job["job_fingerprint"], unit, kind, idx)
        evs = [frame_ev(f, core) for f in frames if core["start_ms"] <= f["at_ms"] < core["end_ms"]]
        observations.append({"observation_id": oid, "clip_id": clip_id, "interval": iv, "modality": modality,
                             "statement": statement[:2000], "evidence_ids": evs if status != "unknown" else evs,
                             "status": status, "sampled_frame_ids": [f["frame_id"] for f in frames],
                             "model_revision": model_rev, "prompt_hash": result["prompt_sha256"],
                             "unknown_reason": unknown_reason, "_kind": kind})
        oe = evidence_id("observation", oid, asset)
        evidence[oe] = {"evidence_id": oe, "asset_id": asset, "kind": "observation", "ref_id": oid, "interval": iv,
                        "precision": "sampled", "provenance_stage_id": "visual", "quote": None}
        return oid

    for rec in result["clips"]:
        cid = rec["clip_id"]
        clip = job_clips.get(cid)
        if clip is None:
            raise StageError("result_mismatch", f"result has unknown clip {cid}")
        core = clip["core"]
        if rec.get("status") != "complete" or not rec.get("parsed"):
            reason = (rec.get("error") or {}).get("code", rec.get("status", "unknown"))
            coverage.append({"modality": "visual", "interval": core, "status": "unknown", "sampling_profile": SAMPLING_PROFILE,
                             "evidence_ids": [], "reason": f"VLM clip {cid} {reason}"})
            continue
        ref_map = {f["ref"]: f for f in clip["frames"]}
        used = [r for r in rec["frames_used"] if r in ref_map]
        transcript_text = "\n".join(t["text"] for t in clip["transcript"])
        m, errors, drop = validate(rec["parsed"], clip_id=cid, labels=used, transcript_text=transcript_text)
        if m is None:  # Colab said valid but local re-validation disagrees: do not trust it
            coverage.append({"modality": "visual", "interval": core, "status": "unknown", "sampling_profile": SAMPLING_PROFILE,
                             "evidence_ids": [], "reason": f"VLM clip {cid} failed local re-validation: {errors[:2]}"})
            continue
        dropped.extend({"clip": cid, **d} for d in drop)
        fr = lambda refs: [ref_map[r] for r in refs if r in ref_map]  # noqa: E731
        stat = {"clear": "supported", "likely": "provisional", "uncertain": "provisional"}
        for i, o in enumerate(m.observations):
            add_obs(cid, cid, "observation", i, o.statement, fr(o.frames), core, "visual", stat[o.certainty])
        svr = m.speech_visual_relation
        if svr.status != "cannot_judge":
            text = f"Speech-visual relation: {svr.status.replace('_', ' ')}." + (f" {svr.note}" if svr.note else "")
            add_obs(cid, cid, "speech_visual_relation", 0, text, fr(svr.evidence_frames), core, "visual", "provisional")
        sv = m.static_visual
        if sv.is_static:
            add_obs(cid, cid, "static_visual", 0, f"Picture stays essentially the same; useful to the explanation: {sv.useful}."
                    + (f" {sv.reason}" if sv.reason else ""), fr([f["ref"] for f in clip["frames"] if f["ref"] in used and f["role"] == "core"]),
                    core, "visual", "provisional")
        for i, t in enumerate(m.text_legibility):
            if t.concern != "none":
                add_obs(cid, cid, "text_legibility", i, f"On-screen text '{t.text}' may be hard to read ({t.concern.replace('_', ' ')})."
                        + (f" {t.note}" if t.note else ""), fr([t.frame]), core, "text", "provisional")
        for i, t in enumerate(m.technical_visual):
            if t.kind != "none":
                add_obs(cid, cid, "technical_visual", i, f"Visual technical issue: {t.kind}." + (f" {t.note}" if t.note else ""),
                        fr(t.frames), core, "visual", "provisional")
        for i, u in enumerate(m.unknowns):
            add_obs(cid, cid, "unknown", i, u, [], core, "visual", "unknown", unknown_reason="model could not judge from sampled stills")
        for i, s in enumerate(m.segments):
            frs = fr(s.frames)
            if not frs:
                continue
            a = max(core["start_ms"], frs[0]["at_ms"])
            b = min(core["end_ms"], max(frs[-1]["at_ms"] + 1000, a + 1))
            if b <= a:
                continue
            for feat, name, val in (("F36", "scene_role", s.scene_role), ("F13", "shot_scale", s.shot_scale)):
                signals.append({"signal_id": det_uuid("signal", job["job_fingerprint"], cid, feat, i), "feature_id": feat,
                                "interval": {"start_ms": a, "end_ms": b}, "modality": "visual", "name": name, "value": val,
                                "unit": "label", "method": "vlm_sampled_stills", "evidence_ids": [frame_ev(f, core) for f in frs
                                                                                                  if core["start_ms"] <= f["at_ms"] < core["end_ms"]],
                                "validity": "estimated", "unknown_reason": None})
        coverage.append({"modality": "visual", "interval": core, "status": "observed", "sampling_profile": SAMPLING_PROFILE,
                         "evidence_ids": [], "reason": None})
        clip_summaries.append({"clip_id": cid, "core": core, "parsed": m.model_dump(), "degraded": rec.get("degraded", []),
                               "frame_map": {r: {"frame_id": ref_map[r]["frame_id"], "at_ms": ref_map[r]["at_ms"]} for r in used}})
    return {"observations": observations, "signals": signals, "evidence": list(evidence.values()), "coverage": coverage,
            "clip_summaries": clip_summaries, "dropped": dropped}


def visual_stage(source: dict, result_zip: Path):
    def fn(ctx: StageContext) -> StageResult:
        vj = ctx.dep("visual_job")
        job = read_json(vj.path("bundle/job.json"))
        with zipfile.ZipFile(result_zip) as z:
            names = z.namelist()
            if "result.json" not in names:
                raise StageError("bad_result", "zip has no result.json")
            result = json.loads(z.read("result.json"))
        if result.get("protocol") != RESULT_PROTOCOL:
            raise StageError("bad_result", f"unsupported protocol {result.get('protocol')}")
        if result["job_fingerprint"] != job["job_fingerprint"]:
            raise StageError("stale_result", "this result belongs to a different visual job (inputs changed since); rerun Colab "
                             "with the current job zip", recommended_action="upload outputs/<video>/colab/<current>.visualjob.zip")
        if result["runtime_digest"] != job["runtime_digest"] or result["asset_sha256"] != source["sha256"]:
            raise StageError("result_mismatch", "runtime digest or asset hash differs from the job")
        prof = VLM_PROFILES.get(result["profile"])
        model = result["model"]
        if prof is None or model.get("repo") != prof["repo"] or model.get("revision") != prof["revision"]:
            raise StageError("unqualified_model", f"result model {model.get('repo')}@{model.get('revision')} is not the pinned "
                             f"{result['profile']} profile; fake/smoke-test results are never imported")
        out = import_result(source, job, result)
        out["profile"], out["model"], out["qualification"] = result["profile"], model, result["qualification"]
        out["counts"], out["stopped_reason"] = result["counts"], result["stopped_reason"]
        write_json(ctx.out / "visual.json", out)
        n_ok = sum(c["status"] == "observed" for c in out["coverage"])
        ctx.log(f"imported {len(out['observations'])} observations, {len(out['signals'])} label signals; "
                f"{n_ok}/{len(out['coverage'])} clips observed ({result['profile']})")
        status = "complete" if n_ok == len(out["coverage"]) else "partial"
        return StageResult(status, {"observed_clips": n_ok, "clips": len(out["coverage"]), "profile": result["profile"]})

    return fn
