"""OCR stage (subprocess in the ocr env): PP-OCRv5 mobile det + rec on CPU.

Recognizer by declared language: en -> en_PP-OCRv5_mobile_rec;
hi/mixed/unknown -> devanagari_PP-OCRv5_mobile_rec (verified on a crop at
qualification; covers Latin too per PaddleOCR multilingual docs - recorded,
not assumed, by the probe below). Consecutive visually identical frames
reuse the previous result. Checkpointed every 50 frames.
"""

from __future__ import annotations

import time
from pathlib import Path

from pipeline.orchestration.io import append_jsonl, read_json, read_jsonl, write_json, write_jsonl
from pipeline.orchestration.stage import StageError, subprocess_main
from pipeline.text_vision.tracking import build_tracks

BATCH = 50
IDENTICAL_MAE = 0.6  # on 64x36 gray (0-255): treat as the same picture


def _tiny(path: str):
    import numpy as np
    from PIL import Image

    with Image.open(path) as im:
        return np.asarray(im.convert("L").resize((64, 36), Image.BILINEAR), dtype="float32")


def _to_boxes(res) -> list[dict]:
    d = res.json["res"] if hasattr(res, "json") and "res" in res.json else dict(res)
    polys = d.get("rec_polys") or d.get("dt_polys") or []
    texts, scores = d.get("rec_texts") or [], d.get("rec_scores") or []
    out = []
    for poly, t, sc in zip(polys, texts, scores):
        quad = [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in list(poly)[:4]]
        if len(quad) == 4 and str(t).strip():
            out.append({"quad": quad, "text": str(t), "score": round(float(sc), 4)})
    return out


def run(args: dict, out: Path) -> dict:
    import numpy as np
    from paddleocr import PaddleOCR

    cfg = args["config"]
    frames = read_json(args["frames"])
    t0 = time.time()
    try:
        ocr = PaddleOCR(text_detection_model_name=cfg["det_model"], text_recognition_model_name=cfg["rec_model"],
                        use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False,
                        text_det_limit_type=cfg["det_limit_type"], text_det_limit_side_len=cfg["det_limit_side_len"],
                        text_rec_score_thresh=0.0,
                        # Paddle 3.3 oneDNN executor fails on PP-OCRv5 det on Windows (PIR attribute); see D-OCR1.
                        enable_mkldnn=cfg["enable_mkldnn"])
    except Exception as exc:
        raise StageError("ocr_unavailable", f"PaddleOCR could not initialise: {exc}",
                         recommended_action="Run scripts/setup_ocr_models.py with network, then retry.") from exc
    print(f"ocr ready in {time.time() - t0:.1f}s ({cfg['det_model']} + {cfg['rec_model']})", flush=True)

    units = out / "units"
    units.mkdir(exist_ok=True)
    journal = out / "units.jsonl"
    done = {r["batch"]: r for r in read_jsonl(journal, tolerate_torn_tail=True) if (units / r["file"]).exists()}
    prev_tiny, prev_boxes, prev_id = None, None, None
    n_batches = (len(frames) + BATCH - 1) // BATCH
    for b in range(n_batches):
        chunk = frames[b * BATCH:(b + 1) * BATCH]
        fname = f"batch_{b:03d}.jsonl"
        if b in done:
            rows = read_jsonl(units / fname)
            last = rows[-1]
            prev_id = last["reused_from"] or last["frame_id"]
            src = next(f for f in frames if f["frame_id"] == prev_id)
            prev_tiny, prev_boxes = _tiny(src["path"]), last["boxes"]
            continue
        tb = time.time()
        rows, reused = [], 0
        for f in chunk:
            tiny = _tiny(f["path"])
            if prev_tiny is not None and float(np.mean(np.abs(tiny - prev_tiny))) < IDENTICAL_MAE:
                boxes, reused_from = prev_boxes, prev_id
                reused += 1
            else:
                result = ocr.predict(f["path"])
                boxes = _to_boxes(result[0]) if result else []
                reused_from = None
                # compare later frames with the last frame actually read, so slow fades cannot drift
                prev_id, prev_tiny, prev_boxes = f["frame_id"], tiny, boxes
            rows.append({"frame_id": f["frame_id"], "at_ms": f["at_ms"], "boxes": boxes, "reused_from": reused_from})
        write_jsonl(units / fname, rows)
        append_jsonl(journal, {"batch": b, "file": fname, "frames": len(rows)})
        print(f"batch {b + 1}/{n_batches}: {len(rows)} frames ({reused} reused) in {time.time() - tb:.1f}s", flush=True)

    all_rows = []
    for b in range(n_batches):
        all_rows.extend(read_jsonl(units / f"batch_{b:03d}.jsonl"))
    write_jsonl(out / "ocr_frames.jsonl", all_rows)
    tracks = build_tracks(all_rows, int(args["video_end_ms"]))
    write_json(out / "ocr_tracks.json", tracks)
    n_boxes = sum(len(r["boxes"]) for r in all_rows)
    print(f"ocr done: {len(all_rows)} frames, {n_boxes} boxes, {len(tracks)} tracks in {time.time() - t0:.0f}s", flush=True)
    return {"status": "complete", "summary": {"frames": len(all_rows), "boxes": n_boxes, "tracks": len(tracks)}}


if __name__ == "__main__":
    subprocess_main(run)
