# Building the Front End with Google AI Studio

This project is fully self-contained. Everything — backend, rules data, simulator
integration, deploy kit — lives in this repo and is owned by whoever holds it.
AI Studio's job: build the front end, and extend the backend where the app needs it.

## Setup before prompting AI Studio

1. Get the backend running locally first (see the root `README.md` Quick start —
   Forge install + `python3 engine/mtg_engine.py serve 8484`). Confirm the
   dashboard works at http://localhost:8484. The front end develops against this.
2. AI Studio's cloud preview can't reach `localhost` on your machine. Either:
   - export the generated app and run it locally (`npm run dev`) next to the engine, or
   - tunnel the engine: `cloudflared tunnel --url http://127.0.0.1:8484` and use that URL, or
   - deploy the backend (`deploy/docker-compose.yml` on Fly.io/Railway/Render/a VPS) and build against the real URL.

## What to give AI Studio

For UI-only work, upload this `frontend_handoff/` folder — spec, real sample
responses, reference UI, and the rules corpus for the RAG assistant. If AI Studio
will also modify the backend, give it the whole repo; the backend is small, plain
Python stdlib (no frameworks), and mapped in the root `README.md`.

## Suggested first prompt

> Build a React web app called "MTG Sim Lab" per the attached API_SPEC.md.
> A working Python backend already exists in this project — build the front end
> against its documented endpoints, using the sample JSON files as exact response
> shapes. The API base URL must be a user-editable setting (default
> http://127.0.0.1:8484). Core flows: deck picker → run simulation → poll status →
> win-rate results with charts → per-game detail; plus a rules search page and an
> AI rules assistant implemented exactly per the "Rules RAG" section of the spec
> (Gemini answers ONLY from retrieved rule text, with inline rule-number citations,
> never from model memory). reference_dashboard.html is a minimal working version
> of the flows — replace it with something great.

## Extending the backend (no external help needed)

The backend is deliberately simple — plain Python, stdlib only, ~1,000 lines total:

- **New API endpoint** → add a route in the `do_GET`/`do_POST` handlers in
  `engine/mtg_engine.py` (existing routes show the pattern).
- **Deck upload feature** → wire a `POST /decks` route to
  `engine/convert_decklist.py` (`convert()` is importable and returns the `.dck`
  text + a validation report).
- **Serving full game logs** → add `GET /results/{file}` reading from the
  sim results directory (`MTG_DATA_DIR/sim_results`).
- **Anything simulation-related** → `engine/run_sim.py` (Forge invocation) and
  `engine/forge_log_adapter.py` (log → JSON). Forge's own CLI flags are documented
  in `training/forge_integration.md`.
- **Rules data updates** → drop the new Comprehensive Rules .txt in `rules/raw/`
  and run `python3 rules/build_rules_kb.py rules/raw/<file>.txt`.

Before going public: add auth + rate limiting in front of `POST /simulate`
(simulations are compute-expensive), and TLS via your host or a reverse proxy.
