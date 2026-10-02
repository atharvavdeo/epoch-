"""Thin, logged wrapper around the pinned ffmpeg binary (imageio-ffmpeg)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class MediaError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = details or {}


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


@lru_cache(maxsize=1)
def ffmpeg_version() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_version()


@dataclass
class FFResult:
    returncode: int
    stderr: str


def run_ffmpeg(args: list[str], *, timeout_s: float = 3600, check: bool = True) -> FFResult:
    """Run ffmpeg with -nostdin/-hide_banner; return stderr text (filters log there)."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s)
    err = proc.stderr.decode("utf-8", errors="replace")
    if check and proc.returncode != 0:
        tail = "\n".join(err.strip().splitlines()[-12:])
        raise MediaError("ffmpeg_failed", f"ffmpeg exited {proc.returncode}: {tail}", details={"args": args[:40]})
    return FFResult(proc.returncode, err)


def stream_ffmpeg_stdout(args: list[str], chunk_bytes: int):
    """Yield raw stdout chunks of an ffmpeg pipe (e.g. f32le audio)."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", *args]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    try:
        while True:
            buf = proc.stdout.read(chunk_bytes)
            if not buf:
                break
            yield buf
    finally:
        proc.stdout.close()
        err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        rc = proc.wait()
        if rc != 0:
            raise MediaError("ffmpeg_stream_failed", f"ffmpeg pipe exited {rc}: {err[-800:]}")


def as_posix(p: Path | str) -> str:
    return str(Path(p))
