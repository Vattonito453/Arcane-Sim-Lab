#!/usr/bin/env bash
# When the stock arm's analysis has landed, build human-blocking plans for the
# whole cohort and start the agent arm. The dials are the ones the blocking
# work exists to test: block whenever a profitable block exists, at any
# attacker size, as many as are available.
cd "$(dirname "$0")/../.."
while [ ! -s studies/precon_predict/stock_final.log ]; do sleep 120; done
sleep 10
python - <<'PY'
import json, sys
sys.path.insert(0, 'studies/precon_predict')
from make_plans import build
cohort = json.load(open('studies/precon_predict/cohort.json', encoding='utf-8'))
build([c['file'] for c in cohort],
      'studies/precon_predict/plans_agent.json',
      {"blockiness": 1.0, "blockPowerFloor": 0, "blockMax": 99,
       "chumpiness": 0.15, "greed": 1.0, "triggerMiss": 0.0,
       "splitAttacks": 0.0, "politics": 0.0})
print("agent plans built for", len(cohort), "decks")
PY
python -u studies/precon_predict/run_cohort.py --rounds 6 --games 2 --workers 14 \
  --agent-plans studies/precon_predict/plans_agent.json \
  --shim-jar "C:/Users/Vatto/AppData/Local/Temp/claude/C--Users-Vatto-Magic-Rules-Engine/a04e3d06-be86-4427-832d-102b2608b95f/scratchpad/shim-060b.jar" \
  > studies/precon_predict/agent_run.log 2>&1
