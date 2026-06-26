#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PYTHON="${PYTHON:-python3}"
VENV="$ROOT/.venv"

DEV=0
for arg in "$@"; do
  case "$arg" in
    --dev) DEV=1 ;;
    *)
      echo "unknown arg: $arg" >&2
      exit 1
      ;;
  esac
done

echo ">> syncing benchpark submodule"
git -C "$ROOT" submodule update --init --recursive

if [[ ! -d "$VENV" ]]; then
  echo ">> creating venv at $VENV"
  "$PYTHON" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

STAMP="$VENV/.dftw-deps-stamp"
WANT="$(cat "$ROOT/vendor/benchpark/requirements.txt" "$ROOT/orchestration/pyproject.toml" | sha256sum | cut -d' ' -f1)"
if [[ "${FORCE:-0}" != "1" && -f "$STAMP" && "$(cat "$STAMP")" == "$WANT" ]]; then
  echo ">> deps unchanged, skipping pip (FORCE=1 to override)"
else
  echo ">> installing benchpark requirements + dftw"
  pip install --quiet --upgrade pip
  pip install --quiet -r "$ROOT/vendor/benchpark/requirements.txt"
  pip install --quiet -e "$ROOT/orchestration"
  echo "$WANT" >"$STAMP"
fi

echo ">> bootstrapping benchpark (ramble + spack, one-time)"
"$ROOT/vendor/benchpark/bin/benchpark" --config "$ROOT/benchpark-config" bootstrap

if [[ "$DEV" == "1" ]]; then
  echo ">> installing pre-commit hooks"
  pip install --quiet pre-commit
  pre-commit install
  pre-commit install-hooks
fi

cat <<EOF

done. no activation needed. put the launcher on PATH:

  export PATH="$ROOT/bin:\$PATH"

then use it from anywhere:

  dftw --help
  dftw patch edit unet3d
EOF
