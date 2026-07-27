# MTG Rules Engine — Complete Project

A Magic: The Gathering **Commander deck-testing engine**: an official-rules knowledge
base (RAG), a real game simulator (Forge), a job-queued HTTP API with a browser
dashboard, and a validated training dataset from real gameplay. This repo is the
entire system — backend, data, deploy kit, and front-end spec. It has no external
dependencies beyond Python 3.10+, Java 17+, and (optionally) Docker.

## Project map

| Folder | What it is |
|---|---|
| `rules/` | The rules brain. Official Comprehensive Rules (June 2026) parsed into a structured KB: `kb/all_rules.json` (3,152 rules), `kb/mechanics.json` (262 keywords), `kb/glossary.json` (735 terms), `kb/turn_structure.json` (ordered phases/steps), `kb/chunks.jsonl` (3,887 RAG-ready chunks). `build_rules_kb.py` regenerates everything from a new CR text file when Wizards updates the rules. |
| `engine/` | The working backend. `mtg_engine.py` = HTTP API + browser dashboard + rules lookups. `run_sim.py` + `forge_log_adapter.py` = run headless Forge simulations, convert logs to structured JSON. `jobqueue.py` + `worker.py` = SQLite job queue so sims run in the background. `convert_decklist.py` = Moxfield/Arena export → Forge `.dck`. `decks/` = ready-to-sim Commander decks incl. a bracket-3 gauntlet (Atraxa / Meren / Ur-Dragon). `setup_forge.sh` = one-command Forge install. |
| `deploy/` | Docker kit for hosting: API container, Forge worker container, compose file. See `deploy/README.md`. |
| `training/` | Real-game dataset: three 4-player Commander games extracted turn-by-turn from YouTube (timestamped transcripts + structured `game_log.json` files + rules-validation reports). Use for testing the engine's rulings, grounding AI features in real play, or ML training. |
| `frontend_handoff/` | Front-end build spec: `API_SPEC.md` (endpoint contract + product brief + RAG pattern), `samples/` (real captured API responses), `reference_dashboard.html` (working minimal UI), `rules_kb/` (corpus copy for client-side RAG). |
| `MTG Engine.command` | macOS double-click launcher: starts the engine and opens the dashboard. |

## Quick start on a new machine (macOS/Linux)

```bash
# 1. Requirements: Python 3.10+, Java 17+
#    macOS: brew install openjdk@17    Ubuntu: sudo apt install openjdk-17-jre-headless

# 2. Install Forge (the game simulator, ~290MB, one time)
bash engine/setup_forge.sh

# 3. Start the engine  (macOS: just double-click "MTG Engine.command")
python3 engine/mtg_engine.py serve 8484
# → http://localhost:8484  — pick decks, run sims, search rules. No terminal needed after this.
```

Docker alternative (no local Java/Forge needed): `docker compose -f deploy/docker-compose.yml up --build`

## How the pieces connect

```
browser / front end
      │ HTTP+JSON (CORS open)
engine/mtg_engine.py ──► rules/kb/*.json      (instant rules lookups & search)
      │ POST /simulate → jobqueue.py (SQLite)
engine/worker.py ──► Forge (Java, headless) ──► forge_log_adapter.py ──► sim_results/*.json
```

- Full endpoint contract with sample responses: `frontend_handoff/API_SPEC.md`
- Simulation output schema: `frontend_handoff/samples/sim_result_game_excerpt.json`
- Add a deck: drop a `.dck` in `engine/decks/`, or convert any Moxfield/Arena export:
  `python3 engine/convert_decklist.py mylist.txt --name "My Deck"`

## Verified state at handoff

- End-to-end tested on macOS (Apple Silicon): 25+ real 4-player Commander games simmed
  across three pods, zero card-database misses (sets through Edge of Eternities work).
- Adapter unit tests: `python3 engine/tests/test_adapter.py`
- Rules KB validated against ~4 hours of real gameplay footage — every table ruling
  checked; reports in `training/*/validation_report.md`.
- Known rough edges: `search` is keyword-scoring (an embeddings upgrade over
  `chunks.jsonl` is the designed next step — see `rules/README.md`); jobs orphaned by
  a mid-run crash stay "running" (add timeout-requeue at scale); Forge's AI is a
  competent but not expert pilot — treat win rates as directional (50+ games) and
  combo/politics decks under-test.

## Licensing note

Forge (the simulator) is GPL-3 and runs as an unmodified separate process — keep it
that way (subprocess/container boundary, no code linking) so your app's license
stays independent. The Comprehensive Rules text is © Wizards of the Coast; this
project uses it for rules lookup, which is standard for community tools — don't
resell the rules text itself.
