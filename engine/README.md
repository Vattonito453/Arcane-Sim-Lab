# MTG Engine — Backend Brains

The "brains" layer for any front end: rules knowledge (RAG over the Comprehensive Rules) + real game simulation (Forge headless). Zero Python dependencies — stdlib only.

```
front end (your next project)
      │  HTTP (JSON)
mtg_engine.py  ──────────────►  rules/kb/*        (3,152 rules, 262 keywords, 735 glossary terms)
      │ subprocess                │
run_sim.py ──► Forge JVM ──► forge_log_adapter.py ──► game_log JSON (same schema as training/)
```

## Components

| File | Role | Status |
|---|---|---|
| `mtg_engine.py` | Unified API: Python import, CLI, and HTTP server | **Verified working** (tested live: /health, /rule, /search, /keyword, /turn-structure) |
| `forge_log_adapter.py` | Forge sim stdout → game_log JSON schema + win-rate summary | **Verified** (unit tests pass: `tests/test_adapter.py`) |
| `run_sim.py` | Runs headless Forge sims, saves raw log + adapted JSON | Code complete — needs Forge installed (see below) |
| `setup_forge.sh` | Installs Forge 2.0.13 (~290MB) on your machine | Run locally |
| `decks/*.dck` | Four ready 100-card Commander decks (Krenko, Drana, Selvala, Talrand) | Counts verified (100 each); card names use evergreen staples |
| `tests/test_adapter.py` | Adapter unit tests using Forge's exact log format | Passing |

**Setup:** `bash setup_forge.sh` once, then the command below. If any deck card name isn't in Forge's database, the raw log in `sim_results/` names the offender — fix that line in the `.dck` and rerun. (Verified working end-to-end on macOS Apple Silicon, 25+ real games.)

## Quick start (your machine)

```bash
cd "MtG Rules Engine/engine"
bash setup_forge.sh                       # one-time; sets FORGE_JAR hint at the end

python3 run_sim.py \
  --decks krenko_goblins.dck drana_vampires.dck selvala_ramp.dck talrand_control.dck \
  --deck-dir ./decks --games 10
# → sim_results/sim_<stamp>.json  (turn-by-turn events + win rates per deck)
```

## API for the front end

```bash
python3 mtg_engine.py serve 8484
```

| Endpoint | Returns |
|---|---|
| `GET /rule/903.10a` | Exact rule text (+subrules for parent numbers) |
| `GET /search?q=trample&k=8` | Scored rule/glossary chunks |
| `GET /keyword/station` | Full keyword entry (all subrules) |
| `GET /glossary/monarch` | Glossary definition + rule refs |
| `GET /turn-structure` | Ordered phases/steps with attached rules — drive your UI's turn tracker straight off this |
| `GET /health` | KB stats |
| `POST /simulate` `{"decks":[...],"deck_dir":"...","games":10}` | Runs Forge, returns adapted JSON with win rates |

CORS is open (`*`) for dev. CLI mirrors every endpoint (`python3 mtg_engine.py rule 903.10a`, `search`, `keyword`, `glossary`, `turn-structure`, `validate-log`, `stats`, `serve`).

`validate-log` cross-checks every `rule_refs` entry in a game log against the KB — currently green on game_001 and game_002.

## Known limits / next steps

- `search` is keyword-overlap scoring; fine for terms, weaker for concept queries ("commander damage" ranks 120.4d above 903.10a). The embedding upgrade over `chunks.jsonl` (see rules/README) is the fix.
- Deck lists are untested against Forge's exact card DB until first local run (expect at most a couple of name swaps).
- Adapter regexes for damage/life lines may need one round of tightening against real Forge output — every event keeps `raw`, so nothing is lost meanwhile.
- Phase 3 (custom `PlayerController` agent) is scoped in `../training/forge_integration.md`.

## Deck-sim workflow for the mtg-deck-master skill

See `SKILL_ADDITION.md` for the ready-to-merge skill section. Flow: skill builds/edits a deck → exports `.dck` → `POST /simulate` (or `run_sim.py`) against gauntlet decks in `decks/` → win rates + event logs feed back into the skill's evaluation.
