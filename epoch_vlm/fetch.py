"""Pinned, verified Hugging Face snapshot download (COLAB_RUNBOOK §3, §6).

Shipped inside the Colab runtime; the local pipeline imports it from here.

Works with huggingface_hub 0.36 (local asr env) and 1.5 (Colab vlm env).
- exact revision, explicit allow-list (no wildcard)
- every LFS file sha256-verified against Hub metadata; small files hashed
- manifest digest recorded; existing verified files are never re-downloaded
- transient network failure: 2 retries after the first attempt (2 s, 8 s)
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

RETRY_DELAYS = (2, 8)

# Files never needed for inference in these environments.
_EXCLUDE_SUFFIXES = (".h5", ".msgpack", ".onnx", ".ot", ".tflite", ".mlmodel", ".pb", ".gguf", ".md", ".png", ".jpg",
                     ".gif", ".gitattributes")
_EXCLUDE_DIRS = ("onnx/", "openvino/", "tf/", "flax/", "coreml/")


def select_files(all_files: list[str], weights_preference: list[str] | None) -> list[str]:
    """Deterministic allow-list: every config/tokenizer/processor file plus one weight format.

    Weight choice: the first preference present (safetensors over bin); sharded
    safetensors are taken from their index. Nothing is selected by wildcard.
    """
    files = [f for f in all_files if not f.startswith(_EXCLUDE_DIRS) and not f.endswith(_EXCLUDE_SUFFIXES)
             and not f.startswith(".") and "/." not in f]
    weight_like = (".safetensors", ".bin", ".pt", ".pth")
    non_weights = [f for f in files if not f.endswith(weight_like) and not f.endswith(".safetensors.index.json")]
    chosen_weights: list[str] = []
    if any(f.endswith(".safetensors.index.json") for f in files):
        idx = [f for f in files if f.endswith(".safetensors.index.json")][0]
        chosen_weights = [idx] + sorted(f for f in files if f.endswith(".safetensors") and "/" not in f)
    else:
        for pref in weights_preference or []:
            if pref in files:
                chosen_weights = [pref]
                break
    if not chosen_weights:
        raise ValueError(f"no preferred weight file among {weights_preference}")
    return sorted(set(non_weights + chosen_weights))


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def _lfs_sha(sib) -> str | None:
    lfs = getattr(sib, "lfs", None)
    if lfs is None:
        return None
    if isinstance(lfs, dict):
        return lfs.get("sha256")
    return getattr(lfs, "sha256", None)


def fetch_snapshot(repo: str, revision: str, cache_dir: Path, weights_preference: list[str] | None = None,
                   token: str | None = None, log=print) -> dict:
    from huggingface_hub import HfApi, snapshot_download

    cache_dir = Path(cache_dir)
    manifest_path = cache_dir / "manifests" / f"{repo.replace('/', '__')}@{revision}.json"
    if manifest_path.exists():
        man = json.loads(manifest_path.read_text(encoding="utf-8"))
        snap = Path(man["snapshot_dir"])
        if snap.exists() and all((snap / f["path"]).exists() and (snap / f["path"]).stat().st_size == f["bytes"]
                                 for f in man["files"]):
            log(f"[models] {repo}@{revision[:10]} verified manifest present ({man['manifest_digest'][:12]})")
            return man

    api = HfApi(token=token)
    last_exc = None
    for attempt, delay in enumerate((0,) + RETRY_DELAYS):
        if delay:
            log(f"[models] retry {attempt}/{len(RETRY_DELAYS)} in {delay}s after: {last_exc}")
            time.sleep(delay)
        try:
            info = api.model_info(repo, revision=revision, files_metadata=True)
            siblings = {s.rfilename: s for s in info.siblings}
            files = select_files(sorted(siblings), weights_preference)
            log(f"[models] {repo}@{revision[:10]}: {len(files)} files")
            snap = Path(snapshot_download(repo_id=repo, revision=revision, allow_patterns=files,
                                          cache_dir=str(cache_dir / "hf"), token=token))
            break
        except Exception as exc:  # network/transient; auth errors also land here but repeat harmlessly twice
            last_exc = exc
            if "401" in str(exc) or "403" in str(exc) or "RevisionNotFound" in type(exc).__name__:
                raise
    else:
        raise RuntimeError(f"download failed after retries: {last_exc}")

    rows = []
    for f in files:
        p = snap / f
        if not p.exists():
            raise RuntimeError(f"snapshot missing {f}")
        actual = _sha256(p)
        expected = _lfs_sha(siblings[f])
        if expected and expected != actual:
            raise RuntimeError(f"sha256 mismatch for {repo}/{f}: expected {expected[:12]} got {actual[:12]}")
        rows.append({"path": f, "bytes": p.stat().st_size, "sha256": actual, "lfs_verified": bool(expected)})
    idx = [f for f in files if f.endswith(".safetensors.index.json")]
    if idx:
        shard_names = set(json.loads((snap / idx[0]).read_text(encoding="utf-8"))["weight_map"].values())
        missing = shard_names - set(files)
        if missing:
            raise RuntimeError(f"index references shards not downloaded: {sorted(missing)[:3]}")
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    man = {"repo": repo, "revision": revision, "snapshot_dir": str(snap), "files": rows, "manifest_digest": digest}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(man, indent=1), encoding="utf-8")
    log(f"[models] {repo}@{revision[:10]} verified, digest {digest[:12]}")
    return man
