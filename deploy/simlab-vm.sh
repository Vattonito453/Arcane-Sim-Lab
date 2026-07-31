#!/bin/bash
# Operate the Sim Lab VM without remembering gcloud flags.
#
#   ./deploy/simlab-vm.sh up        start the VM (billing resumes)
#   ./deploy/simlab-vm.sh down      stop it (billing drops to disk only)
#   ./deploy/simlab-vm.sh status    running? which IP? containers healthy?
#   ./deploy/simlab-vm.sh url       print the address to send people
#   ./deploy/simlab-vm.sh key       print the shared API key (reads it on the VM)
#   ./deploy/simlab-vm.sh logs      follow worker logs (watch sims execute)
#   ./deploy/simlab-vm.sh redeploy  re-upload this repo and rebuild in place
#
# Billing note: Compute Engine charges per hour the instance is RUNNING, whether
# or not anyone is simulating. `down` is the only thing that stops that meter.
set -euo pipefail

VM="${SIMLAB_VM:-simlab}"
ZONE="${SIMLAB_ZONE:-us-central1-a}"
PROJECT="${SIMLAB_PROJECT:-arcane-sim-lab-v2}"
G=(gcloud compute --project="$PROJECT")
REMOTE_DIR='~/"MtG Rules Engine/deploy"'

ssh_do() { "${G[@]}" ssh "$VM" --zone="$ZONE" --quiet --command="$1"; }

ip_of() {
  "${G[@]}" instances describe "$VM" --zone="$ZONE" \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null
}

case "${1:-status}" in
  up)
    "${G[@]}" instances start "$VM" --zone="$ZONE"
    echo "Waiting for the web container…"
    for _ in $(seq 1 40); do
      if ssh_do "curl -fs -m 5 -o /dev/null http://localhost/" 2>/dev/null; then
        echo "Ready: http://$(ip_of)"
        exit 0
      fi
      sleep 10
    done
    echo "VM is up but the web container has not answered yet; try: $0 status" >&2
    ;;
  down)
    "${G[@]}" instances stop "$VM" --zone="$ZONE"
    echo "Stopped. Billing is now disk-only (~\$4/mo)."
    ;;
  status)
    "${G[@]}" instances list --filter="name=$VM" \
      --format="table(name,status,machineType.basename(),networkInterfaces[0].accessConfigs[0].natIP)"
    ssh_do "cd $REMOTE_DIR && sudo docker compose --env-file .env ps --format 'table {{.Name}}\t{{.Status}}'" 2>/dev/null \
      || echo "(containers unreachable — VM may be stopped)"
    ;;
  url)  echo "http://$(ip_of)" ;;
  key)  ssh_do "grep '^MTG_API_KEYS=' $REMOTE_DIR/.env | cut -d= -f2" ;;
  logs) ssh_do "cd $REMOTE_DIR && sudo docker compose --env-file .env logs -f --tail=40 worker" ;;
  redeploy)
    cd "$(dirname "$0")/../.."
    # COPYFILE_DISABLE stops macOS tar emitting AppleDouble "._name"
    # sidecars for files with extended attributes. Those extract as real
    # files on Linux, match engine/decks/*.dck, and are binary — which is
    # exactly how the first deploy served a 500 for its whole deck list.
    COPYFILE_DISABLE=1 tar czf /tmp/simlab.tgz \
      --exclude='MtG Rules Engine/web/node_modules' \
      --exclude='MtG Rules Engine/web/.next' \
      --exclude='MtG Rules Engine/web/.next-verify' \
      --exclude='MtG Rules Engine/engine/sim_results' \
      --exclude='MtG Rules Engine/.git' \
      --exclude='MtG Rules Engine/MtG Rules Engine' \
      --exclude='MtG Rules Engine/deploy/.env' \
      --exclude='*.zip' --exclude='.DS_Store' \
      "MtG Rules Engine"
    "${G[@]}" scp /tmp/simlab.tgz "$VM:~/simlab.tgz" --zone="$ZONE" --quiet
    # .env is excluded from the archive, so the VM's secret survives extraction.
    ssh_do "tar xzf ~/simlab.tgz && cd $REMOTE_DIR && sudo docker compose --env-file .env up -d --build"
    echo "Redeployed: http://$(ip_of)"
    ;;
  *)
    sed -n '2,20p' "$0"; exit 1 ;;
esac
