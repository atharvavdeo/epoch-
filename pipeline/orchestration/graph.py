"""Ordered local stage graph for video assets (TRD §1 order, D16 split).

Local:  probe -> proxy, audio, video_scan -> frames -> asr -> align -> ocr
        -> visual_job (bundle for Colab)
Colab:  VLM observations        [imported back with `attach-visual`]
Local:  visual -> embed -> narrative -> score -> export

GPU-free locally: ASR/alignment/embeddings are CPU FP32 (D16), OCR CPU.
"""

from __future__ import annotations

from pipeline.media import stages as media
from pipeline.orchestration.stage import run_stage

VIDEO_STAGE_ORDER = ["probe", "proxy", "audio", "video_scan", "frames", "asr", "align", "ocr", "visual_job",
                     "visual", "embed", "narrative", "score", "export"]
# OCR is opt-in (D18): PaddleOCR on Windows CPU was ~3 s/frame and destabilised the laptop.
# Without it the text track is reported as unknown, never as clean.
LOCAL_PRE_VISUAL = ["probe", "proxy", "audio", "video_scan", "frames", "asr", "align", "visual_job"]


def local_stages(with_ocr: bool) -> list[str]:
    return LOCAL_PRE_VISUAL[:-1] + (["ocr"] if with_ocr else []) + ["visual_job"]


def _step(name: str, source: dict, allow_out_of_scope: bool):
    """Build (spec, fn) lazily so a missing model only fails its own stage."""
    if name == "probe":
        return media.probe_spec(source, allow_out_of_scope), media.probe_stage(source, allow_out_of_scope)
    if name == "proxy":
        return media.proxy_spec(), media.proxy_stage(source)
    if name == "audio":
        return media.audio_spec(), media.audio_stage(source)
    if name == "video_scan":
        return media.video_scan_spec(), media.video_scan_stage(source)
    if name == "frames":
        return media.frames_spec(), media.frames_stage(source)
    if name in ("asr", "align"):
        from pipeline.speech import stages as speech

        return (speech.asr_spec(source), speech.asr_stage(source)) if name == "asr" else (
            speech.align_spec(source), speech.align_stage(source))
    if name == "ocr":
        from pipeline.text_vision import stages as tv

        return tv.ocr_spec(source), tv.ocr_stage(source)
    if name == "visual_job":
        from pipeline.visual import job as vj

        return vj.visual_job_spec(source), vj.visual_job_stage(source)
    raise KeyError(name)


def run_local_until(ws, source: dict, *, until: str, allow_out_of_scope: bool = False, force: set[str] | None = None,
                    retry_partial: bool = False, with_ocr: bool = False) -> bool:
    from pipeline.orchestration.stage import StageError

    force = force or set()
    names = local_stages(with_ocr)
    if until not in names:
        raise StageError("bad_until", f"--until must be one of {names}")
    ok = True
    for name in names:
        try:
            spec, fn = _step(name, source, allow_out_of_scope)
        except StageError as exc:  # e.g. model not downloaded: report, keep going where possible
            print(f"[blocked] {name}: {exc.code}: {exc.message}" + (f"\n  -> {exc.recommended_action}" if exc.recommended_action else ""))
            ws.event(stage=name, event="blocked", code=exc.code, message=exc.message)
            ok = False
            if name == until:
                break
            continue
        rec = run_stage(ws, spec, fn, force=name in force, retry_partial=retry_partial)
        if rec.status in ("failed", "skipped"):
            ok = False
            if name == "probe":
                break
        if name == until:
            break
    return ok


# ------------------------------------------------------------ after Colab

def embed_spec_and_fn(source: dict):
    from pipeline.local_models import manifest, model_fingerprint, offline_env
    from pipeline.orchestration.stage import StageResult, StageSpec

    spec = StageSpec(name="embed", version="1", env="asr", deps=("align",),
                     config={"chunk_words": [100, 200], "top_k": 3, "min_cos": 0.85, "prefix": "passage: "},
                     extra={"model": model_fingerprint("embed")})

    def fn(ctx):
        res = ctx.run_subprocess("pipeline.reasoning.embed_stage", {
            "transcript": str(ctx.dep("align").path("transcript.json")),
            "model_dir": manifest("embed")["snapshot_dir"], "threads": 4}, extra_env=offline_env())
        return StageResult(res["status"], res.get("summary", {}))

    return spec, fn


def attach_visual(ws, source: dict, result_zip) -> bool:
    from pathlib import Path

    from pipeline.visual.attach import select_job_for_result, visual_spec, visual_stage

    result_zip = Path(result_zip).resolve()
    select_job_for_result(ws, result_zip)
    rec = run_stage(ws, visual_spec(source, result_zip), visual_stage(source, result_zip))
    return rec.status in ("complete", "partial")


def run_finish(ws, source: dict, *, force: set[str] | None = None) -> bool:
    """embed -> narrative -> score -> export. Missing visual is reported, never faked."""
    from pipeline.package_export import export_spec, export_stage
    from pipeline.reasoning.narrative import narrative_spec, narrative_stage
    from pipeline.scoring.stage import score_spec, score_stage

    force = force or set()
    if ws.current("visual") is None:
        print("[note] no Colab visual result attached: visual track will be UNKNOWN and the package partial")
    ok = True
    steps = [embed_spec_and_fn(source), (narrative_spec(source), narrative_stage(source)), (score_spec(), score_stage(source)),
             (export_spec(source), export_stage(source, ws))]
    for spec, fn in steps:
        rec = run_stage(ws, spec, fn, force=spec.name in force)
        if rec.status in ("failed", "skipped"):
            ok = False
            if spec.name in ("score", "export"):
                break
    return ok
