#!/usr/bin/env bash
# One-command deploy, run on the VM from a git clone of this repo:
#
#   ~/simlab/deploy/redeploy.sh          # pull main, rebuild the whole stack
#   ~/simlab/deploy/redeploy.sh web      # pull main, rebuild only the front end
#
# Deploys exactly what is committed on origin/main — never local edits
# (--ff-only refuses to proceed if the clone has diverged). deploy/.env lives
# only on the VM, is untracked, and survives pulls.
set -euo pipefail
cd "$(dirname "$0")"
git -C .. pull --ff-only
docker compose --env-file .env up -d --build "$@"
