"""Controller-side OCR stage spec (inference runs in the ocr env)."""

from __future__ import annotations

import json

from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.settings import models_dir
from pipeline.orchestration.stage import StageContext, StageError, StageResult, StageSpec

OCR_MODELS = {"det": "PP-OCRv5_mobile_det",
              "rec": {"en": "en_PP-OCRv5_mobile_rec", "hi": "devanagari_PP-OCRv5_mobile_rec"}}


def paddle_env() -> dict[str, str]:
    return {"PADDLE_PDX_CACHE_HOME": str(models_dir() / "paddlex"),
            "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True",
            "PADDLE_PDX_MODEL_SOURCE": "huggingface"}


def rec_model_for(language: str) -> str:
    return OCR_MODELS["rec"]["en" if language == "en" else "hi"]


def ocr_config(language: str) -> dict:
    return {"det_model": OCR_MODELS["det"], "rec_model": rec_model_for(language), "det_limit_type": "max",
            "det_limit_side_len": 1280, "min_score_for_tracks": 0.5, "iou_min": 0.5, "text_sim_min": 0.8,
            "max_missing_samples": 1, "identical_frame_mae": 0.6, "enable_mkldnn": False}


def _manifest_digests(cfg: dict) -> dict:
    p = models_dir() / "manifests" / "paddleocr.json"
    if not p.exists():
        raise StageError("model_missing", "PaddleOCR models are not downloaded/qualified",
                         recommended_action=".venvs/ocr/Scripts/python.exe scripts/setup_ocr_models.py")
    man = json.loads(p.read_text(encoding="utf-8"))
    return {k: man["models"][k]["digest"] for k in (cfg["det_model"], cfg["rec_model"])}


def ocr_spec(source: dict) -> StageSpec:
    cfg = ocr_config(source["project"]["declared_language"])
    return StageSpec(name="ocr", version="1", env="ocr", deps=("frames", "probe"), config=cfg,
                     extra={"model_digests": _manifest_digests(cfg)},
                     versions={"paddleocr": "3.7.0", "paddlepaddle": "3.3.1"})


def ocr_stage(source: dict):
    def fn(ctx: StageContext) -> StageResult:
        frames = ctx.dep("frames")
        grid = read_json(frames.path("grid.json"))
        work = [{"frame_id": g["frame_id"], "at_ms": g["at_ms"], "path": str(frames.path(f"src/{g['frame_id']}.jpg"))}
                for g in grid]
        write_json(ctx.out / "_frames_in.json", work)
        probe = read_json(ctx.dep("probe").path("probe.json"))
        res = ctx.run_subprocess("pipeline.text_vision.ocr_stage", {
            "frames": str(ctx.out / "_frames_in.json"), "config": ocr_config(source["project"]["declared_language"]),
            "video_end_ms": probe["video_end_ms"]}, extra_env=paddle_env())
        return StageResult(res["status"], res.get("summary", {}))

    return fn
