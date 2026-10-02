"""Generate small synthetic media fixtures with known ground truth.

Timeline of `basic.mp4` (25 s, 1280x720, 25 fps, 48 kHz stereo):
  0-5   testsrc2 motion        + 440 Hz tone
  5-7   black                  + digital silence
  7-14  static card with text  + 660 Hz tone     (text "RETENTION TEST 42")
  14-20 static SMPTE bars      + digital silence (freeze + pause)
  20-25 testsrc2 motion        + clipped 880 Hz tone
Hard cuts at 5, 7, 14, 20 s. Variants: rotated (display matrix 90),
noaudio, vfr. Output: fixtures/generated/ (git-ignored).
Usage: python scripts/make_fixtures.py  (run with the media venv)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.media.ffmpeg import run_ffmpeg  # noqa: E402

OUT = ROOT / "fixtures" / "generated"
FONT = Path("C:/Windows/Fonts/arial.ttf")
W, H, R = 1280, 720, 25


def _font_arg() -> str:
    if FONT.exists():
        return "fontfile='" + str(FONT).replace("\\", "/").replace(":", "\\:") + "':"
    return ""


def basic(path: Path) -> None:
    text = (f"color=c=0x102040:s={W}x{H}:r={R}:d=7,"
            f"drawtext={_font_arg()}text='RETENTION TEST 42':fontsize=96:fontcolor=white:x=(w-tw)/2:y=(h-th)/2")
    fc = ";".join([
        f"testsrc2=s={W}x{H}:r={R}:d=5,format=yuv420p[v0]",
        f"color=c=black:s={W}x{H}:r={R}:d=2,format=yuv420p[v1]",
        f"{text},format=yuv420p[v2]",
        f"smptebars=s={W}x{H}:r={R}:d=6,format=yuv420p[v3]",
        f"testsrc2=s={W}x{H}:r={R}:d=5,hue=h=90,format=yuv420p[v4]",
        "sine=f=440:r=48000:d=5,volume=0.25,aformat=channel_layouts=stereo[a0]",
        "anullsrc=r=48000:cl=stereo:d=2[a1]",
        "sine=f=660:r=48000:d=7,volume=0.25,aformat=channel_layouts=stereo[a2]",
        "anullsrc=r=48000:cl=stereo:d=6[a3]",
        "sine=f=880:r=48000:d=5,volume=20,aformat=sample_fmts=s16:channel_layouts=stereo[a4]",
        "[v0][a0][v1][a1][v2][a2][v3][a3][v4][a4]concat=n=5:v=1:a=1[v][a]",
    ])
    run_ffmpeg(["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "18", "-g", "25", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(path)])


def rotated(src: Path, path: Path) -> None:
    run_ffmpeg(["-display_rotation", "90", "-i", str(src), "-c", "copy", str(path)])


def noaudio(src: Path, path: Path) -> None:
    run_ffmpeg(["-i", str(src), "-an", "-c:v", "copy", str(path)])


def vfr(src: Path, path: Path) -> None:
    # Alternate 30 ms / 50 ms frame spacing -> genuinely variable frame rate.
    run_ffmpeg(["-i", str(src), "-vf", "setpts='(N*0.04+if(mod(N,2),-0.01,0))/TB'", "-fps_mode", "passthrough",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", str(path)])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    b = OUT / "basic.mp4"
    basic(b)
    rotated(b, OUT / "rotated.mp4")
    noaudio(b, OUT / "noaudio.mp4")
    vfr(b, OUT / "vfr.mp4")
    # 75 s variant (>= 60 s) so retention scenarios are exercised in tests
    run_ffmpeg(["-stream_loop", "2", "-i", str(b), "-c", "copy", str(OUT / "long.mp4")])
    for p in sorted(OUT.glob("*.mp4")):
        print(p.name, p.stat().st_size)


if __name__ == "__main__":
    main()
