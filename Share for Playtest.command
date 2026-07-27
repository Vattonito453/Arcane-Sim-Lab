#!/bin/bash
# Puts Sim Lab on a public HTTPS URL so other people can use it.
#
# WHAT THIS EXPOSES: anyone with the link can browse your decks, runs and
# replays — reads need no key. Starting a simulation does need the key, which is
# baked into the page, so effectively anyone with the link can queue sims too.
# They run on THIS Mac. Close this window and the link dies.
#
# The URL is different every run — Cloudflare quick tunnels are ephemeral.
# Double-click this file in Finder.
cd "$(dirname "$0")" || exit 1

WEB_PORT="${SIMLAB_PORT:-3000}"
API_PORT="${MTG_PORT_LOCAL:-8484}"
LOG_DIR="${TMPDIR:-/tmp}/simlab"
mkdir -p "$LOG_DIR"

cleanup() { echo; echo "Shutting down — the public link is now dead."; kill 0; }
trap cleanup EXIT INT TERM

command -v cloudflared >/dev/null || { echo "cloudflared not found: brew install cloudflared"; read -r; exit 1; }
command -v java >/dev/null || echo "NOTE: no java — people can browse and replay, but not run new sims."

# One shared key for the whole playtest group. Regenerated each run, so an old
# link that somehow stayed open can't queue simulations against this one.
SIMLAB_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

echo "Starting engine on 127.0.0.1:$API_PORT (key-protected)…"
MTG_BIND=127.0.0.1 MTG_API_KEYS="$SIMLAB_KEY" \
  python3 engine/mtg_engine.py serve "$API_PORT" > "$LOG_DIR/engine.log" 2>&1 &

printf "Waiting for the engine"
for _ in $(seq 1 60); do
  curl -fs -m 2 "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 && { echo " — ready."; break; }
  printf "."; sleep 1
done
curl -fs -m 2 "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 || {
  echo; echo "Engine failed. See $LOG_DIR/engine.log"; read -r; exit 1; }

# Production build, not dev: this is being served to other people. The key has to
# be present at BUILD time — Next.js inlines NEXT_PUBLIC_* into the bundle.
# NEXT_PUBLIC_API_BASE=/engine routes API calls through this app's own origin, so
# one tunnel covers both halves and there is no CORS or mixed-content problem.
cd web || { echo "web/ not found"; exit 1; }
[ -d node_modules ] || npm install || { echo "npm install failed"; read -r; exit 1; }

echo "Building the front end (this takes a minute)…"
NEXT_PUBLIC_API_BASE=/engine NEXT_PUBLIC_API_KEY="$SIMLAB_KEY" \
  npm run build > "$LOG_DIR/build.log" 2>&1 || {
    echo "Build failed. See $LOG_DIR/build.log"; read -r; exit 1; }

echo "Serving on :$WEB_PORT…"
NEXT_PUBLIC_API_BASE=/engine NEXT_PUBLIC_API_KEY="$SIMLAB_KEY" \
  npm run start -- -p "$WEB_PORT" > "$LOG_DIR/web.log" 2>&1 &

printf "Waiting for the front end"
for _ in $(seq 1 90); do
  curl -fs -m 2 -o /dev/null "http://localhost:$WEB_PORT/" 2>/dev/null && { echo " — ready."; break; }
  printf "."; sleep 1
done

echo "Opening the tunnel…"
cloudflared tunnel --url "http://localhost:$WEB_PORT" > "$LOG_DIR/tunnel.log" 2>&1 &

PUBLIC_URL=""
for _ in $(seq 1 40); do
  PUBLIC_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_DIR/tunnel.log" 2>/dev/null | head -1)
  [ -n "$PUBLIC_URL" ] && break
  sleep 1
done

if [ -z "$PUBLIC_URL" ]; then
  echo "Tunnel did not report a URL. See $LOG_DIR/tunnel.log"; read -r; exit 1
fi

# Prove it end to end before handing the link over.
HOST_ONLY=${PUBLIC_URL#https://}
NOTE=""
HEALTH=$(curl -fs -m 20 "$PUBLIC_URL/engine/health" 2>/dev/null | head -c 40)
if [ -z "$HEALTH" ]; then
  # Don't call the tunnel broken yet. Corporate DNS commonly blackholes
  # *.trycloudflare.com (quick tunnels are an exfiltration route), which makes
  # the link unreachable from THIS machine while working fine for everyone else.
  # Retry against a public resolver's answer to tell the two cases apart.
  IP=$(nslookup "$HOST_ONLY" 1.1.1.1 2>/dev/null | awk '/^Address: /{print $2}' | tail -1)
  if [ -n "$IP" ]; then
    HEALTH=$(curl -fs --resolve "$HOST_ONLY:443:$IP" -m 20 "$PUBLIC_URL/engine/health" 2>/dev/null | head -c 40)
    [ -n "$HEALTH" ] && NOTE="
  NOTE: this Mac's own DNS will not resolve the link (VPN or network filtering).
        The tunnel is fine — other people can open it. To see it yourself, use
        your phone with wifi off, or disconnect the VPN."
  fi
fi

cat <<EOF

──────────────────────────────────────────────────────────────
  Send this link:

     $PUBLIC_URL

──────────────────────────────────────────────────────────────
  serving over the tunnel : $([ -n "$HEALTH" ] && echo "yes" || echo "NO — check $LOG_DIR/tunnel.log")
  sims run on             : this Mac (close this window to stop)
  logs                    : $LOG_DIR$NOTE

  Anyone with the link can browse and can queue simulations.
  Limits already in force: 6 sims/hour each, 3 queued at once, 64 games max.
──────────────────────────────────────────────────────────────

EOF
wait
