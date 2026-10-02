"""Colab VLM job runner (COLAB_RUNBOOK §2 steps 5–8, §4–§6).

  python -m epoch_vlm.runner --job JOB_DIR --out OUT_DIR --profile Q35-9B-BF16 \
      --snapshot MODEL_DIR --model-json MODEL.json [--mirror DRIVE_DIR] [--no-refine]

Flow: verify job -> load model once -> qualification (worst-case token probe
+ 3x warm leak check, >=2 GiB headroom) -> base clips (checkpoint each,
mirror to Drive, verify copy) -> bounded refinement -> result.json + zip.
Budgets: 1 schema repair per call and <=8 repairs/video; 1 reduced-input
retry on activation OOM; stop early if >20% of base clips fail or OOM
persists twice. Never accepts invalid output to finish a batch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from epoch_vlm import RESULT_PROTOCOL
from epoch_vlm.backends import GpuOOM
from epoch_vlm.prompting import build_messages, load_template, repair_messages, select_frames, template_sha, transcript_blob
from epoch_vlm.schema import extract_json, validate

HEADROOM_GIB = 2.0
LEAK_TOLERANCE_GIB = 0.25


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def fp(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def atomic_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def verify_job(job_dir: Path) -> dict:
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    bad = []
    for f in job["files"]:
        p = job_dir / f["path"]
        if not p.exists() or p.stat().st_size != f["bytes"] or sha256_file(p) != f["sha256"]:
            bad.append(f["path"])
    if bad:
        raise RuntimeError(f"job bundle corrupt: {len(bad)} files fail hash check, e.g. {bad[:3]}. Re-upload the zip.")
    return job


class Runner:
    def __init__(self, job_dir: Path, out: Path, backend, *, profile: str, model_info: dict, env_info: dict,
                 mirror: Path | None = None, refine: bool = True, log=print):
        self.job_dir, self.out, self.backend = job_dir, out, backend
        self.profile, self.model_info, self.env_info = profile, model_info, env_info
        self.mirror, self.refine_enabled, self.log = mirror, refine, log
        self.job = verify_job(job_dir)
        if profile not in self.job["profiles_allowed"]:
            raise RuntimeError(f"profile {profile} not allowed by this job ({self.job['profiles_allowed']})")
        self.limits = self.job["limits"]
        tpl_path = job_dir / "runtime" / "prompts" / "visual_observation.v1.md"
        self.tpl = load_template(tpl_path)
        self.prompt_sha = template_sha(tpl_path)
        self.repairs_left = int(self.limits["max_repairs"])
        self.oom_failures = 0
        self.events: list[dict] = []
        (out / "clips").mkdir(parents=True, exist_ok=True)
        (out / "refinements").mkdir(parents=True, exist_ok=True)
        self._images: dict[str, object] = {}

    # ------------------------------------------------------------- helpers
    def event(self, **kw) -> None:
        row = {"at": now(), **kw}
        self.events.append(row)
        with open(self.out / "events.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def image(self, rel: str):
        from PIL import Image

        if rel not in self._images:
            with Image.open(self.job_dir / rel) as im:
                self._images[rel] = im.convert("RGB")
        return self._images[rel]

    def unit_fp(self, unit: dict) -> str:
        return fp({"input": unit["input_digest"], "prompt": self.prompt_sha, "runtime": self.job["runtime_digest"],
                   "profile": self.profile, "model": [self.model_info.get("repo"), self.model_info.get("revision")],
                   "limits": self.limits})

    def mirror_copy(self, path: Path) -> None:
        if not self.mirror:
            return
        dst = self.mirror / path.relative_to(self.out)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dst)
        if sha256_file(dst) != sha256_file(path):  # local completion != persistent completion
            raise RuntimeError(f"checkpoint copy to {dst} failed verification")

    def load_done(self, kind: str, unit_id: str, unit: dict) -> dict | None:
        p = self.out / kind / f"{unit_id}.json"
        if not p.exists() and self.mirror and (self.mirror / kind / f"{unit_id}.json").exists():
            shutil.copyfile(self.mirror / kind / f"{unit_id}.json", p)
        if not p.exists():
            return None
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return rec if rec.get("fingerprint") == self.unit_fp(unit) else None

    # --------------------------------------------------------------- core call
    def _prepare_within_cap(self, clip: dict, frames: list[dict], token_cap: int, refine: dict | None):
        degraded = []
        while True:
            msgs = build_messages(self.job, clip, frames, self.tpl, self.image, refine=refine)
            prep = self.backend.prepare(msgs)
            if prep.input_tokens <= token_cap or len(frames) <= 4:
                break
            ctx = [f for f in frames if f.get("role") == "context"]
            if ctx:
                frames = [f for f in frames if f is not ctx[0] and f is not ctx[-1]]
            else:
                frames = frames[::2] if len(frames) > 8 else frames[:-1]
            if "token_cap" not in degraded:
                degraded.append("token_cap")
        if prep.input_tokens > token_cap:
            raise RuntimeError(f"input {prep.input_tokens} tokens exceeds cap {token_cap} even at minimum frames")
        return msgs, prep, frames, degraded

    def call(self, unit_id: str, clip: dict, frames_pool: list[dict], frame_cap: int, refine: dict | None = None) -> dict:
        labels_all = {f["ref"] for f in frames_pool}
        rec = {"unit_id": unit_id, "clip_id": clip["clip_id"], "status": "failed", "attempts": 0, "degraded": [],
               "frames_used": [], "frame_ids": [], "input_tokens": None, "image_sizes": [], "output_tokens": None,
               "hit_token_limit": False, "elapsed_s": 0.0, "raw_output": None, "parsed": None,
               "validation_errors": [], "dropped_items": [], "repair_used": False, "parse_notes": {}, "error": None,
               "prompt_sha256": self.prompt_sha, "started_at": now()}
        caps = [(frame_cap, int(self.limits["max_input_tokens"]))]
        caps.append((max(4, frame_cap // 2), int(self.limits["oom_retry_token_cap"])))
        t0 = time.time()
        for attempt, (cap, token_cap) in enumerate(caps):
            rec["attempts"] = attempt + 1
            try:
                frames = select_frames({"frames": frames_pool}, cap)
                msgs, prep, frames, deg = self._prepare_within_cap(clip, frames, token_cap, refine)
                rec["degraded"] = sorted(set(rec["degraded"] + deg + (["oom_retry"] if attempt else [])))
                rec.update(frames_used=[f["ref"] for f in frames], frame_ids=[f["frame_id"] for f in frames],
                           input_tokens=prep.input_tokens, image_sizes=prep.image_sizes[:4] + (
                               [["...", len(prep.image_sizes)]] if len(prep.image_sizes) > 4 else []))
                labels = [f["ref"] for f in frames]
                assert set(labels) <= labels_all
                gen = self.backend.generate(prep, int(self.limits["max_new_tokens"]))
                rec.update(raw_output=gen.text[:8000], output_tokens=gen.output_tokens, hit_token_limit=gen.hit_token_limit)
                expected_id = refine["refine_id"] if refine else clip["clip_id"]
                parsed, errors, dropped, notes = self._parse(gen.text, expected_id, labels, clip)
                if errors and self.repairs_left > 0:
                    self.repairs_left -= 1
                    rec["repair_used"] = True
                    self.event(event="repair", unit=unit_id, errors=errors[:5])
                    rmsgs = repair_messages(msgs, gen.text, errors, expected_id, self.tpl)
                    rprep = self.backend.prepare(rmsgs)
                    if rprep.input_tokens > token_cap + int(self.limits["max_new_tokens"]) + 600:
                        errors = errors + [f"repair prompt {rprep.input_tokens} tokens exceeds budget"]
                    else:
                        gen2 = self.backend.generate(rprep, int(self.limits["max_new_tokens"]))
                        rec.update(raw_output_repair=gen2.text[:8000], output_tokens=(gen.output_tokens + gen2.output_tokens))
                        parsed, errors, dropped, notes = self._parse(gen2.text, expected_id, labels, clip)
                rec.update(validation_errors=errors, dropped_items=dropped, parse_notes=notes)
                if parsed is not None and not errors:
                    rec.update(status="complete", parsed=parsed)
                else:
                    rec["error"] = {"code": "invalid_model_output", "message": "; ".join(errors)[:600], "retryable": False}
                break
            except GpuOOM as exc:
                self.event(event="oom", unit=unit_id, attempt=attempt + 1, frame_cap=cap)
                rec["error"] = {"code": "activation_oom", "message": str(exc)[:300], "retryable": attempt == 0}
                if attempt == len(caps) - 1:
                    self.oom_failures += 1
                continue
        rec["elapsed_s"] = round(time.time() - t0, 2)
        rec["finished_at"] = now()
        rec["memory_after"] = self.backend.memory()
        return rec

    def _parse(self, text: str, expected_id: str, labels: list[str], clip: dict):
        obj, notes = extract_json(text)
        if obj is None:
            return None, [notes.get("error", "unparseable output")], [], notes
        model, errors, dropped = validate(obj, clip_id=expected_id, labels=labels, transcript_text=transcript_blob(clip))
        return (model.model_dump() if model else None), errors, dropped, notes

    # -------------------------------------------------------- qualification
    def qualify(self) -> dict:
        qpath = self.out / "qualification.json"
        gpu = self.env_info.get("gpu", {}).get("name")
        key = fp({"profile": self.profile, "gpu": gpu, "runtime": self.job["runtime_digest"]})
        if qpath.exists():
            q = json.loads(qpath.read_text(encoding="utf-8"))
            if q.get("key") == key and q.get("passed"):
                self.log("qualification: reusing passed qualification for this profile/GPU/runtime")
                return q
        clips = self.job["clips"]
        cap = int(self.limits["frame_cap"])
        worst = max(clips, key=lambda c: (len(select_frames(c, cap)), len(transcript_blob(c)) + len(c["ocr"])))
        sizes = sorted(clips, key=lambda c: len(select_frames(c, cap)))
        rep = sizes[len(sizes) // 2]
        self.log(f"qualification: worst-case {worst['clip_id']}, representative {rep['clip_id']} x3")
        self.backend.reset_peak()
        w = self.call(worst["clip_id"], worst, worst["frames"], cap)
        peaks, reps = [], []
        for i in range(3):
            self.backend.reset_peak()
            r = self.call(rep["clip_id"], rep, rep["frames"], cap)
            reps.append(r)
            peaks.append(r["memory_after"]["peak_reserved_gib"])
        mem = self.backend.memory()
        worst_peak = w["memory_after"]["peak_reserved_gib"]
        headroom = mem["total_gib"] - max([worst_peak] + peaks)
        growth = peaks[2] - peaks[1]
        reasons = []
        if w["status"] != "complete":
            reasons.append(f"worst-case clip failed: {(w['error'] or {}).get('code')}")
        if reps[0]["status"] != "complete":
            reasons.append(f"representative clip failed: {(reps[0]['error'] or {}).get('code')}")
        if headroom < HEADROOM_GIB:
            reasons.append(f"GPU headroom {headroom:.2f} GiB < {HEADROOM_GIB} GiB")
        if growth > LEAK_TOLERANCE_GIB:
            reasons.append(f"peak reserved grew {growth:.2f} GiB between equivalent warm runs")
        if reps[0]["raw_output"] and reps[2]["raw_output"] and reps[0]["raw_output"] != reps[2]["raw_output"]:
            reasons.append("greedy outputs differ between identical warm runs (nondeterminism)")
        per_clip = sum(r["elapsed_s"] for r in reps) / 3
        q = {"key": key, "passed": not reasons, "reasons": reasons, "worst_case_clip": worst["clip_id"],
             "worst_input_tokens": w["input_tokens"], "worst_peak_reserved_gib": worst_peak,
             "representative_clip": rep["clip_id"], "warm_peaks_gib": peaks, "headroom_gib": round(headroom, 2),
             "warm_seconds_per_clip": round(per_clip, 2),
             "estimated_base_minutes": round(per_clip * len(clips) / 60, 1),
             "template": getattr(self.backend, "template_info", {}), "created_at": now(),
             "reused_outputs": {worst["clip_id"]: w, rep["clip_id"]: reps[0]}}
        atomic_json(qpath, q)
        self.mirror_copy(qpath)
        self.log(f"qualification {'PASSED' if q['passed'] else 'FAILED'}: headroom {headroom:.1f} GiB, "
                 f"{per_clip:.1f}s/clip, est. {q['estimated_base_minutes']} min for {len(clips)} clips; {reasons}")
        return q

    # ------------------------------------------------------------------ run
    def run(self) -> dict:
        started = now()
        q = self.qualify()
        if not q["passed"]:
            return self.finish(started, q, stopped="qualification_failed")
        reuse = q.get("reused_outputs", {})
        clips = self.job["clips"]
        failed, stopped = 0, None
        for i, clip in enumerate(clips):
            unit = clip
            done = self.load_done("clips", clip["clip_id"], unit)
            if done:
                failed += done["status"] != "complete"
                continue
            if clip["clip_id"] in reuse and reuse[clip["clip_id"]]["status"] == "complete":
                rec = dict(reuse[clip["clip_id"]])
                rec["reused_from_qualification"] = True
            else:
                rec = self.call(clip["clip_id"], clip, clip["frames"], int(self.limits["frame_cap"]))
            rec["fingerprint"] = self.unit_fp(unit)
            path = self.out / "clips" / f"{clip['clip_id']}.json"
            atomic_json(path, rec)
            self.mirror_copy(path)
            failed += rec["status"] != "complete"
            self.event(event="clip", clip=clip["clip_id"], status=rec["status"], s=rec["elapsed_s"],
                       tokens=rec["input_tokens"], degraded=rec["degraded"])
            self.log(f"[{i + 1}/{len(clips)}] {clip['clip_id']} {rec['status']} in {rec['elapsed_s']}s "
                     f"tokens={rec['input_tokens']} frames={len(rec['frames_used'])}"
                     + (f" degraded={rec['degraded']}" if rec["degraded"] else "")
                     + (f" error={rec['error']['code']}" if rec["error"] and rec["status"] != "complete" else ""))
            if failed > float(self.limits["stop_fail_fraction"]) * len(clips):
                stopped = f"more than {int(100 * float(self.limits['stop_fail_fraction']))}% of base clips failed"
                break
            if self.oom_failures >= 2:
                stopped = "activation OOM persisted after reduced-input retry twice"
                break
        if not stopped and self.refine_enabled:
            self.refinements()
        return self.finish(started, q, stopped=stopped)

    def refinements(self) -> None:
        by_id = {c["clip_id"]: c for c in self.job["clips"]}
        budget = int(self.limits["max_refinements"])
        for r in self.job.get("refinements", []):
            if budget <= 0:
                break
            base_path = self.out / "clips" / f"{r['clip_id']}.json"
            base = json.loads(base_path.read_text(encoding="utf-8")) if base_path.exists() else None
            parsed = (base or {}).get("parsed") or {}
            asked = (parsed.get("needs_closer_look") or {}).get("needed", False)
            text_concern = any(t.get("concern") not in (None, "none") for t in parsed.get("text_legibility", []))
            trigger = asked or (r["reason"] == "small_text" and (text_concern or not parsed))
            if not trigger:
                self.event(event="refine_skipped", refine=r["refine_id"], reason="base pass did not ask for it")
                continue
            if self.load_done("refinements", r["refine_id"], r):
                budget -= 1
                continue
            budget -= 1
            clip = by_id[r["clip_id"]]
            rec = self.call(r["refine_id"], clip, r["frames"], int(self.limits["refine_frame_cap"]), refine=r)
            rec["fingerprint"] = self.unit_fp(r)
            rec["refine_id"] = r["refine_id"]
            path = self.out / "refinements" / f"{r['refine_id']}.json"
            atomic_json(path, rec)
            self.mirror_copy(path)
            self.log(f"refine {r['refine_id']} ({r['reason']}) {rec['status']} in {rec['elapsed_s']}s")

    def finish(self, started: str, q: dict, stopped: str | None) -> dict:
        clips = []
        for c in self.job["clips"]:
            p = self.out / "clips" / f"{c['clip_id']}.json"
            if p.exists():
                clips.append(json.loads(p.read_text(encoding="utf-8")))
            else:
                clips.append({"unit_id": c["clip_id"], "clip_id": c["clip_id"], "status": "not_run", "parsed": None,
                              "error": {"code": "not_run", "message": stopped or "not processed", "retryable": True}})
        refs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((self.out / "refinements").glob("*.json"))]
        q_public = {k: v for k, v in q.items() if k != "reused_outputs"}
        result = {
            "protocol": RESULT_PROTOCOL, "job_id": self.job["job_id"], "job_fingerprint": self.job["job_fingerprint"],
            "runtime_digest": self.job["runtime_digest"], "asset_sha256": self.job["asset"]["sha256"],
            "profile": self.profile, "model": self.model_info, "environment": self.env_info, "qualification": q_public,
            "prompt_sha256": self.prompt_sha, "stopped_reason": stopped, "clips": clips, "refinements": refs,
            "repairs_used": int(self.limits["max_repairs"]) - self.repairs_left,
            "counts": {"clips": len(clips), "complete": sum(c["status"] == "complete" for c in clips),
                       "failed": sum(c["status"] == "failed" for c in clips),
                       "not_run": sum(c["status"] == "not_run" for c in clips), "refinements": len(refs)},
            "started_at": started, "finished_at": now(),
        }
        atomic_json(self.out / "result.json", result)
        zpath = self.out.parent / f"{self.job['asset']['sha256'][:16]}_{self.job['job_fingerprint'][:16]}.{self.profile}.visualresult.zip"
        tmp = zpath.with_suffix(".zip.tmp")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for p in sorted(self.out.rglob("*")):
                if p.is_file() and not p.name.endswith(".tmp"):
                    z.write(p, p.relative_to(self.out).as_posix())
        os.replace(tmp, zpath)
        if self.mirror:
            shutil.copyfile(zpath, self.mirror / zpath.name)
        self.log(f"result: {result['counts']} stopped={stopped} -> {zpath}")
        return {"result": result, "zip": str(zpath)}


def env_report() -> dict:
    info = {"python": sys.version.split()[0]}
    try:
        import torch
        import transformers

        info.update(torch=torch.__version__, transformers=transformers.__version__, cuda=torch.version.cuda)
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            info["gpu"] = {"name": p.name, "total_gib": round(p.total_memory / 1024 ** 3, 2),
                           "capability": f"{p.major}.{p.minor}"}
    except Exception as exc:
        info["error"] = str(exc)[:200]
    return info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--snapshot", help="verified local model snapshot dir")
    ap.add_argument("--model-json", help="model manifest json (repo/revision/digest)")
    ap.add_argument("--mirror", help="persistent checkpoint dir (Google Drive)")
    ap.add_argument("--no-refine", action="store_true")
    ap.add_argument("--fake", action="store_true", help="test backend; result is rejected by the importer")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        if a.fake:
            from epoch_vlm.backends import FakeBackend

            backend, model_info = FakeBackend(), {"repo": "FAKE", "revision": "FAKE", "manifest_digest": None}
        else:
            from epoch_vlm.backends import QwenBackend

            man = json.loads(Path(a.model_json).read_text(encoding="utf-8"))
            backend = QwenBackend(a.snapshot)
            model_info = {"repo": man["repo"], "revision": man["revision"], "manifest_digest": man["manifest_digest"],
                          "dtype": "bfloat16", "device_map": {"": 0}, "attn_implementation": "sdpa",
                          "load_seconds": round(backend.load_s, 1), "placement": backend.placement}
        r = Runner(Path(a.job), out, backend, profile=a.profile, model_info=model_info, env_info=env_report(),
                   mirror=Path(a.mirror) if a.mirror else None, refine=not a.no_refine)
        res = r.run()
        return 0 if res["result"]["counts"]["complete"] > 0 else 3
    except Exception as exc:
        traceback.print_exc()
        atomic_json(out / "fatal_error.json", {"error": f"{type(exc).__name__}: {exc}", "at": now()})
        return 2


if __name__ == "__main__":
    sys.exit(main())
