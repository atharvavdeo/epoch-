"""Analysis package validation (Schema §3, §8). Used by export self-check and the API importer.

Checks while streaming the ZIP: entry count, sizes, compression ratio, path
safety (absolute, traversal, symlinks, devices, duplicates after case
folding), encryption, executables; then manifest, exact file set, hashes,
content sniffing, per-record contracts and referential integrity.
Hashes protect integrity, not scientific truth.
"""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from contracts.common import SCHEMA_VERSION, check_interval_in_asset
from contracts.entities import (
    Asset, Coverage, EditSuggestion, Evidence, Frame, Issue, Manifest, Observation, OCRTrack, Project, Promise,
    RetentionPrediction, RetentionScenario, RiskBin, Run, Shot, Signal, TranscriptSegment, Word,
)

GiB, MiB = 1024 ** 3, 1024 ** 2
LIMITS = {"zip_bytes": 2 * GiB, "expanded_bytes": 5 * GiB, "entries": 20_000, "json_bytes": 100 * MiB, "image_bytes": 25 * MiB,
          "proxy_bytes": 2 * GiB, "ratio": 100, "path_len": 240}
ALLOWED_SUFFIX = {".json", ".jsonl", ".jpg", ".mp4", ".txt", ".md"}
JSONL_MODELS = {"transcript": TranscriptSegment, "words": Word, "shots": Shot, "frames": Frame, "ocr": OCRTrack,
                "signals": Signal, "observations": Observation, "evidence": Evidence, "promises": Promise, "issues": Issue,
                "suggestions": EditSuggestion, "risk": RiskBin, "scenarios": RetentionScenario, "coverage": Coverage,
                "predictions": RetentionPrediction}
OPTIONAL_JSONL = {"predictions"}  # added after the first packages shipped; older packages stay importable
STAGE_OF_FILE = {"transcript": "align", "words": "align", "shots": "video_scan", "frames": "frames", "ocr": "ocr",
                 "signals": "score", "observations": "visual", "evidence": "narrative", "promises": "narrative",
                 "issues": "narrative", "suggestions": "narrative", "risk": "score", "scenarios": "score",
                 "predictions": "predict"}


class PackageError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}


@dataclass
class ValidatedPackage:
    manifest: Manifest
    project: Project
    asset: Asset
    run: Run
    records: dict[str, list] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _check_entries(z: zipfile.ZipFile) -> None:
    infos = z.infolist()
    if len(infos) > LIMITS["entries"]:
        raise PackageError("too_many_entries", f"{len(infos)} entries > {LIMITS['entries']}")
    seen, total = set(), 0
    for i in infos:
        n = i.filename
        if i.flag_bits & 0x1:
            raise PackageError("encrypted_entry", f"encrypted entry {n}")
        mode = (i.external_attr >> 16) & 0xFFFF
        if mode and (stat.S_ISLNK(mode) or stat.S_ISCHR(mode) or stat.S_ISBLK(mode) or stat.S_ISFIFO(mode)):
            raise PackageError("unsafe_entry", f"symlink/device entry {n}")
        if n.endswith("/"):
            continue
        if n.startswith(("/", "\\")) or "\\" in n or ":" in n.split("/")[0] or any(p in ("", ".", "..") for p in n.split("/")):
            raise PackageError("unsafe_path", f"unsafe path {n!r}")
        if len(n) > LIMITS["path_len"]:
            raise PackageError("path_too_long", n[:80])
        key = n.casefold()
        if key in seen:
            raise PackageError("duplicate_path", f"duplicate normalised path {n}")
        seen.add(key)
        suffix = Path(n).suffix.lower()
        if suffix not in ALLOWED_SUFFIX:
            raise PackageError("disallowed_file_type", f"{n}: only {sorted(ALLOWED_SUFFIX)} are accepted")
        limit = LIMITS["json_bytes"] if suffix in (".json", ".jsonl", ".txt", ".md") else (
            LIMITS["image_bytes"] if suffix == ".jpg" else LIMITS["proxy_bytes"])
        if i.file_size > limit:
            raise PackageError("entry_too_large", f"{n} is {i.file_size} bytes (limit {limit})")
        if i.compress_size and i.file_size / max(1, i.compress_size) > LIMITS["ratio"] and i.file_size > MiB:
            raise PackageError("compression_ratio", f"{n} expands {i.file_size / i.compress_size:.0f}:1")
        total += i.file_size
        if total > LIMITS["expanded_bytes"]:
            raise PackageError("expanded_too_large", "expanded size exceeds 5 GiB")


def _hash_member(z: zipfile.ZipFile, name: str, limit: int) -> tuple[str, int, bytes]:
    h, n, head = hashlib.sha256(), 0, b""
    with z.open(name) as fh:
        while True:
            b = fh.read(1024 * 1024)
            if not b:
                break
            if not head:
                head = b[:16]
            n += len(b)
            if n > limit:  # enforce while streaming, not after extraction
                raise PackageError("entry_too_large", f"{name} exceeds its limit while reading")
            h.update(b)
    return h.hexdigest(), n, head


def _jsonl(z: zipfile.ZipFile, name: str) -> list[dict]:
    rows = []
    for ln, line in enumerate(z.read(name).decode("utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(f"{c} not allowed"))))
            except ValueError as exc:
                raise PackageError("invalid_json", f"{name}:{ln}: {exc}") from exc
    return rows


def validate_package(path: Path) -> ValidatedPackage:
    path = Path(path)
    if path.stat().st_size > LIMITS["zip_bytes"]:
        raise PackageError("zip_too_large", "package exceeds 2 GiB")
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise PackageError("not_a_zip", f"not a valid ZIP: {exc}") from exc
    with z:
        _check_entries(z)
        names = {i.filename for i in z.infolist() if not i.filename.endswith("/")}
        if "manifest.json" not in names:
            raise PackageError("missing_manifest", "manifest.json missing at package root")
        try:
            manifest = Manifest.model_validate_json(z.read("manifest.json"))
        except ValidationError as exc:
            raise PackageError("invalid_manifest", str(exc)[:800]) from exc
        major = manifest.schema_version.split(".")[0]
        if major != SCHEMA_VERSION.split(".")[0]:
            raise PackageError("unsupported_schema", f"schema {manifest.schema_version}; supported {SCHEMA_VERSION}")
        listed = {f.relative_path: f for f in manifest.files}
        extra = names - set(listed) - {"manifest.json"}
        missing = set(listed) - names
        if extra:
            raise PackageError("unlisted_files", f"files not in manifest: {sorted(extra)[:5]}")
        if missing:
            raise PackageError("missing_files", f"listed files missing: {sorted(missing)[:5]}")
        for rel, a in listed.items():
            suffix = Path(rel).suffix.lower()
            limit = LIMITS["json_bytes"] if suffix in (".json", ".jsonl", ".txt", ".md") else (
                LIMITS["image_bytes"] if suffix == ".jpg" else LIMITS["proxy_bytes"])
            sha, n, head = _hash_member(z, rel, limit)
            if sha != a.sha256 or n != a.bytes:
                raise PackageError("hash_mismatch", f"{rel} does not match its manifest hash/size")
            if suffix == ".jpg" and not head.startswith(b"\xff\xd8\xff"):
                raise PackageError("bad_image", f"{rel} is not a JPEG")
            if suffix == ".mp4" and head[4:8] != b"ftyp":
                raise PackageError("bad_video", f"{rel} is not an MP4")

        def model(name, cls):
            try:
                return cls.model_validate_json(z.read(name))
            except KeyError as exc:
                raise PackageError("missing_file", f"{name} is required") from exc
            except ValidationError as exc:
                raise PackageError("invalid_record", f"{name}: {str(exc)[:600]}") from exc

        project = model("data/project.json", Project)
        asset = model("data/asset.json", Asset)
        run = model("data/run.json", Run)
        if (project.project_id, asset.asset_id, run.run_id) != (manifest.project_id, manifest.asset_id, manifest.run_id):
            raise PackageError("identity_mismatch", "project/asset/run ids differ from the manifest")
        if asset.sha256 != manifest.source_sha256 or run.asset_id != asset.asset_id or asset.project_id != project.project_id:
            raise PackageError("identity_mismatch", "asset hash or ownership differs from the manifest")
        records: dict[str, list] = {}
        for key, cls in JSONL_MODELS.items():
            name = f"data/{key}.jsonl"
            if name not in names:
                stage = STAGE_OF_FILE.get(key)
                if key == "coverage":
                    raise PackageError("missing_file", "data/coverage.jsonl is always required")
                if key in OPTIONAL_JSONL:
                    records[key] = []
                    continue
                if stage not in manifest.missing_stage_names:
                    raise PackageError("missing_file", f"{name} absent but stage '{stage}' is not declared missing")
                records[key] = []
                continue
            rows = []
            for i, r in enumerate(_jsonl(z, name)):
                try:
                    rows.append(cls.model_validate(r))
                except ValidationError as exc:
                    raise PackageError("invalid_record", f"{name} row {i + 1}: {str(exc)[:500]}") from exc
            records[key] = rows
    _referential(manifest, asset, run, records)
    return ValidatedPackage(manifest, project, asset, run, records)


def _referential(manifest, asset, run, r) -> None:
    T = asset.duration_ms

    def uniq(key, attr):
        ids = [getattr(x, attr) for x in r[key]]
        if len(ids) != len(set(ids)):
            raise PackageError("duplicate_id", f"duplicate {attr} in {key}")
        return set(ids)

    def same_run(key):
        for x in r[key]:
            if getattr(x, "run_id", run.run_id) != run.run_id:
                raise PackageError("cross_run_reference", f"{key} row belongs to another run")

    seg = uniq("transcript", "segment_id")
    frames = uniq("frames", "frame_id")
    obs = uniq("observations", "observation_id")
    sig = uniq("signals", "signal_id")
    ocr = uniq("ocr", "track_id")
    ev = uniq("evidence", "evidence_id")
    iss = uniq("issues", "issue_id")
    sug = uniq("suggestions", "suggestion_id")
    for k in ("transcript", "shots", "ocr", "signals", "observations", "evidence", "promises", "issues", "suggestions",
              "risk", "coverage"):
        same_run(k)
    artifact_ids = {f.artifact_id for f in manifest.files}
    targets = {"transcript": seg, "frame": frames, "observation": obs, "signal": sig, "ocr": ocr}
    try:
        for e in r["evidence"]:
            check_interval_in_asset(e.interval, T, f"evidence {e.evidence_id}")
            if e.ref_id not in targets[e.kind]:
                raise PackageError("dangling_reference", f"evidence {e.evidence_id} -> missing {e.kind} {e.ref_id}")
            if e.asset_id != asset.asset_id:
                raise PackageError("cross_run_reference", f"evidence {e.evidence_id} cites another asset")
        for f in r["frames"]:
            if f.artifact_id not in artifact_ids:
                raise PackageError("dangling_reference", f"frame {f.frame_id} image not in package")
        for s in r["transcript"]:
            check_interval_in_asset(s.interval, T, "segment")
        for i in r["issues"]:
            check_interval_in_asset(i.affected_interval, T, f"issue {i.issue_id}")
            for e in i.evidence_ids:
                if e not in ev:
                    raise PackageError("dangling_reference", f"issue {i.issue_id} cites missing evidence {e}")
            for s in i.suggested_edit_ids:
                if s not in sug:
                    raise PackageError("dangling_reference", f"issue {i.issue_id} cites missing suggestion {s}")
        for s in r["suggestions"]:
            for i in s.issue_ids:
                if i not in iss:
                    raise PackageError("dangling_reference", f"suggestion {s.suggestion_id} -> missing issue {i}")
            if s.source_interval is not None:
                check_interval_in_asset(s.source_interval, T, "suggestion")
            if s.destination_ms is not None and s.destination_ms > T:
                raise PackageError("out_of_range", f"suggestion {s.suggestion_id} destination beyond the video")
        for o in r["observations"]:
            check_interval_in_asset(o.interval, T, "observation")
            for e in o.evidence_ids:
                if e not in ev:
                    raise PackageError("dangling_reference", f"observation cites missing evidence {e}")
        for p in r["promises"]:
            for e in p.setup_evidence_ids + p.fulfilment_evidence_ids:
                if e not in ev:
                    raise PackageError("dangling_reference", f"promise cites missing evidence {e}")
        for b in r["risk"]:
            check_interval_in_asset(b.interval, T, "risk bin")
            for i in b.contributing_issue_ids:
                if i not in iss:
                    raise PackageError("dangling_reference", f"risk bin cites missing issue {i}")
    except ValueError as exc:
        raise PackageError("out_of_range", str(exc)) from exc
