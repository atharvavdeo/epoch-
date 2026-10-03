"""Serial upload worker entry point, executed in the isolated media environment."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.orchestration.io import read_json, write_json
from pipeline.orchestration.stage import StageError, run_stage


def event(**data):
    print("[epoch-job] " + json.dumps(data), flush=True)


def run(request: dict) -> dict:
    from pipeline.orchestration.graph import _step, embed_spec_and_fn, local_stages
    from pipeline.orchestration.workspace import register_video
    from pipeline.package_export import export_spec, export_stage
    from pipeline.predict.stage import predict_spec, predict_stage
    from pipeline.reasoning.narrative import narrative_spec, narrative_stage
    from pipeline.reasoning.jev import jev_spec, jev_stage
    from pipeline.media.voice import voice_spec, voice_stage
    from pipeline.scoring.stage import score_spec, score_stage
    from pipeline.outputs import export_outputs

    path, project, kind = Path(request["path"]), request["project"], request["kind"]
    if kind == "text":
        from pipeline.script.stage import register_script, script_spec, script_stage
        ws, source = register_script(path, project)
        names = ["script"]
    else:
        if kind == "audio":
            from pipeline.cli import wrap_audio
            path = wrap_audio(path)
        ws, source = register_video(path, title=project["title"], category=project["category"],
                                    language=project["declared_language"], project_id=project["project_id"],
                                    description=project.get("description"))
        names = ["probe", "proxy", "audio", "asr", "align"] if kind == "audio" else local_stages(False)
    finish = ["embed", "narrative", "predict"] + (["voice"] if kind != "text" else []) + ["jev", "score", "export"]
    steps = names + finish
    states = []
    for i, name in enumerate(steps):
        event(stage=name, stages=states + [{"name": name, "status": "running"}], progress=i / (len(steps) + 1))
        if name == "script":
            spec, fn = script_spec(source), script_stage(source)
        elif name in names:
            spec, fn = _step(name, source, True)
        elif name == "embed":
            spec, fn = embed_spec_and_fn(source)
        elif name == "narrative":
            spec, fn = narrative_spec(source), narrative_stage(source)
        elif name == "predict":
            spec, fn = predict_spec(source), predict_stage(source)
        elif name == "voice":
            spec, fn = voice_spec(), voice_stage(source)
        elif name == "jev":
            spec, fn = jev_spec(source), jev_stage(source)
        elif name == "score":
            spec, fn = score_spec(source), score_stage(source)
        else:
            spec, fn = export_spec(source), export_stage(source, ws)
        rec = run_stage(ws, spec, fn)
        states.append({"name": name, "status": rec.status, "elapsed_s": rec.data.get("elapsed_s", 0)})
        event(stage=name, stages=states, progress=(i + 1) / (len(steps) + 1))
        if rec.status not in ("complete", "partial"):
            e = rec.data.get("error") or {}
            raise StageError(e.get("code", "analysis_failed"), e.get("message", f"{name} {rec.status}; no package imported"))
    export_outputs(ws, source)
    exp = ws.current("export")
    package = exp.path(exp.data["summary"]["zip"])
    return {"package": str(package), "workspace": str(ws.root), "stages": states}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    ap.add_argument("--result", required=True)
    args = ap.parse_args()
    try:
        result = run(read_json(Path(args.request)))
    except Exception as exc:
        write_json(Path(args.result), {"error": {"code": getattr(exc, "code", "analysis_failed"),
                   "message": str(exc)[:1000]}})
        return 2
    write_json(Path(args.result), result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
