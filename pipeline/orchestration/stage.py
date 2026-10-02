"""Content-addressed stage execution with resume (Schema §5, COLAB_RUNBOOK §5).

Layout under a workspace:
  stages/<name>/<fp16>/           finished stage (stage.json + artifacts)
  stages/<name>/<fp16>.partial/   in-progress / crashed attempt (unit checkpoints)
  current.json                    stage name -> fp16 of the latest finished result
  journal.jsonl                   append-only stage events

fingerprint = sha256(canonical JSON of stage name+version, schema version,
relevant config, extra inputs (title, model revisions, prompt hashes), env
lock digest, and every upstream stage's output digest).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from contracts.common import SCHEMA_VERSION, fingerprint, sha256_file, utc_now
from pipeline.orchestration.io import append_jsonl, read_json, write_json
from pipeline.orchestration.settings import env_python, lock_path

FINISHED = ("complete", "partial", "failed", "skipped")


class StageError(Exception):
    """A stage failure with a Schema §7 shaped description."""

    def __init__(self, code: str, message: str, *, retryable: bool = False, details: dict | None = None,
                 recommended_action: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
        self.recommended_action = recommended_action

    def to_error(self, stage: str, attempt: int) -> dict:
        return {"code": self.code, "message": self.message[:2000], "stage": stage, "retryable": self.retryable,
                "attempt": attempt, "evidence_ids": [], "details": _redact(self.details),
                "recommended_action": self.recommended_action, "occurred_at": utc_now()}


def _redact(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if any(s in k.lower() for s in ("key", "token", "secret", "password", "authorization")):
            out[k] = "[redacted]"
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v if not isinstance(v, str) else v[:500]
        else:
            out[k] = str(v)[:500]
    return out


@dataclass
class StageSpec:
    name: str
    version: str
    env: str = "media"
    deps: tuple[str, ...] = ()
    optional_deps: tuple[str, ...] = ()
    config: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)
    versions: dict = field(default_factory=dict)


@dataclass
class StageResult:
    status: str  # complete | partial
    summary: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class StageRecord:
    name: str
    fingerprint: str
    status: str
    dir: Path
    data: dict

    @property
    def fp16(self) -> str:
        return self.fingerprint[:16]

    def path(self, rel: str) -> Path:
        return self.dir / rel

    @property
    def output_digest(self) -> str:
        return self.data.get("output_digest") or fingerprint([])


@dataclass
class StageContext:
    ws: "Workspace"
    spec: StageSpec
    fingerprint: str
    out: Path
    deps: dict[str, StageRecord]
    attempt: int

    def log(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] [{self.spec.name}] {msg}"
        print(line, flush=True)
        with open(self.ws.root / "pipeline.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def dep(self, name: str) -> StageRecord:
        if name not in self.deps:
            raise StageError("missing_dependency", f"{self.spec.name} needs completed stage {name}")
        return self.deps[name]

    def run_subprocess(self, module: str, args: dict, *, timeout_s: float = 6 * 3600,
                       extra_env: dict[str, str] | None = None) -> dict:
        """Run `python -m module --args <json>` inside the spec's environment."""
        args = {"out_dir": str(self.out), "stage": self.spec.name, **args}
        args_path = self.out / "_subprocess_args.json"
        write_json(args_path, args)
        py = env_python(self.spec.env)
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        env.update(extra_env or {})
        self.log(f"subprocess {module} in env '{self.spec.env}'")
        log_file = self.out / "_subprocess.log"
        with open(log_file, "a", encoding="utf-8") as lf:
            # Below-normal priority keeps the laptop responsive while a heavy stage runs.
            flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) if os.name == "nt" else 0
            proc = subprocess.Popen([str(py), "-m", module, "--args", str(args_path)], stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, env=env, cwd=str(self.ws.repo_root), creationflags=flags)
            assert proc.stdout is not None
            start = time.time()
            for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                lf.write(line + "\n")
                lf.flush()
                print(f"    {line}", flush=True)
                if time.time() - start > timeout_s:
                    proc.kill()
                    raise StageError("subprocess_timeout", f"{module} exceeded {timeout_s}s")
            rc = proc.wait()
        result_path = self.out / "_result.json"
        result = read_json(result_path) if result_path.exists() else {}
        if rc != 0 or result.get("status") == "failed":
            err = result.get("error") or {}
            raise StageError(err.get("code", "subprocess_failed"),
                             err.get("message", f"{module} exited with code {rc}; see {log_file}"),
                             retryable=bool(err.get("retryable", False)), details=err.get("details", {}),
                             recommended_action=err.get("recommended_action"))
        return result


class Workspace:
    def __init__(self, root: Path, repo_root: Path):
        self.root = Path(root)
        self.repo_root = Path(repo_root)
        (self.root / "stages").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- pointers
    def _current(self) -> dict:
        p = self.root / "current.json"
        return read_json(p) if p.exists() else {}

    def current(self, name: str) -> StageRecord | None:
        fp16 = self._current().get(name)
        if not fp16:
            return None
        d = self.root / "stages" / name / fp16
        if not (d / "stage.json").exists():
            return None
        data = read_json(d / "stage.json")
        return StageRecord(name, data["fingerprint"], data["status"], d, data)

    def _set_current(self, name: str, fp16: str) -> None:
        cur = self._current()
        cur[name] = fp16
        write_json(self.root / "current.json", cur)

    def event(self, **row: Any) -> None:
        append_jsonl(self.root / "journal.jsonl", {"at": utc_now(), **row})


def lock_digest(env: str) -> str:
    p = lock_path(env)
    return sha256_file(p) if p.exists() else fingerprint({"missing_lock": env})


def stage_fingerprint(spec: StageSpec, deps: dict[str, StageRecord]) -> str:
    return fingerprint({
        "stage": spec.name,
        "version": spec.version,
        "schema": SCHEMA_VERSION,
        "config": spec.config,
        "extra": spec.extra,
        "lock": lock_digest(spec.env),
        "deps": {k: v.output_digest for k, v in sorted(deps.items())},
    })


def _list_artifacts(d: Path) -> list[dict]:
    out = []
    for p in sorted(d.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(d).as_posix()
        if rel == "stage.json" or rel.startswith("_") or "/_" in rel or p.name.startswith("."):
            continue
        out.append({"path": rel, "sha256": sha256_file(p), "bytes": p.stat().st_size})
    return out


def _verify(rec: StageRecord) -> str | None:
    for a in rec.data.get("artifacts", []):
        p = rec.dir / a["path"]
        if not p.exists():
            return f"missing artifact {a['path']}"
        if p.stat().st_size != a["bytes"] or sha256_file(p) != a["sha256"]:
            return f"artifact hash mismatch {a['path']}"
    return None


def run_stage(ws: Workspace, spec: StageSpec, fn: Callable[[StageContext], StageResult], *,
              force: bool = False, retry_partial: bool = False) -> StageRecord:
    """Run or reuse a stage. Required deps must be complete/partial."""
    deps: dict[str, StageRecord] = {}
    for d in spec.deps:
        rec = ws.current(d)
        if rec is None or rec.status not in ("complete", "partial"):
            return _finish_skipped(ws, spec, f"required stage '{d}' is {rec.status if rec else 'missing'}")
        deps[d] = rec
    for d in spec.optional_deps:
        rec = ws.current(d)
        if rec is not None and rec.status in ("complete", "partial"):
            deps[d] = rec

    fp = stage_fingerprint(spec, deps)
    fp16 = fp[:16]
    base = ws.root / "stages" / spec.name
    final = base / fp16
    partial = base / f"{fp16}.partial"

    if final.exists() and (final / "stage.json").exists() and not force:
        data = read_json(final / "stage.json")
        rec = StageRecord(spec.name, fp, data["status"], final, data)
        reason = _verify(rec)
        redo = retry_partial and data["status"] in ("partial", "failed")
        if reason is None and data["status"] in ("complete", "partial") and not redo:
            ws._set_current(spec.name, fp16)
            ws.event(stage=spec.name, fingerprint=fp, event="cache_hit", status=data["status"])
            print(f"[cache] {spec.name} {fp16} ({data['status']})", flush=True)
            return rec
        # stale/corrupt/failed/retry: move back into a partial dir so unit checkpoints resume
        if not partial.exists():
            final.rename(partial)
        else:
            shutil.rmtree(final)
        ws.event(stage=spec.name, fingerprint=fp, event="reopen", reason=reason or f"retry {data['status']}")

    partial.mkdir(parents=True, exist_ok=True)
    prev_attempts = 0
    if (partial / "stage.json").exists():
        prev_attempts = int(read_json(partial / "stage.json").get("attempt_count", 0))
    attempt = prev_attempts + 1
    started = utc_now()
    t0 = time.time()
    ctx = StageContext(ws=ws, spec=spec, fingerprint=fp, out=partial, deps=deps, attempt=attempt)
    write_json(partial / "stage.json", {"name": spec.name, "fingerprint": fp, "status": "running",
                                        "attempt_count": attempt, "started_at": started})
    ws.event(stage=spec.name, fingerprint=fp, event="start", attempt=attempt)
    ctx.log(f"start fp={fp16} attempt={attempt}")
    error = None
    try:
        result = fn(ctx)
        status = result.status
        if status not in ("complete", "partial"):
            raise StageError("bad_stage_status", f"stage returned status {status}")
    except StageError as exc:
        status, result, error = "failed", StageResult("failed"), exc.to_error(spec.name, attempt)
    except Exception as exc:  # unexpected: record, never hide
        tb = traceback.format_exc(limit=6)
        status, result = "failed", StageResult("failed")
        error = StageError("unexpected_error", f"{type(exc).__name__}: {exc}", details={"traceback": tb}).to_error(spec.name, attempt)
        print(tb, file=sys.stderr, flush=True)

    artifacts = _list_artifacts(partial)
    data = {
        "name": spec.name,
        "fingerprint": fp,
        "status": status,
        "attempt_count": attempt,
        "started_at": started,
        "finished_at": utc_now(),
        "elapsed_s": round(time.time() - t0, 2),
        "env": spec.env,
        "version": spec.version,
        "versions": spec.versions,
        "config": spec.config,
        "extra": spec.extra,
        "dependencies": {k: {"fingerprint": v.fingerprint, "output_digest": v.output_digest} for k, v in deps.items()},
        "artifacts": artifacts,
        "output_digest": fingerprint([[a["path"], a["sha256"]] for a in artifacts]),
        "summary": result.summary,
        "warnings": result.warnings,
        "error": error,
    }
    write_json(partial / "stage.json", data)
    if status == "failed":
        # keep the partial dir (unit checkpoints) for resume; do not advance current pointer
        ws.event(stage=spec.name, fingerprint=fp, event="failed", error=error)
        ctx.log(f"FAILED {error['code']}: {error['message']}")
        return StageRecord(spec.name, fp, status, partial, data)
    if final.exists():
        shutil.rmtree(final)
    partial.rename(final)
    ws._set_current(spec.name, fp16)
    ws.event(stage=spec.name, fingerprint=fp, event="finish", status=status, elapsed_s=data["elapsed_s"])
    ctx.log(f"{status} in {data['elapsed_s']}s")
    return StageRecord(spec.name, fp, status, final, data)


def _finish_skipped(ws: Workspace, spec: StageSpec, reason: str) -> StageRecord:
    ws.event(stage=spec.name, event="skipped", reason=reason)
    print(f"[skip] {spec.name}: {reason}", flush=True)
    data = {"name": spec.name, "fingerprint": None, "status": "skipped", "summary": {}, "artifacts": [],
            "error": None, "skip_reason": reason}
    return StageRecord(spec.name, "0" * 64, "skipped", ws.root, data)


def subprocess_main(run: Callable[[dict, Path], dict]) -> None:
    """Entry helper for stage modules executed in another environment.

    `run(args, out_dir)` returns {"status": ..., "summary": {...}}; any
    exception is converted into a failed _result.json and exit code 1.
    """
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--args", required=True)
    ns = ap.parse_args()
    args = json.loads(Path(ns.args).read_text(encoding="utf-8"))
    out = Path(args["out_dir"])
    try:
        res = run(args, out)
        write_json(out / "_result.json", res)
        sys.exit(0)
    except StageError as exc:
        write_json(out / "_result.json", {"status": "failed", "error": exc.to_error(args.get("stage", "?"), 0)})
        print(f"STAGE ERROR {exc.code}: {exc.message}", flush=True)
        sys.exit(1)
    except Exception as exc:
        tb = traceback.format_exc(limit=8)
        print(tb, flush=True)
        write_json(out / "_result.json", {"status": "failed", "error": StageError(
            "unexpected_error", f"{type(exc).__name__}: {exc}", details={"traceback": tb}).to_error(args.get("stage", "?"), 0)})
        sys.exit(1)
