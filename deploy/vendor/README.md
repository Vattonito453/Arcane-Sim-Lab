# deploy/vendor

Local-dev override for the `simlab-forge-shim.jar` binary (built from the
separate GPL-3.0 `simlab-forge-shim` repository — see CLAUDE.md "Legal
posture" for why it is a separate repo).

Humanized simulation is the product default, so the worker image ALWAYS
carries the shim. The Dockerfile's shim-builder stage takes the jar from
here when `deploy/sync-shim.sh` has staged it (fast local path, no network);
otherwise it clones `SIMLAB_SHIM_REPO` and builds from source — that is the
VM/redeploy path and requires the shim repo to be reachable (public).

The jar itself is gitignored: this repo vendors no GPL code or binaries.
Since the shim repo is public, distributing an image containing the jar
already satisfies GPL source availability.
