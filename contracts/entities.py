"""Entity contracts (Schema.md §2) used by Phase 1.

P2/P3-only entities (EditPlan, TimelineMap, ChatMessage, RerunRequest,
ActualMetricSeries, Evaluation) are intentionally not defined yet; they are
added with the milestone that first uses them so no untested contract ships.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from contracts.common import (
    ArtifactId,
    Category,
    EvidenceId,
    EvidenceStatus,
    FiniteFloat,
    Interval,
    Language,
    Modality,
    NonNegMs,
    PosInt,
    Precision,
    Record,
    RelPath,
    RiskTrack,
    RunStatus,
    Severity,
    Sha256,
    StageStatus,
    Timestamp,
    Unit,
    UUIDStr,
)

# ------------------------------------------------------------------- errors


class ErrorObject(Record):
    """Schema §7 error object."""

    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=2000)
    stage: str | None
    retryable: bool
    attempt: int = Field(ge=0)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    recommended_action: str | None
    occurred_at: Timestamp


# ---------------------------------------------------------------- artifacts


class Artifact(Record):
    artifact_id: ArtifactId
    kind: str = Field(min_length=1, max_length=60)
    relative_path: RelPath
    sha256: Sha256
    # Schema §3 requires empty JSONL files for stages with no rows, so 0 is valid here
    # (reconciles §1 "bytes are positive"; see ARCHITECTURE decision log R-01).
    bytes: int = Field(ge=0)
    producer_stage_id: str = Field(min_length=1)
    input_fingerprint: Sha256
    created_at: Timestamp


# ---------------------------------------------------------- project / asset


class Project(Record):
    project_id: UUIDStr
    title: str = Field(min_length=1, max_length=300)
    category: Category
    declared_language: Language
    created_at: Timestamp
    updated_at: Timestamp
    active_run_id: UUIDStr | None = None
    description: str | None = None


class StreamInfo(Record):
    index: int = Field(ge=0)
    type: Literal["video", "audio", "subtitle", "data", "attachment", "unknown"]
    codec: str | None


class VideoMetadata(Record):
    container: str
    width: PosInt
    height: PosInt
    display_width: PosInt  # after rotation
    display_height: PosInt
    rotation: Literal[0, 90, 180, 270]
    fps_num: PosInt
    fps_den: PosInt
    vfr: bool
    source_start_pts: int
    time_base_num: PosInt
    time_base_den: PosInt
    has_audio: bool
    video_codec: str
    audio_codec: str | None
    audio_sample_rate: int | None
    audio_channels: int | None
    frame_count: int | None
    streams: list[StreamInfo]


class ScriptMetadata(Record):
    word_count: PosInt
    estimated_wpm: PosInt
    timing: Literal["estimated_script"] = "estimated_script"


class Asset(Record):
    asset_id: UUIDStr
    project_id: UUIDStr
    kind: Literal["video", "script"]
    sha256: Sha256
    original_name: str = Field(min_length=1, max_length=400)
    bytes: PosInt
    duration_ms: PosInt
    time_origin: Literal["source_pts", "estimated_script"]
    metadata: VideoMetadata | ScriptMetadata
    parent_asset_id: UUIDStr | None = None
    original_media_artifact_id: ArtifactId | None = None

    @model_validator(mode="after")
    def _kind_matches(self) -> "Asset":
        if self.kind == "video" and (self.time_origin != "source_pts" or not isinstance(self.metadata, VideoMetadata)):
            raise ValueError("video asset requires time_origin=source_pts and video metadata")
        if self.kind == "script" and (
            self.time_origin != "estimated_script" or not isinstance(self.metadata, ScriptMetadata)
        ):
            raise ValueError("script asset requires time_origin=estimated_script and script metadata")
        return self


# ------------------------------------------------------- run / stage / prov


class Stage(Record):
    stage_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    status: StageStatus
    fingerprint: Sha256 | None
    attempt_count: int = Field(ge=0)
    artifact_ids: list[ArtifactId] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    started_at: Timestamp | None = None
    finished_at: Timestamp | None = None
    error: ErrorObject | None = None
    versions: dict[str, str] | None = None
    config: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _started_requires_versions(self) -> "Stage":
        if self.status not in ("pending", "skipped") and (self.versions is None or self.config is None):
            raise ValueError(f"stage {self.name}: versions and config are required once started")
        if self.status in ("failed",) and self.error is None:
            raise ValueError(f"stage {self.name}: failed stage needs an error object")
        return self


class ModelRecord(Record):
    role: str
    model_id: str
    revision: str
    weight_digest: str | None
    dtype: str
    device: str


class LockRecord(Record):
    name: str
    sha256: Sha256


class PromptRecord(Record):
    prompt_id: str
    sha256: Sha256


class Provenance(Record):
    code_revision: str = Field(min_length=1)
    environment_locks: list[LockRecord]
    models: list[ModelRecord]
    prompts: list[PromptRecord]
    hardware: dict[str, Any]
    precision: str
    sampling_profile: dict[str, Any]
    detector_config: dict[str, Any]
    scoring_version: str
    source_rights_note: str
    external_service_model: str | None = None


class Run(Record):
    run_id: UUIDStr
    project_id: UUIDStr
    asset_id: UUIDStr
    status: RunStatus
    schema_version: str
    config_hash: Sha256
    input_fingerprint: Sha256
    model_profile: str
    created_at: Timestamp
    stages: list[Stage]
    coverage_summary: dict[str, Any]
    provenance: Provenance
    parent_run_id: UUIDStr | None = None
    source_edit_plan_id: UUIDStr | None = None
    finished_at: Timestamp | None = None


# ------------------------------------------------------------- extraction


class TranscriptSegment(Record):
    segment_id: UUIDStr
    run_id: UUIDStr
    interval: Interval
    text: str = Field(min_length=1)
    language: Language
    precision: Precision
    source: Literal["asr", "user"]
    word_ids: list[UUIDStr]
    speaker_id: str | None = None
    original_asr_text: str | None = None
    correction_revision: int = Field(default=0, ge=0)


class Word(Record):
    word_id: UUIDStr
    segment_id: UUIDStr
    text: str = Field(min_length=1)
    start_ms: NonNegMs | None
    end_ms: NonNegMs | None
    alignment_status: Literal["aligned", "unaligned", "estimated"]
    detector_confidence: Unit | None = None

    @model_validator(mode="after")
    def _times_together(self) -> "Word":
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("word start/end must both be null or both set")
        if self.start_ms is not None and not self.start_ms < self.end_ms:  # type: ignore[operator]
            raise ValueError("word start must be < end")
        if self.alignment_status == "unaligned" and self.start_ms is not None:
            raise ValueError("unaligned words carry null times")
        if self.alignment_status != "unaligned" and self.start_ms is None:
            raise ValueError("aligned/estimated words need times")
        return self


class Shot(Record):
    shot_id: UUIDStr
    run_id: UUIDStr
    interval: Interval
    start_boundary_source: Literal["video_start", "adaptive_detector", "decode_gap"]
    end_boundary_source: Literal["video_end", "adaptive_detector", "decode_gap"]
    metrics: dict[str, Any]
    boundary_confidence: FiniteFloat | None = None
    scene_id: str | None = None


SamplingReason = Literal[
    "uniform_1fps",
    "shot_boundary_before",
    "shot_boundary_after",
    "refinement_2fps",
    "text_crop",
]


class Frame(Record):
    frame_id: UUIDStr
    artifact_id: ArtifactId
    at_ms: NonNegMs
    source_pts: int
    time_base_num: PosInt
    time_base_den: PosInt
    width: PosInt
    height: PosInt
    source_width: PosInt
    source_height: PosInt
    sampling_reason: SamplingReason
    crop_box: list[int] | None = None  # [x0,y0,x1,y1] in original (display) pixels
    clip_id: str | None = None
    transformations: list[str]

    @model_validator(mode="after")
    def _crop(self) -> "Frame":
        if self.crop_box is not None:
            x0, y0, x1, y1 = self.crop_box if len(self.crop_box) == 4 else (0, 0, 0, 0)
            if len(self.crop_box) != 4 or not (0 <= x0 < x1 <= self.source_width and 0 <= y0 < y1 <= self.source_height):
                raise ValueError("crop_box must be [x0,y0,x1,y1] inside source pixels")
        return self


class OCRSample(Record):
    frame_id: UUIDStr
    quad: list[list[FiniteFloat]]  # 4 points [x,y] in source (display) pixels
    observed_text: str
    confidence: Unit

    @model_validator(mode="after")
    def _quad(self) -> "OCRSample":
        if len(self.quad) != 4 or any(len(p) != 2 for p in self.quad):
            raise ValueError("quad must be 4 [x,y] points")
        return self


class OCRTrack(Record):
    track_id: UUIDStr
    run_id: UUIDStr
    interval: Interval
    text: str = Field(min_length=1)
    language: Language
    samples: list[OCRSample] = Field(min_length=1)
    visibility_precision: Literal["sampled"] = "sampled"
    detector_confidence: Unit


class Signal(Record):
    signal_id: UUIDStr
    run_id: UUIDStr
    feature_id: str = Field(pattern=r"^(F\d{2}|X\d{2})$")
    interval: Interval
    modality: Modality
    name: str = Field(min_length=1, max_length=80)
    value: Any
    unit: str
    method: str = Field(min_length=1)
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    validity: Literal["measured", "estimated", "unknown"]
    unknown_reason: str | None = None

    @model_validator(mode="after")
    def _null_needs_reason(self) -> "Signal":
        if self.value is None and not self.unknown_reason:
            raise ValueError("signal with null value requires unknown_reason")
        if self.validity == "unknown" and not self.unknown_reason:
            raise ValueError("unknown validity requires unknown_reason")
        _assert_finite_tree(self.value)
        return self


def _assert_finite_tree(v: Any) -> None:
    import math

    if isinstance(v, float) and not math.isfinite(v):
        raise ValueError("non-finite number in signal value")
    if isinstance(v, dict):
        for x in v.values():
            _assert_finite_tree(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            _assert_finite_tree(x)


class Observation(Record):
    observation_id: UUIDStr
    run_id: UUIDStr
    clip_id: str
    interval: Interval
    modality: Modality
    statement: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[EvidenceId]
    status: EvidenceStatus
    sampled_frame_ids: list[UUIDStr]
    model_revision: str
    prompt_hash: Sha256
    unknown_reason: str | None = None

    @model_validator(mode="after")
    def _unknown(self) -> "Observation":
        if self.status == "unknown" and not self.unknown_reason:
            raise ValueError("unknown observation requires unknown_reason")
        if self.status != "unknown" and not self.evidence_ids:
            raise ValueError("a non-unknown observation must cite evidence")
        return self


EvidenceKind = Literal["transcript", "frame", "ocr", "signal", "observation"]


class Evidence(Record):
    evidence_id: EvidenceId
    run_id: UUIDStr
    asset_id: UUIDStr
    kind: EvidenceKind
    ref_id: str = Field(min_length=1)
    interval: Interval
    precision: Precision
    provenance_stage_id: str
    quote: str | None = None


class Coverage(Record):
    run_id: UUIDStr
    modality: Modality
    interval: Interval
    status: Literal["observed", "partial", "unknown", "not_applicable"]
    sampling_profile: str
    evidence_ids: list[EvidenceId] = Field(default_factory=list)
    reason: str | None = None

    @model_validator(mode="after")
    def _reason(self) -> "Coverage":
        if self.status in ("partial", "unknown") and not self.reason:
            raise ValueError("partial/unknown coverage requires a reason")
        return self


# ---------------------------------------------------------------- reasoning


class PromiseStatus(str, Enum):
    unaddressed = "unaddressed"
    partial = "partial"
    fulfilled = "fulfilled"
    uncertain = "uncertain"


class Promise(Record):
    promise_id: UUIDStr
    run_id: UUIDStr
    title_quote: str = Field(min_length=1)
    obligation: str = Field(min_length=1, max_length=600)
    setup_evidence_ids: list[EvidenceId]
    fulfilment_evidence_ids: list[EvidenceId]
    status: PromiseStatus
    partial_interval: Interval | None = None
    fulfilled_interval: Interval | None = None

    @model_validator(mode="after")
    def _fulfilled(self) -> "Promise":
        if self.status == "fulfilled" and (not self.fulfilment_evidence_ids or self.fulfilled_interval is None):
            raise ValueError("fulfilled promise needs fulfilment evidence and interval")
        if self.status == "partial" and self.partial_interval is None:
            raise ValueError("partial promise needs partial_interval")
        return self


ISSUE_TYPES = (
    "delayed_payoff",
    "slow_intro",
    "unnecessary_repetition",
    "tangent",
    "unresolved_promise",
    "dead_air",
    "rushed_delivery",
    "visual_stagnation",
    "visual_speech_mismatch",
    "unreadable_text",
    "visual_overload",
    "technical_visual_fault",
    "technical_audio_fault",
    "disruptive_cta",
    "weak_transition",
)
IssueType = Literal[
    "delayed_payoff",
    "slow_intro",
    "unnecessary_repetition",
    "tangent",
    "unresolved_promise",
    "dead_air",
    "rushed_delivery",
    "visual_stagnation",
    "visual_speech_mismatch",
    "unreadable_text",
    "visual_overload",
    "technical_visual_fault",
    "technical_audio_fault",
    "disruptive_cta",
    "weak_transition",
]
# FEATURES "Initial issue ontology": contextual types enter in P2.
P1_ISSUE_TYPES = tuple(
    t for t in ISSUE_TYPES if t not in ("visual_speech_mismatch", "unreadable_text", "visual_overload", "weak_transition")
)

# One risk track per issue type (RETENTION_MODEL §2: exactly one track).
ISSUE_TRACK: dict[str, str] = {
    "delayed_payoff": "narrative",
    "slow_intro": "narrative",
    "unnecessary_repetition": "narrative",
    "tangent": "narrative",
    "unresolved_promise": "narrative",
    "disruptive_cta": "narrative",
    "weak_transition": "narrative",
    "dead_air": "pacing",
    "rushed_delivery": "pacing",
    "visual_stagnation": "visual",
    "visual_speech_mismatch": "visual",
    "visual_overload": "visual",
    "unreadable_text": "text",
    "technical_visual_fault": "technical",
    "technical_audio_fault": "technical",
}


class Issue(Record):
    issue_id: UUIDStr
    run_id: UUIDStr
    type: IssueType
    affected_interval: Interval
    modality_tags: list[Modality] = Field(min_length=1)
    risk_track: RiskTrack
    severity: Severity
    evidence_status: EvidenceStatus
    evidence_ids: list[EvidenceId] = Field(min_length=1)
    explanation: str = Field(min_length=1, max_length=2000)
    counter_explanation: str = Field(min_length=1, max_length=2000)
    # R-02: may be empty when every proposed edit failed the content-retention guard (no safe edit)
    suggested_edit_ids: list[UUIDStr] = Field(default_factory=list)
    review_status: Literal["open", "accepted", "dismissed"] = "open"
    cause_group_id: UUIDStr
    comparison_intervals: list[Interval] | None = None
    review_reason: str | None = None

    @model_validator(mode="after")
    def _track(self) -> "Issue":
        if ISSUE_TRACK[self.type] != self.risk_track:
            raise ValueError(f"issue type {self.type} belongs to track {ISSUE_TRACK[self.type]}")
        if self.evidence_status == "unknown":
            raise ValueError("unknown evidence cannot produce an accepted issue")
        if self.type == "unnecessary_repetition" and not self.comparison_intervals:
            raise ValueError("repetition issues must cite the earlier occurrence in comparison_intervals")
        return self


class EditSuggestion(Record):
    suggestion_id: UUIDStr
    run_id: UUIDStr
    issue_ids: list[UUIDStr] = Field(min_length=1)
    operation: Literal["cut", "move", "rewrite", "insert_visual", "adjust_audio"]
    source_interval: Interval | None
    destination_ms: NonNegMs | None
    proposed_text: str | None
    rationale: str = Field(min_length=1, max_length=2000)
    prerequisites: list[str] = Field(default_factory=list)
    requires_reanalysis: bool

    @model_validator(mode="after")
    def _shape(self) -> "EditSuggestion":
        op = self.operation
        if op in ("cut", "move", "rewrite", "adjust_audio") and self.source_interval is None:
            raise ValueError(f"{op} requires source_interval")
        if op == "move":
            if self.destination_ms is None:
                raise ValueError("move requires destination_ms")
            si = self.source_interval
            if si is not None and si.start_ms <= self.destination_ms <= si.end_ms:
                raise ValueError("move destination cannot be inside the moved span")
        if op == "insert_visual" and self.source_interval is None and self.destination_ms is None:
            raise ValueError("insert_visual needs a source_interval or destination_ms")
        if op == "rewrite" and not (self.proposed_text and self.proposed_text.strip()):
            raise ValueError("rewrite requires proposed_text")
        if op in ("rewrite", "insert_visual", "adjust_audio", "move") and not self.requires_reanalysis:
            raise ValueError(f"{op} has no measured effect without reanalysis (RETENTION_MODEL §5)")
        return self


# ------------------------------------------------------------------ scoring


class TrackValue(Record):
    risk: Unit | None  # r[k,b]; null when wholly unknown
    coverage: Unit  # c[k,b]
    lower: Unit  # l = c*r
    upper: Unit  # u = c*r + (1-c)


class RiskBin(Record):
    run_id: UUIDStr
    interval: Interval
    track_values: dict[str, TrackValue]
    combined_lower: Unit
    combined_upper: Unit
    display_value: int | None = Field(default=None, ge=0, le=100)
    evidence_coverage: Unit
    contributing_issue_ids: list[UUIDStr]

    @model_validator(mode="after")
    def _bounds(self) -> "RiskBin":
        if self.combined_lower > self.combined_upper + 1e-9:
            raise ValueError("combined_lower > combined_upper")
        return self


class Bound(Record):
    lower: FiniteFloat
    upper: FiniteFloat
    central: FiniteFloat | None = None

    @model_validator(mode="after")
    def _ordered(self) -> "Bound":
        if self.lower > self.upper + 1e-9:
            raise ValueError("bound lower > upper")
        return self


class ScenarioBin(Record):
    start_ms: NonNegMs
    end_ms: NonNegMs
    baseline_start: FiniteFloat
    baseline_end: FiniteFloat
    retention_start: Bound
    retention_end: Bound
    risk: Bound
    conditional_drop: Bound | None
    absolute_drop: Bound | None


class TopRegion(Record):
    interval: Interval
    max_risk: Unit
    score: FiniteFloat
    dominant_cause_group_id: UUIDStr | None
    issue_ids: list[UUIDStr]


class ScenarioAssumptions(Record):
    retention_at_30s: float = Field(gt=0.0, le=1.0)
    retention_at_end: float = Field(gt=0.0, le=1.0)
    kappa: float = Field(ge=0.0, le=10.0)
    acknowledged: bool = False

    @model_validator(mode="after")
    def _order(self) -> "ScenarioAssumptions":
        if self.retention_at_end > self.retention_at_30s:
            raise ValueError("require 0 < retention_at_end <= retention_at_30s <= 1")
        return self


class ScenarioSummary(Record):
    duration_ms: PosInt
    assumed_avd_seconds: Bound
    assumed_apv_pct: Bound
    assumed_end_pct: Bound | None
    top_regions: list[TopRegion]


class RetentionScenario(Record):
    scenario_id: UUIDStr
    base_run_id: UUIDStr
    edit_plan_id: UUIDStr | None = None
    mode: Literal["baseline", "hypothetical", "reanalysed"]
    formula_version: str
    scoring_profile: Literal["multimodal-v1", "script-only-v1"]
    assumptions: ScenarioAssumptions
    bins: list[ScenarioBin]
    summary: ScenarioSummary
    coverage_status: Literal["complete", "partial"]
    labels: list[str]
    created_at: Timestamp


# ------------------------------------------------------------- prediction
# Text retention model (pipeline/predict). Rule-based priors, never calibrated in P1: `calibrated` is pinned
# False so a package cannot claim otherwise.


class PredictionSecond(Record):
    t: int = Field(ge=0)
    retention: Unit
    lower: Unit
    upper: Unit
    neutral: Unit
    loss: Unit
    excess_loss: Unit
    contributions: dict[str, Unit]
    protective: list[str]


class DropReason(Record):
    feature: str
    share: Unit
    text: str


class DropMoment(Record):
    start_s: int = Field(ge=0)
    end_s: int = Field(ge=0)
    excess_loss: Unit
    retention_before: Unit
    retention_after: Unit
    reasons: list[DropReason]
    quote: str | None = None
    issue_ids: list[UUIDStr] = Field(default_factory=list)


class RetentionPrediction(Record):
    prediction_id: UUIDStr
    run_id: UUIDStr
    model_version: str
    label: str
    calibrated: Literal[False]
    anchors: dict[str, Unit]
    features: list[dict[str, Unit]]
    per_second: list[PredictionSecond]
    summary: dict[str, Any]
    drop_moments: list[DropMoment]
    weights: dict[str, Any]
    notes: list[str]
    feature_info: dict[str, Any]
    created_at: Timestamp


# ------------------------------------------------------------------ package


class Manifest(Record):
    schema_version: str
    package_id: UUIDStr
    project_id: UUIDStr
    asset_id: UUIDStr
    run_id: UUIDStr
    created_at: Timestamp
    package_kind: Literal["analysis", "partial_analysis"]
    source_sha256: Sha256
    files: list[Artifact]
    required_stage_names: list[str]
    completed_stage_names: list[str]
    missing_stage_names: list[str]
    missing_stage_reasons: dict[str, str] = Field(default_factory=dict)
    exported_by_version: str

    @model_validator(mode="after")
    def _consistency(self) -> "Manifest":
        paths = [f.relative_path for f in self.files]
        lowered = [p.lower() for p in paths]
        if len(set(lowered)) != len(lowered):
            raise ValueError("duplicate (case-normalised) paths in manifest")
        if "manifest.json" in lowered:
            raise ValueError("manifest must not list itself")
        missing = set(self.missing_stage_names)
        if missing - set(self.missing_stage_reasons):
            raise ValueError(f"missing stages need reasons: {sorted(missing - set(self.missing_stage_reasons))}")
        if missing & set(self.completed_stage_names):
            raise ValueError("a stage cannot be both completed and missing")
        if self.package_kind == "analysis" and missing:
            raise ValueError("a complete analysis package cannot have missing stages")
        return self
