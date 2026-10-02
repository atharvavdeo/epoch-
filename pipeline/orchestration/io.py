"""Atomic file helpers shared by every environment (stdlib only)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path: Path, obj: Any) -> None:
    _atomic_write_bytes(Path(path), (json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + "\n").encode("utf-8"))


def write_jsonl(path: Path, rows: Iterable[Any]) -> int:
    lines = [json.dumps(r, ensure_ascii=False, allow_nan=False, separators=(",", ":")) for r in rows]
    _atomic_write_bytes(Path(path), ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8"))
    return len(lines)


def append_jsonl(path: Path, row: Any) -> None:
    """Append one line and fsync (journals). Partial last lines are ignored on read."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: Path, *, tolerate_torn_tail: bool = False) -> list[Any]:
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if tolerate_torn_tail and i == len(lines) - 1:
                break  # crash mid-append: drop the torn final line only
            raise
    return rows


def write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(Path(path), text.encode("utf-8"))
