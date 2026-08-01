# deploy/vendor

Drop point for the `simlab-forge-shim.jar` binary (built from the separate
GPL-3.0 `simlab-forge-shim` repository — see CLAUDE.md "Legal posture" for
why it is a separate repo). Run `deploy/sync-shim.sh` before building the
worker image if you want shim/humanized simulation available in it.

The jar itself is gitignored: this directory vendors nothing into the repo,
and the worker image builds fine without it (the worker then supports only
`--agent forge`). If the image containing the jar is ever pushed to a public
registry, the shim's source must be published under GPL-3.0 — publishing its
repo satisfies that.
