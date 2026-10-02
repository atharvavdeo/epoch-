import math

import pytest
from pydantic import ValidationError

from contracts.common import Interval, canonical_json, det_uuid, evidence_id, fingerprint, utc_now
from contracts.entities import EditSuggestion, Issue, Manifest, Signal, Word

RUN = det_uuid("run")
SUG = det_uuid("sug")
EV = evidence_id("transcript", "seg1", "asset")


def _issue(**kw):
    base = dict(
        issue_id=det_uuid("i"), run_id=RUN, type="slow_intro",
        affected_interval={"start_ms": 0, "end_ms": 30000}, modality_tags=["speech"],
        risk_track="narrative", severity="medium", evidence_status="supported",
        evidence_ids=[EV], explanation="x", counter_explanation="y",
        suggested_edit_ids=[SUG], cause_group_id=det_uuid("c"),
    )
    base.update(kw)
    return Issue.model_validate(base)


def test_interval_is_half_open_and_ordered():
    assert Interval(start_ms=0, end_ms=1).duration_ms == 1
    for bad in [(5, 5), (6, 5), (-1, 3)]:
        with pytest.raises(ValidationError):
            Interval(start_ms=bad[0], end_ms=bad[1])


def test_det_uuid_is_stable_lowercase_uuid():
    a, b = det_uuid("x", 1), det_uuid("x", 1)
    assert a == b and a == a.lower() and len(a) == 36
    assert det_uuid("x", 1) != det_uuid("x1")  # separator prevents concatenation collisions


def test_canonical_json_rejects_nan_and_sorts():
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    with pytest.raises(ValueError):
        canonical_json({"a": math.nan})
    assert fingerprint({"a": 1}) == fingerprint({"a": 1})


def test_issue_rejects_extra_fields_unknown_enum_and_wrong_track():
    _issue()
    with pytest.raises(ValidationError):
        _issue(made_up_field=1)
    with pytest.raises(ValidationError):
        _issue(type="boring_section")
    with pytest.raises(ValidationError):
        _issue(risk_track="visual")  # slow_intro belongs to narrative
    with pytest.raises(ValidationError):
        _issue(evidence_ids=[])
    with pytest.raises(ValidationError):
        _issue(evidence_status="unknown")
    with pytest.raises(ValidationError):
        _issue(issue_id="NOT-A-UUID")


def test_repetition_requires_comparison_interval():
    with pytest.raises(ValidationError):
        _issue(type="unnecessary_repetition")
    _issue(type="unnecessary_repetition", comparison_intervals=[{"start_ms": 1000, "end_ms": 2000}])


def test_signal_null_needs_reason_and_rejects_nan():
    base = dict(signal_id=det_uuid("s"), run_id=RUN, feature_id="F23", interval={"start_ms": 0, "end_ms": 500},
                modality="visual", name="luma_mean", unit="ratio", method="pyav", validity="measured")
    Signal.model_validate({**base, "value": 0.4})
    with pytest.raises(ValidationError):
        Signal.model_validate({**base, "value": None})
    with pytest.raises(ValidationError):
        Signal.model_validate({**base, "value": {"x": [1.0, float("inf")]}})


def test_word_times_null_together():
    seg = det_uuid("seg")
    Word(word_id=det_uuid("w"), segment_id=seg, text="hi", start_ms=None, end_ms=None, alignment_status="unaligned")
    with pytest.raises(ValidationError):
        Word(word_id=det_uuid("w"), segment_id=seg, text="hi", start_ms=10, end_ms=None, alignment_status="aligned")
    with pytest.raises(ValidationError):  # never fabricate aligned status without times
        Word(word_id=det_uuid("w"), segment_id=seg, text="hi", start_ms=None, end_ms=None, alignment_status="aligned")


def test_edit_suggestion_shapes():
    common = dict(suggestion_id=SUG, run_id=RUN, issue_ids=[det_uuid("i")], rationale="r", prerequisites=[])
    EditSuggestion.model_validate({**common, "operation": "cut", "source_interval": {"start_ms": 0, "end_ms": 10},
                                   "destination_ms": None, "proposed_text": None, "requires_reanalysis": False})
    with pytest.raises(ValidationError):  # move into itself
        EditSuggestion.model_validate({**common, "operation": "move", "source_interval": {"start_ms": 0, "end_ms": 10},
                                       "destination_ms": 5, "proposed_text": None, "requires_reanalysis": True})
    with pytest.raises(ValidationError):  # rewrite needs wording
        EditSuggestion.model_validate({**common, "operation": "rewrite", "source_interval": {"start_ms": 0, "end_ms": 10},
                                       "destination_ms": None, "proposed_text": " ", "requires_reanalysis": True})
    with pytest.raises(ValidationError):  # rewrite cannot claim a measured effect
        EditSuggestion.model_validate({**common, "operation": "rewrite", "source_interval": {"start_ms": 0, "end_ms": 10},
                                       "destination_ms": None, "proposed_text": "new", "requires_reanalysis": False})


def test_manifest_rejects_self_listing_dupes_and_unreasoned_missing():
    now = utc_now()
    base = dict(schema_version="1.0.0", package_id=det_uuid("p"), project_id=det_uuid("pr"), asset_id=det_uuid("a"),
                run_id=RUN, created_at=now, package_kind="partial_analysis", source_sha256="a" * 64,
                files=[], required_stage_names=["visual"], completed_stage_names=[],
                missing_stage_names=["visual"], missing_stage_reasons={"visual": "awaiting colab"},
                exported_by_version="t")
    Manifest.model_validate(base)
    with pytest.raises(ValidationError):
        Manifest.model_validate({**base, "missing_stage_reasons": {}})
    with pytest.raises(ValidationError):
        Manifest.model_validate({**base, "package_kind": "analysis"})
    f = dict(artifact_id="art_" + "0" * 24, kind="data", relative_path="data/a.json", sha256="b" * 64, bytes=1,
             producer_stage_id="s", input_fingerprint="c" * 64, created_at=now)
    with pytest.raises(ValidationError):
        Manifest.model_validate({**base, "files": [f, {**f, "relative_path": "DATA/A.json"}]})
    for bad in ["../x.json", "/abs.json", "C:/x.json", "a\\b.json", "a/./b.json"]:
        with pytest.raises(ValidationError):
            Manifest.model_validate({**base, "files": [{**f, "relative_path": bad}]})
