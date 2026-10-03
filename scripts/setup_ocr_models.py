"""Download PP-OCRv5 models, qualify them on a rendered probe, hash them.

  .venvs/ocr/Scripts/python.exe scripts/setup_ocr_models.py

RISKS "Open items": verify one Hindi crop before bulk processing. The probe
renders known English and Devanagari strings and records what each
recognizer reads back. The manifest (file sha256s) pins the model bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.orchestration.settings import models_dir  # noqa: E402
from pipeline.text_vision.stages import OCR_MODELS, paddle_env  # noqa: E402

PROBES = {"en": "RETENTION TEST 42", "hi": "नमस्ते दुनिया"}
FONTS = {"en": "C:/Windows/Fonts/arial.ttf", "hi": "C:/Windows/Fonts/Nirmala.ttc"}
if sys.platform == "darwin":
    FONTS = {"en": "/System/Library/Fonts/Supplemental/Arial.ttf",
             "hi": "/System/Library/Fonts/Kohinoor.ttc"}


def render(text: str, font: str, path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 200), (16, 32, 64))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(font, 72)
    d.text((40, 50), text, font=f, fill=(255, 255, 255))
    img.save(path)


def sha_dir(d: Path) -> list[dict]:
    rows = []
    for p in sorted(d.rglob("*")):
        if p.is_file():
            rows.append({"path": p.relative_to(d).as_posix(), "bytes": p.stat().st_size,
                         "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    return rows


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    os.environ.update(paddle_env())
    from paddleocr import PaddleOCR

    probe_dir = models_dir() / "paddle_probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for lang, rec in OCR_MODELS["rec"].items():
        ocr = PaddleOCR(text_detection_model_name=OCR_MODELS["det"], text_recognition_model_name=rec,
                        use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False,
                        enable_mkldnn=False)
        reads = {}
        for plang, text in PROBES.items():
            img = probe_dir / f"probe_{plang}.png"
            render(text, FONTS[plang], img)
            r = ocr.predict(str(img))[0]
            d = r.json["res"]
            reads[plang] = {"expected": text, "read": d.get("rec_texts", []), "scores": d.get("rec_scores", [])}
        report[rec] = reads
        print(rec, json.dumps(reads, ensure_ascii=False))

    official = Path(os.environ["PADDLE_PDX_CACHE_HOME"]) / "official_models"
    manifest = {"models": {}, "probe": report}
    for name in [OCR_MODELS["det"], *OCR_MODELS["rec"].values()]:
        d = official / name
        if not d.exists():
            print(f"missing model dir {d}")
            return 1
        rows = sha_dir(d)
        manifest["models"][name] = {"dir": str(d), "files": rows,
                                    "digest": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}
    out = models_dir() / "manifests" / "paddleocr.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"manifest: {out}")
    return 0


if __name__ == "__main__":
    _utf8_console()
    sys.exit(main())
