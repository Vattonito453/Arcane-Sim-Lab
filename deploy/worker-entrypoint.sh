#!/bin/sh
# Start a virtual X display, then hand off to the worker.
#
# Why a display at all: Forge ships ONE desktop jar for both its GUI and its
# `sim` mode, and forge.GuiDesktop's static initializer calls
# initializeScreenScale() -> getDefaultScreenDevice() before sim mode is
# reached. Headless it throws java.awt.HeadlessException; with
# -Djava.awt.headless=false it fails on a missing libXext.so.6. Either way the
# failure is SILENT — Forge registers a Sentry handler that swallows the
# exception and exits 1 with no output, which reads exactly like a container
# doing nothing.
#
# Why not xvfb-run: it starts Xvfb in a subshell and waits for the server to
# signal readiness with SIGUSR1. That handshake does not complete when the
# script runs as PID 1 in a container — measured here: Xvfb came up, the wait
# never returned, and the command it was supposed to run never started at all.
# Starting the server directly and polling for its socket is deterministic.
set -e

DISPLAY_NUM="${XVFB_DISPLAY:-99}"
Xvfb ":$DISPLAY_NUM" -screen 0 1280x1024x24 -nolisten tcp &
XVFB_PID=$!

# Wait for the socket rather than sleeping a fixed amount.
i=0
while [ ! -e "/tmp/.X11-unix/X$DISPLAY_NUM" ]; do
    i=$((i + 1))
    if [ "$i" -gt 100 ]; then
        echo "entrypoint: Xvfb failed to create /tmp/.X11-unix/X$DISPLAY_NUM" >&2
        exit 1
    fi
    if ! kill -0 "$XVFB_PID" 2>/dev/null; then
        echo "entrypoint: Xvfb exited before becoming ready" >&2
        exit 1
    fi
    sleep 0.1
done

export DISPLAY=":$DISPLAY_NUM"
# Say which shim this image carries. A stale cached build layer once pinned the
# VM to a Stage-3 shim while main was on Stage 5, and nothing in the logs said
# so — the agent's own behavior was the only clue. Now it is one line.
if [ -f /opt/simlab-forge-shim/COMMIT ]; then
    echo "entrypoint: shim commit $(cat /opt/simlab-forge-shim/COMMIT)"
else
    echo "entrypoint: WARNING no shim provenance file — image predates the fix" >&2
fi
echo "entrypoint: Xvfb ready on $DISPLAY, starting $*"
# exec so the worker becomes the main process and receives signals directly.
exec "$@"
