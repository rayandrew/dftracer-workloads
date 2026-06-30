#!/usr/bin/env bash

set -euo pipefail

RAW="${1:?usage: 01-download.sh <raw_dir>}"
JOBS="${DFTW_DL_JOBS:-8}"
BASE="https://huggingface.co/datasets/neheller/KiTS-Challenge-Imaging/resolve/main/images"

command -v curl >/dev/null || {
  echo "curl is required for the parallel download" >&2
  exit 1
}

mkdir -p "$RAW"
cd "$RAW"
if [[ ! -d kits19 ]]; then
  git clone https://github.com/neheller/kits19
fi
cd kits19

# Fetch one case's imaging; skips if already present (resumable), retries on failure.
fetch_case() {
  local c="$1" dest="data/$1/imaging.nii.gz"
  [[ -s "$dest" ]] && return 0
  echo "fetch $c"
  curl -fsSL --retry 5 --retry-delay 10 -o "$dest.part" "$BASE/$c.nii.gz" && mv "$dest.part" "$dest"
}
export -f fetch_case
export BASE

find data -maxdepth 1 -type d -name 'case_*' -printf '%f\n' |
  xargs -P "$JOBS" -I{} bash -c 'fetch_case "$@"' _ {}
touch .imaging-complete # marker: only written after every case is present
