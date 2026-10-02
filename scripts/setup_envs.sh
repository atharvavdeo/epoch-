#!/usr/bin/env bash
# Creates the isolated local environments from the hashed locks (TRD §2, D06).
# Usage: scripts/setup_envs.sh [media|api|ocr|asr ...]   (default: all four)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UV="${UV:-uv}"
# Windows Defender can lock hardlinked Scripts*.exe launchers ("Access is denied").
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
PY311="${PY311:-$(py -3.11 -c 'import sys;print(sys.executable)' 2>/dev/null || command -v python3.11)}"
ENVS=("$@"); [ ${#ENVS[@]} -eq 0 ] && ENVS=(media api ocr asr)
for env in "${ENVS[@]}"; do
  dir="$ROOT/.venvs/$env"
  echo "[setup] $env -> $dir"
  [ -d "$dir" ] || "$UV" venv --python "$PY311" "$dir"
  if [ -x "$dir/Scripts/python.exe" ]; then py="$dir/Scripts/python.exe"; else py="$dir/bin/python"; fi
  # One bounded retry: Windows Defender transiently locks freshly written
  # launchers ("Access is denied"); a second sync resumes from uv's cache.
  "$UV" pip sync --python "$py" --require-hashes "$ROOT/locks/$env.txt"     || { echo "[setup] $env: retrying sync once"; sleep 5; "$UV" pip sync --python "$py" --require-hashes "$ROOT/locks/$env.txt"; }
  "$UV" pip install --python "$py" --no-deps -e "$ROOT"
  echo "[setup] $env ok: $("$py" -c 'import sys;print(sys.version.split()[0])')"
done
