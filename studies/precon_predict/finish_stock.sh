#!/usr/bin/env bash
# Wait for the stock cohort run to finish, then tally, analyse and persist the
# fitted model into engine/models/ so the API can use it.
cd "$(dirname "$0")/../.."
while ! grep -q "cohort_results.json" studies/precon_predict/stock_run.log 2>/dev/null; do sleep 120; done
sleep 5
python studies/precon_predict/tally.py runs_stock
echo
python studies/precon_predict/analyze.py --arm runs_stock --min-games 16
if [ -f studies/precon_predict/model_runs_stock.json ]; then
  mkdir -p engine/models
  python - <<'PY'
import json
from pathlib import Path
m = json.loads(Path('studies/precon_predict/model_runs_stock.json').read_text(encoding='utf-8'))
m['human_games'] = 10982
m['ground_truth'] = 'playgroup.gg commander precons, captured 2026-08-03'
Path('engine/models/precon_predict.json').write_text(json.dumps(m, indent=1), encoding='utf-8')
print('\nmodel -> engine/models/precon_predict.json')
PY
fi
