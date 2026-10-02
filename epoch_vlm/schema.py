"""VLM output contract + deterministic validation against the clip context.

Model text -> extract one JSON object -> pydantic (extra=forbid, enums,
limits) -> context checks (frame labels exist, quotes are real transcript
substrings, banned claim classes). Items that break a content rule are
dropped and reported; structural failure triggers the single repair.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Label = str
SceneRole = Literal["talking_head", "a_roll_other", "b_roll", "screen_recording", "slide_or_diagram", "product_closeup",
                    "demo_hands", "title_or_text_card", "graphics_animation", "black_or_blank", "mixed", "unknown"]
ShotScale = Literal["wide", "medium", "close", "extreme_close", "screen", "not_applicable", "unknown"]
Note = str


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _short(v: str, n: int = 400) -> str:
    v = " ".join(str(v).split())
    if len(v) > n:
        raise ValueError(f"text longer than {n} characters")
    return v


class Segment(_M):
    frames: list[Label] = Field(min_length=1, max_length=2)
    scene_role: SceneRole
    shot_scale: ShotScale
    visible_content: str
    on_screen_text: str

    _v = field_validator("visible_content", "on_screen_text")(lambda v: _short(v))


class InformationFlow(_M):
    status: Literal["new_visual_information", "same_information_restated", "static_no_change", "unclear"]
    evidence_frames: list[Label] = Field(max_length=32)
    note: str

    _v = field_validator("note")(lambda v: _short(v))


class SpeechVisualRelation(_M):
    status: Literal["illustrates_speech", "neutral_backdrop", "unrelated", "contradicts", "cannot_judge"]
    evidence_frames: list[Label] = Field(max_length=32)
    transcript_quote: str
    note: str

    _v = field_validator("note", "transcript_quote")(lambda v: _short(v))


class StaticVisual(_M):
    is_static: bool
    useful: Literal["yes", "no", "unclear"]
    reason: str

    _v = field_validator("reason")(lambda v: _short(v))


class TextLegibility(_M):
    frame: Label
    text: str
    concern: Literal["too_small", "too_brief", "occluded", "low_contrast", "cluttered", "none"]
    note: str

    _v = field_validator("text", "note")(lambda v: _short(v))


class TechnicalVisual(_M):
    frames: list[Label] = Field(min_length=1, max_length=32)
    kind: Literal["blur", "black", "frozen", "overexposed", "underexposed", "compression", "framing", "none"]
    note: str

    _v = field_validator("note")(lambda v: _short(v))


class ObservationItem(_M):
    statement: str = Field(min_length=3)
    frames: list[Label] = Field(min_length=1, max_length=32)
    polarity: Literal["supports_viewer", "neutral", "potential_problem"]
    certainty: Literal["clear", "likely", "uncertain"]

    _v = field_validator("statement")(lambda v: _short(v))


class CloserLook(_M):
    needed: bool
    focus: Literal["small_text", "fast_action", "transition", "none"]
    reason: str

    _v = field_validator("reason")(lambda v: _short(v))


class ClipObservation(_M):
    clip_id: str
    frames_reviewed: int = Field(ge=0, le=64)
    segments: list[Segment] = Field(min_length=1, max_length=8)  # descriptive; prompt asks for 1-3
    information_flow: InformationFlow
    speech_visual_relation: SpeechVisualRelation
    static_visual: StaticVisual
    text_legibility: list[TextLegibility] = Field(max_length=4)
    technical_visual: list[TechnicalVisual] = Field(max_length=3)
    observations: list[ObservationItem] = Field(min_length=1, max_length=6)
    needs_closer_look: CloserLook
    unknowns: list[str] = Field(max_length=3)

    _u = field_validator("unknowns")(lambda v: [_short(x) for x in v])


# ------------------------------------------------------------------ parsing

_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


def extract_json(raw: str) -> tuple[dict | None, dict]:
    """Return (object, notes). Hidden reasoning is stripped, never parsed."""
    notes = {"thinking_stripped": False, "fence_stripped": False, "trailing_text": False}
    text = raw
    if "<think>" in text:
        notes["thinking_stripped"] = True
        text = _THINK.sub("", text)
        if "<think>" in text:  # unterminated reasoning: output truncated inside it
            return None, {**notes, "error": "unterminated <think> block (output budget exhausted)"}
    text = text.strip()
    if text.startswith("```"):
        notes["fence_stripped"] = True
        text = _FENCE.sub("", text).strip()
    start = text.find("{")
    if start < 0:
        return None, {**notes, "error": "no JSON object found"}
    try:
        obj, end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        return None, {**notes, "error": f"invalid JSON: {exc.msg} at char {exc.pos}"}
    if text[start + end:].strip():
        notes["trailing_text"] = True
    if not isinstance(obj, dict):
        return None, {**notes, "error": "top-level JSON is not an object"}
    return obj, notes


# ---------------------------------------------------------------- validation

_BANNED = {
    "audio_claim": re.compile(r"\b(music|song|soundtrack|sound effects?|sfx|background audio|voice(?:-| )?over tone|tone of voice|loud|quiet|audio)\b", re.I),
    "emotion_or_mind": re.compile(r"\b(bored|boring|excited|exciting|confident|nervous|anxious|happy|sad|angry|frustrated|enthusiastic|passionate|sincere|insecure|annoyed|engaging|engaged|interesting|captivating)\b", re.I),
    "prediction": re.compile(r"(\d+\s*%|\bpercent\b|\bretention\b|\bviewers? (?:will|would|might|may) (?:leave|drop|stop|click)|\bdrop[- ]?off\b|\bengagement\b)", re.I),
}


def _norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s).casefold().split())


def banned_reason(text: str) -> str | None:
    for name, rx in _BANNED.items():
        if rx.search(text or ""):
            return name
    return None


def validate(obj: dict, *, clip_id: str, labels: list[str], transcript_text: str) -> tuple[ClipObservation | None, list[str], list[dict]]:
    """Return (validated, structural_errors, dropped_items).

    structural_errors non-empty => reject (repair once). Content-rule
    violations drop the offending item only and are reported.
    """
    try:
        m = ClipObservation.model_validate(obj)
    except ValidationError as exc:
        errs = []
        for e in exc.errors()[:12]:
            loc = ".".join(str(x) for x in e["loc"])
            errs.append(f"{loc}: {e['msg']}")
        return None, errs, []
    errors: list[str] = []
    dropped: list[dict] = []
    known = set(labels)
    if m.clip_id != clip_id:
        errors.append(f"clip_id must be '{clip_id}', got '{m.clip_id}'")

    def bad_refs(refs: list[str]) -> list[str]:
        return [r for r in refs if r not in known]

    for i, s in enumerate(m.segments):
        if bad_refs(s.frames):
            errors.append(f"segments.{i}.frames cites unknown labels {bad_refs(s.frames)}")
        elif len(s.frames) == 2 and labels.index(s.frames[0]) > labels.index(s.frames[1]):
            errors.append(f"segments.{i}.frames must be [first, last] in order")
    for path, refs in (("information_flow.evidence_frames", m.information_flow.evidence_frames),
                       ("speech_visual_relation.evidence_frames", m.speech_visual_relation.evidence_frames)):
        if bad_refs(refs):
            errors.append(f"{path} cites unknown labels {bad_refs(refs)}")
    q = m.speech_visual_relation.transcript_quote.strip()
    if q and _norm(q) not in _norm(transcript_text):
        errors.append("speech_visual_relation.transcript_quote is not an exact substring of the TRANSCRIPT lines")
    if errors:
        return None, errors, []

    keep_t = []
    for t in m.text_legibility:
        if t.frame not in known:
            dropped.append({"item": "text_legibility", "reason": "unknown_frame", "value": t.model_dump()})
        else:
            keep_t.append(t)
    m.text_legibility = keep_t
    keep_tv = []
    for t in m.technical_visual:
        why = "unknown_frame" if bad_refs(t.frames) else banned_reason(t.note)
        if why:
            dropped.append({"item": "technical_visual", "reason": why, "value": t.model_dump()})
        else:
            keep_tv.append(t)
    m.technical_visual = keep_tv
    keep_o = []
    for o in m.observations:
        why = "unknown_frame" if bad_refs(o.frames) else banned_reason(o.statement)
        if why:
            dropped.append({"item": "observation", "reason": why, "value": o.model_dump()})
        else:
            keep_o.append(o)
    m.observations = keep_o
    for name in ("information_flow", "speech_visual_relation"):
        part = getattr(m, name)
        why = banned_reason(part.note)
        if why:
            dropped.append({"item": f"{name}.note", "reason": why, "value": part.note})
            part.note = ""
    why = banned_reason(m.static_visual.reason)
    if why:
        dropped.append({"item": "static_visual.reason", "reason": why, "value": m.static_visual.reason})
        m.static_visual.reason = ""
    m.unknowns = [u for u in m.unknowns if not banned_reason(u)]
    return m, [], dropped
