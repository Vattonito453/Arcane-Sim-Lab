# Forge Integration Map — Headless Simulation Backend

Verified against `Card-Forge/forge` source (cloned 2026-07-22, master). Forge = Java 17+, Maven, GPL-3.0.

## The short version

Forge ships a headless simulation mode that already supports **4-player Commander, AI vs AI, N games, machine-parseable logs** — no GUI, no patching. Command:

```
java -jar forge-gui-desktop-<ver>-jar-with-dependencies.jar sim \
  -d deck1.dck deck2.dck deck3.dck deck4.dck \
  -D /path/to/decks -f commander -n 100 -q
```

Flags (from `SimulateMatch.argumentHelp()`): `-d` decks (names or `.dck` files), `-D` deck directory, `-n` number of games, `-m` match of X games, `-t` tournament (Bracket/RoundRobin/Swiss), `-p` players per match, `-f` format (`commander` → `RegisteredPlayer.forCommander()`), `-c` timeout seconds (default 120, slow games scored as draws), `-q` quiet (result only, no game log).

## Entry points (exact classes)

| What | Class | Notes |
|---|---|---|
| CLI dispatch | `forge.view.Main` (forge-gui-desktop) | `args[0] == "sim"` → `SimulateMatch.simulate(args)`; also a stub `server` mode (not implemented — confirms no official API server) |
| Sim driver | `forge.view.SimulateMatch` | Parses flags, builds decks, runs games with `TimeLimitedCodeBlock` timeout. `simulateOffthreadGame(List<Deck>, GameType, int)` is a ready-made programmatic entry |
| Match/game lifecycle | `forge.game.Match` (forge-game) | `new Match(GameRules, List<RegisteredPlayer>, title)` → `createGame()` → `startGame(game)`. Blocking, single-thread capable |
| Rules config | `forge.game.GameRules` | Game type, sim timeout, variant options |
| Player seat | `forge.game.player.RegisteredPlayer` | `forCommander(Deck)` wires command zone + 40 life; `forVariants(...)` for other multiplayer formats |
| Decision hooks | `forge.game.player.PlayerController` (abstract, ~148 public methods) | Every choice a player makes: mulligans, targets, attackers, blockers, modes, ordering triggers. **Subclass this to inject your own agent** |
| Built-in AI | `forge.ai.PlayerControllerAi` + `AiController`, `AiAttackController`, `AiBlockController`, `ComputerUtil*` (forge-ai) | Drop-in opponent; also readable reference for decision heuristics |
| Card/deck model | forge-core + `forge.deck.Deck`, `DeckSerializer` | `.dck` is a simple text format; card scripts live in `forge-gui/res/cardsfolder` |
| Init required | `forge.model.FModel.initialize(null, null)` | Must run before any simulation (loads card DB) |

## Game log = your validation interface

`Game.getGameLog().getLogEntries(type)` returns typed entries. `GameLogEntryType` enum:
`TURN, PHASE, MULLIGAN, LAND, MANA, STACK_ADD, STACK_RESOLVE, ZONE_CHANGE, COMBAT, DAMAGE, LIFE, DISCARD, EFFECT_REPLACED, PLAYER_CONTROL, INFORMATION, GAME_OUTCOME, MATCH_RESULTS`

This maps almost 1:1 onto the `action` vocabulary in `training/game_00X/game_log.json` (land_drop, cast_spell/STACK_ADD, declare_attackers/COMBAT, combat_damage/DAMAGE, triggered_ability/STACK_ADD, life totals/LIFE). A thin adapter can convert Forge logs into our JSON schema — and vice versa, our extracted real-game logs become replay/assertion fixtures.

## Recommended architecture

```
your RAG (rules/kb)  ←– adjudication & CR citations –→  orchestrator (Python)
                                                            │ subprocess / Py4J
                                                        Forge JVM
                                                    sim mode or embedded Match
                                                            │
                                                 GameLog → JSON adapter → training/
```

1. **Phase 1 — subprocess**: run `sim` CLI, parse stdout game logs into `game_log.json` schema. Zero Java code. Good for bulk data generation (100s of AI games as training corpus).
2. **Phase 2 — embedded**: small Java shim calling `FModel.initialize` → `Match`/`RegisteredPlayer.forCommander` → custom `GameLogEntry` export (JSON). Exposes full state, not just logs.
3. **Phase 3 — custom agent**: subclass `PlayerController`, delegate decisions to an external process (your model), while Forge enforces rules. This is the "train on real data, act in simulator" loop.

## Caveats

- **GPL-3.0**: fine for internal tooling; derivative distributed code must be GPL.
- Rules coverage is huge but unofficial — keep the RAG as authority on disputes; log divergences as test cases.
- `sim` mode lives in **forge-gui-desktop** (not forge-game), so build that module: `mvn -U -B clean package -pl forge-gui-desktop -am -DskipTests`.
- First run needs the card resource folder (`forge-gui/res`) present; decks referenced by name resolve from the Commander deck store (`FModel.getDecks().getCommander()`).

## Suggested first milestone

Recreate game_002 (LRR) decks approximately as `.dck` files, run `sim -f commander -n 50 -q` for the 4 seats, adapt logs to our JSON schema, and diff Forge's rulings against the validated events in `game_002/game_log.json` (e.g., does Forge enforce 903.10a at 21? does an empty-library draw end the game per 104.3c?). That gives an automated conformance harness between the simulator and the rules KB.
