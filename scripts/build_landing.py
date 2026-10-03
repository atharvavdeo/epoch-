"""Build the backend-free showcase and browser-compatible supplied demo media.

Run with .venvs/media/bin/python scripts/build_landing.py. Downloaded videos stay
outside Git; dist is the only folder uploaded to Pages. No secrets/API data copied.
"""
from pathlib import Path
import argparse
import shutil
import subprocess
import json
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--media-root', type=Path, default=ROOT.parent / 'epoch-data' / 'inputs')
    args = parser.parse_args()
    source = ROOT / 'apps' / 'landing'
    output = source / 'dist'
    media = output / 'media'
    media.mkdir(parents=True, exist_ok=True)
    for name in ('index.html', 'styles.css', 'main.js', 'tour.js', 'tour.css', '_headers'):
        shutil.copy2(source / name, output / name)
    vendor = output / 'vendor'
    vendor.mkdir(exist_ok=True)
    driver_dist = ROOT / 'apps' / 'web' / 'node_modules' / 'driver.js' / 'dist'
    for name in ('driver.js.iife.js', 'driver.css'):
        shutil.copy2(driver_dist / name, vendor / name)
    shutil.copy2(driver_dist.parent / 'LICENSE', vendor / 'driver-LICENSE.txt')
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    mapping = [('y7xV8g73n9U.mp4', 'jio-short.mp4'), ('qGbvEhKhaWA.mp4', 'prahaar-trailer.mp4'),
               ('ve7AA01vplE.mp4', 'education.mp4')]
    for src_name, dest_name in mapping:
        src, dest = args.media_root / src_name, media / dest_name
        if not src.is_file():
            raise FileNotFoundError(f'Missing supplied demo source: {src}')
        if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
            continue
        print(f'Prepared {dest_name}', flush=True)
        cmd = [ffmpeg, '-v', 'error', '-y', '-i', str(src), '-map', '0:v:0', '-map', '0:a:0?',
               '-vf', 'scale=w=min(720\\,iw):h=-2', '-c:v', 'libx264', '-threads', '2',
               '-preset', 'fast', '-crf', '27', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '96k',
               '-movflags', '+faststart', str(dest)]
        subprocess.run(['nice', '-n', '10', *cmd], check=True)
    audio = media / 'voice-excerpt.wav'
    if not audio.exists():
        subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', str(args.media_root / 've7AA01vplE.mp4'),
                        '-t', '40', '-vn', '-ac', '1', '-ar', '16000', str(audio)], check=True)
    files = [p for p in output.rglob('*') if p.is_file()]
    oversize = [str(p) for p in files if p.stat().st_size > 25 * 1024**2]
    if oversize:
        raise ValueError(f'Pages file-size bound exceeded: {oversize}')
    print(json.dumps({'output': str(output), 'files': len(files),
                      'bytes': sum(p.stat().st_size for p in files)}))


if __name__ == '__main__':
    main()
