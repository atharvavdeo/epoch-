"""Controller-side specs for the speech stages (executed in the asr env)."""

from __future__ import annotations

from pipeline.local_models import manifest, model_fingerprint, offline_env
from pipeline.orchestration.io import read_json
from pipeline.orchestration.settings import setting
from pipeline.orchestration.stage import StageContext, StageError, StageResult, StageSpec

ASR_CONFIG = {
    "beam_size": 5,
    "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
    "seed": 1234,
    "condition_on_previous_text": True,
    "compression_ratio_threshold": 2.4,
    "log_prob_threshold": -1.0,
    "no_speech_threshold": 0.6,
    "vad": {"threshold": 0.5, "min_speech_duration_ms": 250, "min_silence_duration_ms": 500, "speech_pad_ms": 200},
    "chunk_target_s": 300,
    "compute_type": "float32",
    "device": "cpu",
}


def _threads() -> int:
    v = setting("EPOCH_ASR_THREADS", "0")
    return int(v) if v.isdigit() else 0


def asr_spec(source: dict) -> StageSpec:
    return StageSpec(name="asr", version="1", env="asr", deps=("audio",), config=ASR_CONFIG,
                     extra={"model": model_fingerprint("asr"), "language": source["project"]["declared_language"]},
                     versions={"faster_whisper": "1.2.1", "ctranslate2": "4.6.0"})


def asr_stage(source: dict):
    def fn(ctx: StageContext) -> StageResult:
        audio = ctx.dep("audio")
        if read_json(audio.path("audio.json")).get("status") == "no_audio":
            raise StageError("no_audio", "video has no audio stream; speech is unknown, not silent")
        res = ctx.run_subprocess("pipeline.speech.asr_stage", {
            "wav": str(audio.path("audio16k.wav")), "model_dir": manifest("asr")["snapshot_dir"],
            "language": source["project"]["declared_language"], "threads": _threads(), "config": ASR_CONFIG,
        }, extra_env=offline_env())
        return StageResult(res["status"], res.get("summary", {}))

    return fn


def align_spec(source: dict) -> StageSpec:
    return StageSpec(name="align", version="1", env="asr", deps=("asr", "audio"),
                     config={"aligner_policy": "en->align_en; hi|mixed->align_hi", "interpolation": "discarded"},
                     extra={"align_en": model_fingerprint("align_en"), "align_hi": model_fingerprint("align_hi"),
                            "asset_sha256": source["sha256"]},
                     versions={"whisperx": "3.8.6", "transformers": "4.57.6"})


def align_stage(source: dict):
    def fn(ctx: StageContext) -> StageResult:
        asr = ctx.dep("asr")
        res = ctx.run_subprocess("pipeline.speech.align_stage", {
            "asr_segments": str(asr.path("asr_segments.json")), "wav": str(ctx.dep("audio").path("audio16k.wav")),
            "asset_sha256": source["sha256"], "asr_fingerprint": asr.fingerprint, "threads": _threads(),
            "aligners": {"en": manifest("align_en")["snapshot_dir"], "hi": manifest("align_hi")["snapshot_dir"]},
        }, extra_env=offline_env())
        return StageResult(res["status"], res.get("summary", {}))

    return fn
