# Human ceiling study — plan

**Status: scaffolded 2026-08-24; pilot video processed, stock-Forge pilot run
in progress. Nothing is pre-registered yet — this document currently records
design intent and data provenance, not a locked analysis.**

**Question.** Where, concretely, does stock Forge's play fall short of strong
human play on the *same decks* — and which of those shortfalls should the shim
close first?

This is a third kind of question. `studies/precon_correlation/` asked whether
our win rates track human win rates (null). `studies/skill_headtohead/` asked
whether the agent beats stock Forge (null). Both compared *outcomes*. This
study compares *behavior*: turn-by-turn human lines from competitive cEDH
videos against stock Forge traces on the same decklists. The output is not a
win rate; it is a ranked list of behavioral gaps (win-turn distribution, combo
assembly speed, tutor targets, interaction timing, mulligan choices) that
becomes shim tuning targets and training data.

Why cEDH specifically: `engine/SIM_CALIBRATION.md` already documents that
engine/combo decks sim below their real strength. cEDH is the extreme of that
regime, so it maximizes the visible gap; and competitive players trying hard
to win are the cleanest available sample of "human trying to win", which is
what the user-facing agent is supposed to approximate regardless of bracket.

---

## 1. Data sources and their honesty labels

### Video game traces (`data/transcripts/`, `traces/`)

YouTube auto-captions of table talk, cleaned by `tools/clean_vtt.py`. What
they can and cannot support, measured on the pilot (n7WpsqsZtdQ):

- **Recoverable, high confidence:** who won, approximate win turn, the win
  method, commander deploy turns, marquee plays and tutors (players announce
  them), spoken interaction (counters, removal, sacrifices), creator
  self-review when present.
- **Recoverable, medium confidence:** per-turn play-by-play. Card names garble
  ("vaccine bubble" = Vexing Bauble, "Legion Extruder" = Twinshot Sniper) and
  are repaired against the published decklist; every repair is flagged in the
  trace file.
- **Not recoverable from audio alone:** life totals, full hands, anything
  shown on screen but not spoken, unspoken fetch targets. Traces are therefore
  *sparse event streams*, never full game states, and must never be presented
  as replays.
- **Frame sampling closes part of that gap** (proven on the pilot 2026-08-24):
  `yt-dlp --download-sections` + ffmpeg stills at transcript-flagged
  timestamps recover the stream's player/deck overlays (exact seat
  attribution), the editor's full-card popups (kills caption garble at the
  moments that matter), and life-tracker readings. Sample 20-40 frames per
  game at turn boundaries and ambiguous plays; do not attempt continuous
  video, and treat un-popped table-cam board detail as zoom-on-demand only.

### Decklists (`decks/`)

Four fidelity tiers, recorded per seat in `manifest.json`:

1. **published** — creator links the exact list.
2. **approximate** — creator links a list but flags it inexact, or the list
   was edited after the video (Moxfield shows lastUpdated; the pilot's Magda
   list drifted and the on-camera Arena of Glory is missing from it).
3. **archetype-substitute** — no list published; a maintained, high-visibility
   list for the same commander(s) substituted. Fine for engine-behavior
   comparison, unusable for exact-line comparison.
4. **missing** — not yet resolved. topdeck.gg event pages are the best untapped
   source for the tournament videos.

Forge card support is checked at conversion (`tools/make_dck.py`) against the
local card DB; unsupported cards are substituted only via an explicit,
recorded `--map` (the pilot needed 4 substitutions in Magda, all from a set
newer than Forge 2.0.13).

### Stock Forge traces (`runs/`)

`run_sim.py --agent shim` (no `--humanize`): stock Forge AI decisions with the
shim's typed zone stream, so board truth is a read, not an inference. Seat
rotation always on. These are the standard result JSON files; per-game clock
900 s.

## 2. Comparison metrics (draft, to be locked before any scaled run)

Per deck, human trace vs stock-Forge distribution:

- **Win turn** when winning, and game length generally. Pilot expectation:
  humans win T4-6 in cEDH; stock Forge with the same decks wins later or
  times out.
- **Commander deploy turn** (Magda T1 on camera; what does Forge do?).
- **Tutor/fetch targets** — the pilot video literally contains the creator
  explaining the correct Magda fetch (God-Pharaoh's Gift proactively, Portal
  reactively). Forge's toolbox choices are directly comparable.
- **Interaction rate and timing** — spoken counterspells/removal per game vs
  Forge's counts from the event log.
- **Mulligan behavior** where spoken ("should not have kept this seven").

The unit of comparison is the deck, not the game: video games are single
samples of human play, so human-side numbers are anecdotes with provenance,
not distributions. They set *targets* ("a strong human wins with this deck by
T5 through this line"), and the sim side measures how far stock Forge is from
the target. No statistical claims until there are enough independent human
games per archetype.

## 3. Pipeline

1. `manifest.json` — verified video inventory with decklist fidelity.
2. `yt-dlp` fetch (scratchpad venv; not vendored) -> `data/meta/`,
   `tools/clean_vtt.py` -> `data/transcripts/`.
3. Decklist resolution (Moxfield via browser fetch; API blocks scripted
   clients) -> `decks/<video>/*.txt` -> `tools/make_dck.py` -> `.dck`.
4. LLM extraction of transcripts -> `traces/<video>.json` (schema per the
   pilot file: per-game key_line with repairs and confidence flags).
5. `run_sim.py --agent shim --rotate` on the same pod -> `runs/`.
6. Comparison report per video (not yet built; blocked on locking §2).

## 4. Known limitations, stated up front

- **One human game is one sample.** A video shows a line, not a distribution.
  Do not compute "human win rate" from these.
- **Auto-captions miss silent plays.** Interaction counts from audio are a
  floor, not a measurement.
- **Selection bias.** Creators publish exciting games; turbo wins are
  overrepresented relative to grindy ones.
- **List drift and archetype substitutes** break exact-line comparison for
  most videos; the manifest records fidelity per seat and any conclusion must
  quote it.
- **Two of the twelve videos are not usable as traces** (one meta-analysis
  video, one unverified 2022 video) and two more are pre-2024 games under an
  older banlist/meta. The manifest flags all four.
- **Copyright posture:** transcripts are creator content fetched for private
  analysis. Like `rules/raw/`, strip `data/transcripts/` and `data/meta/`
  before this repo ever goes public; traces (our own structured extraction)
  can stay.

## 5. Pilot (complete 2026-08-24)

Video n7WpsqsZtdQ (ThatMillGuy, 2 games): Magda / Rog-Ishai / Tymna-Thrasios /
Selvala(substitute). Human result: Magda wins both games, round 5 and ~6, via
treasure engine into Portal to Phyrexia / Liquimetal Torque activations —
including a turn-1 Magda off Sol Ring + Mox Opal. Traces:
`traces/n7WpsqsZtdQ.json`.

Stock-Forge run: 4 games, seat-rotated, 900 s clock, `--agent shim` (stock AI,
zone ground truth). Result `runs/sim_20260824_140312_*.json`; board check
passes at exit_match_rate 1.0 / assumed 0.0 (zone_stream basis). No timeouts,
games ran 75-150 s wall each.

**Unit warning that already bit once:** Forge counts *player* turns (4 per
table round); humans say "turn 5" meaning round 5. All comparisons below are
in table rounds. An early read of this pilot quoted "turn 37 vs turn 5" as an
8x gap; the honest figure is 2x.

| | human (2 games) | stock Forge (4 games) |
|---|---|---|
| Winner | Magda both | Magda 3, Selvala 1, Rog-Ishai 0, TymnaThras 0 |
| Winning round | 5, ~6 | 10, 11, 12, 12 |
| Win method | Magda toolbox (Portal to Phyrexia, Liquimetal Torque) | combat damage every game; Portal never fetched |
| Magda deploy | round 1 (Sol Ring + Mox Opal) | not yet extracted per-game |

Two pilot observations worth carrying into §2 when it locks:

1. **Deck ranking may survive even when line quality does not.** Stock Forge
   found the same winning deck as the humans (Magda 75%) despite never
   playing the deck's actual win line. If that holds across videos, win-rate
   ranking is a weak discriminator and the tuning signal must come from the
   line-level features (win round, fetch targets, method), not outcomes.
2. **The gap is concentrated in the toolbox choice.** Forge attacks with
   Dwarves; the human converts the same treasures into Portal/God-Pharaoh's
   Gift activations. "What does Magda fetch" is a single, measurable,
   shim-tunable decision — exactly the kind of target this study exists to
   produce (compare `stage5-combo-pursuit` line-of-sight work).
