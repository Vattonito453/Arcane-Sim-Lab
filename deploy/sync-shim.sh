#!/usr/bin/env bash
# Build simlab-forge-shim (separate GPL repo) and stage its jar for the
# worker image. Run from anywhere; safe to skip — the image builds without it.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SHIM_DIR="${SIMLAB_SHIM_DIR:-$HOME/Desktop/Personal/simlab-forge-shim}"

if [[ ! -d "$SHIM_DIR" ]]; then
  echo "shim repo not found at $SHIM_DIR (set SIMLAB_SHIM_DIR)" >&2
  exit 1
fi
"$SHIM_DIR/build.sh"
cp "$SHIM_DIR/simlab-forge-shim.jar" "$HERE/vendor/simlab-forge-shim.jar"
echo "staged $HERE/vendor/simlab-forge-shim.jar"
