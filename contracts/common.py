"""Common types, enumerations and invariants (Schema.md §1)."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"
PRODUCER_VERSION = "epoch-pipeline/0.1.0"

# Namespace for deterministic (name-based) UUIDs. Fixed forever: changing it
# would change every derived ID and silently break resume/fingerprints.
EPOCH_NAMESPACE = uuid.UUID("6f1c2a54-3b7e-5d0a-9c3e-2b8f4e7a9d10")

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EVIDENCE_ID_RE = re.compile(r"^ev_[0-9a-f]{16,64}$")
ARTIFACT_ID_RE = re.compile(r"^art_[0-9a-f]{16,64}$")


# ---------------------------------------------------------------- enumerations


class Language(str, Enum):
    en = "en"
    hi = "hi"
    mixed = "mixed"
    unknown = "unknown"


class Category(str, Enum):
    tech_review = "tech_review"
    education = "education"
    other = "other"


class Modality(str, Enum):
    speech = "speech"
    visual = "visual"
    audio = "audio"
    text = "text"


class Precision(str, Enum):
    frame = "frame"
    word = "word"
    segment = "segment"
    sampled = "sampled"
    estimated = "estimated"


class EvidenceStatus(str, Enum):
    supported = "supported"
    provisional = "provisional"
    unknown = "unknown"


class StageStatus(str, Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    partial = "partial"
    failed = "failed"
    skipped = "skipped"
    cancelled = "cancelled"
    stale = "stale"


class RunStatus(str, Enum):
    planned = "planned"
    running = "running"
    complete = "complete"
    partial = "partial"
    failed = "failed"
    cancelled = "cancelled"


class RiskTrack(str, Enum):
    narrative = "narrative"
    visual = "visual"
    pacing = "pacing"
    text = "text"
    technical = "technical"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


# ------------------------------------------------------------------ validators


def _uuid(v: str) -> str:
    if not isinstance(v, str) or not UUID_RE.match(v):
        raise ValueError(f"not a lowercase UUID: {v!r}")
    return v


def _sha256(v: str) -> str:
    if not isinstance(v, str) or not SHA256_RE.match(v):
        raise ValueError("not a 64-char lowercase sha256 hex")
    return v


def _evidence_id(v: str) -> str:
    if not isinstance(v, str) or not EVIDENCE_ID_RE.match(v):
        raise ValueError(f"not an evidence id (ev_<hex16+>): {v!r}")
    return v


def _artifact_id(v: str) -> str:
    if not isinstance(v, str) or not ARTIFACT_ID_RE.match(v):
        raise ValueError(f"not an artifact id (art_<hex16+>): {v!r}")
    return v


def _rfc3339_utc(v: str) -> str:
    if not isinstance(v, str) or not v.endswith("Z"):
        raise ValueError("timestamps must be RFC3339 UTC ending in 'Z'")
    datetime.strptime(v[:19], "%Y-%m-%dT%H:%M:%S")
    return v


def _relpath(v: str) -> str:
    if not isinstance(v, str) or not v:
        raise ValueError("empty path")
    if "\\" in v or v.startswith("/") or re.match(r"^[A-Za-z]:", v):
        raise ValueError(f"path must be relative POSIX: {v!r}")
    parts = v.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"path escapes or is non-canonical: {v!r}")
    if len(v) > 240:
        raise ValueError("path longer than 240 characters")
    return v


UUIDStr = Annotated[str, AfterValidator(_uuid)]
Sha256 = Annotated[str, AfterValidator(_sha256)]
EvidenceId = Annotated[str, AfterValidator(_evidence_id)]
ArtifactId = Annotated[str, AfterValidator(_artifact_id)]
Timestamp = Annotated[str, AfterValidator(_rfc3339_utc)]
RelPath = Annotated[str, AfterValidator(_relpath)]
NonNegMs = Annotated[int, Field(ge=0)]
PosInt = Annotated[int, Field(gt=0)]


def finite(v: float | None) -> float | None:
    if v is not None and (not isinstance(v, (int, float)) or not math.isfinite(v)):
        raise ValueError("number must be finite")
    return v


FiniteFloat = Annotated[float, AfterValidator(finite)]
Unit = Annotated[float, Field(ge=0.0, le=1.0), AfterValidator(finite)]


# ---------------------------------------------------------------- base models


class Record(BaseModel):
    """Canonical stored record: unknown fields rejected, enums by value."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True, frozen=False)

    def dump(self) -> dict[str, Any]:
        # Canonical stored records include nullable fields explicitly.
        return self.model_dump(mode="json", exclude_none=False)


class Interval(Record):
    """Half-open [start_ms, end_ms) on the source presentation timeline."""

    start_ms: NonNegMs
    end_ms: NonNegMs

    @model_validator(mode="after")
    def _ordered(self) -> "Interval":
        if not self.start_ms < self.end_ms:
            raise ValueError(f"interval must satisfy start<end, got [{self.start_ms},{self.end_ms})")
        return self

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def within(self, duration_ms: int) -> bool:
        return self.end_ms <= duration_ms

    def overlap_ms(self, other: "Interval") -> int:
        return max(0, min(self.end_ms, other.end_ms) - max(self.start_ms, other.start_ms))


def check_interval_in_asset(iv: Interval, duration_ms: int, what: str = "interval") -> None:
    if iv.end_ms > duration_ms:
        raise ValueError(f"{what} [{iv.start_ms},{iv.end_ms}) exceeds asset duration {duration_ms}ms")


# ------------------------------------------------------------------ id helpers


def det_uuid(*parts: Any) -> str:
    """Deterministic lowercase UUIDv5 from ordered parts.

    Same inputs -> same ID across runs, which keeps resume and fingerprints
    stable. Parts are joined with an unambiguous separator.
    """
    name = "\x1f".join(str(p) for p in parts)
    return str(uuid.uuid5(EPOCH_NAMESPACE, name))


def new_uuid() -> str:
    return str(uuid.uuid4())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path, chunk: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    """Sorted, compact, UTF-8 JSON used for every fingerprint and digest."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def fingerprint(obj: Any) -> str:
    return sha256_bytes(canonical_json(obj).encode("utf-8"))


def evidence_id(kind: str, ref_id: str, run_scope: str) -> str:
    return "ev_" + sha256_bytes(f"{run_scope}|{kind}|{ref_id}".encode())[:24]


def artifact_id(relative_path: str, sha: str) -> str:
    return "art_" + sha256_bytes(f"{relative_path}|{sha}".encode())[:24]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
