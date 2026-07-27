#!/usr/bin/env bash
# Install Forge (headless-capable) for the MTG Rules Engine simulation backend.
# Tested target: Forge 2.0.13. Works on macOS and Linux. Requires Java 17+.
set -euo pipefail

FORGE_VERSION="${FORGE_VERSION:-2.0.13}"
INSTALL_DIR="${FORGE_DIR:-$HOME/forge}"
URL="https://github.com/Card-Forge/forge/releases/download/forge-${FORGE_VERSION}/forge-installer-${FORGE_VERSION}.tar.bz2"

echo "== Checking Java =="
if ! command -v java >/dev/null || ! java -version 2>&1 | grep -qE 'version "(1[7-9]|2[0-9])'; then
  echo "Java 17+ required."
  echo "  macOS:  brew install openjdk@17"
  echo "  Ubuntu: sudo apt install openjdk-17-jre-headless"
  exit 1
fi

echo "== Downloading Forge ${FORGE_VERSION} (~290 MB) =="
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
curl -L --progress-bar -o forge.tar.bz2 "$URL"

echo "== Extracting =="
tar xjf forge.tar.bz2 && rm forge.tar.bz2

JAR=$(ls "$INSTALL_DIR"/forge-gui-desktop-*-jar-with-dependencies.jar 2>/dev/null | head -1 || true)
if [ -z "$JAR" ]; then
  # some releases nest the payload one level down
  JAR=$(find "$INSTALL_DIR" -name "forge-gui-desktop-*jar-with-dependencies.jar" | head -1)
fi
[ -z "$JAR" ] && { echo "Could not locate the Forge jar after extraction — check $INSTALL_DIR"; exit 1; }

echo "== Smoke test: headless sim help =="
cd "$(dirname "$JAR")"
java -Xmx1g -jar "$JAR" sim 2>&1 | head -5 || true

cat <<EOF

Done.
  Jar: $JAR
Add to your shell profile:
  export FORGE_JAR="$JAR"

Try a real 4-player Commander sim (decks in engine/decks/):
  python3 run_sim.py --decks krenko_goblins.dck drana_vampires.dck \\
      selvala_ramp.dck talrand_control.dck \\
      --deck-dir /path/to/MtG\ Rules\ Engine/engine/decks --games 5
EOF
