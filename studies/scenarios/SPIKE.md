# G-harness spike: does a 4-player GameState work in the shim's headless Match?

Repair plan WS3 task 1, gate **G-harness** (`tasks/25-repair-plan.md` §4.4:
pass = "4-player GameState works"; fallbacks: 2-player states, then
GameAction zone moves, which would move G1 to Tue 10/27). Run 2026-09-28 on
the dev box, Forge 2.0.13, shim 0.17.1 (`simlab-forge-shim` branch
`shim-0.17.1-scenario`, commits `4a50c6f` and `967cb71`).

## Verdict

**Four-player route. G-harness passes; no fallback was needed.** A
four-seat Commander state applies inside the shim's headless Match, for
stock seats and for plan seats, and every field the format carries reads
back as written (below). A two-seat cut of the same state also loads (2 of
2 trials), so the first fallback works too, but nothing needs it.

**Plan consequence:** none. G1 stays **Fri 10/23**; the E1 prototype can
seed its scenarios with `--scenario` from day one. The GameAction route
(and its +1 day) is not taken.

## What was tried

### 1. The API (javap and the forge-2.0.13 source)

`javap -p -cp forge-gui-desktop-2.0.13-jar-with-dependencies.jar
forge.game.GameState` lists the public `parse(List<String>)`,
`parse(InputStream)`, `applyToGame(Game)` and a **protected**
`applyGameOnThread(Game)`. The source at tag `forge-2.0.13`
(`forge-game/src/main/java/forge/game/GameState.java`, `Match.java`,
`GameAction.java`, `phase/PhaseHandler.java`,
`forge-core/.../util/ThreadUtil.java`) settled six things:

1. **Seat keys.** `getPlayerState` maps `human` to 0, `ai` to 1 and `p`
   plus ONE digit to that index, and `applyGameOnThread` throws unless the
   state has exactly as many player states as the game has players. Player
   `i` is `game.getPlayers().get(i)`, which is registration order, which is
   the shim's `--decks` order. So `p0`..`p3` address four seats.
2. **Every zone is cleared first.** `setupPlayerState` empties battlefield,
   hand, graveyard, library, exile, command and sideboard, then fills only
   the zones the state names. An unnamed library is an empty library, so
   the writer writes every zone of every seat.
3. **Commanders.** `|IsCommander` calls `player.addCommander(card)`, in any
   zone, and `createCommanderEffect()` rebuilds the command-zone effect the
   clear removed. The plan's syntax was right.
4. **Threading.** `applyToGame` is `game.getAction().invoke(...)`, and
   `invoke` runs inline only when `ThreadUtil.isGameThread()`, i.e. the
   thread's name starts with `Game`; otherwise it posts the work to Forge's
   own thread pool and returns at once. The shim's game thread is
   `shim-game-N`, so `applyToGame` would race the game it seeds. The shim
   calls `applyGameOnThread` directly (a two-line subclass for the protected
   access) from a hook that is already on the game thread. The same
   routing inside `GameState` applies only to mana-pool lines, which the
   writer never emits.
5. **When: Forge's own start-game hook, not a controller callback.**
   `Match.startGame(game, startGameHook)` is public; puzzle mode passes its
   state through it (`HostedMatch`). Forge runs the hook inside
   `PhaseHandler.setupFirstTurn`, on the game thread: after opening hands
   and `MulliganService`, after turn 1's untap step began, before any
   player receives priority. That is exactly the point the plan asked for,
   and unlike "the first controller callback" it exists for an all-stock
   arm too (stock seats have no Sim Lab controller to call back into). This
   is the one departure from the plan's mechanism text, and it is a
   simplification.
6. **Limits.** Combat is seeded only against `getSingleOpponent()` (1v1),
   so scenarios start outside combat. A blank line throws in the line
   splitter (`charAt(0)`), so the shim drops blank lines. The format has no
   commander tax, commander damage, storm count or stack (see README).

### 2. The board: `spike/spike_4p.json`

Pod `2iA_Jt0d6sM` (derevi, godo_archetype, nadu, rograkh_silas), turn 5,
Godo's precombat main phase. Every field: tapped (Command Tower, Sol Ring,
a Mountain, Steam Vents), summoning sickness (Derevi; Nadu, which also
wears Lightning Greaves), counters (Birds of Paradise `P1P1=1`, Urza's Saga
`LORE=2`), marked damage (Birds, 1), a token (Treasure), equipment attached
(Helm of the Host on Godo, Lightning Greaves on Nadu), commanders on the
battlefield (Derevi, Godo, Nadu) and unplaced in the command zone (Rograkh
and Silas, added by the writer), explicit library tops (derevi: Ancient
Tomb, Mana Crypt; godo: Sol Ring), graveyard, exile, life 40/35/30/40,
poison 3 on nadu.

### 3. Commands

```bash
# the state text for trial 0 (library shuffle seed = the trial's seed)
py studies/scenarios/writer.py studies/scenarios/spike/spike_4p.json --seed 2026101401

# two arms x 2 trials through the runner (final jar); the plan arm uses the
# G0a version-2 plans for this pod
py studies/scenarios/run_scenarios.py studies/scenarios/spike/spike_4p.json \
    --jar <scratch>/harness/shim-0.17.1-967cb71.jar --out <scratch>/harness/spike_run \
    --arms stock,plan --trials 2 --parallel 4 --seed 2026101401 \
    --plans <scratch>/g0a/plans_2iA_Jt0d6sM_v2.json
```

which runs, per trial, with the Forge directory as the working directory:

```bash
java -Xmx3g -cp "<scratch>/harness/shim-0.17.1-967cb71.jar;forge-gui-desktop-2.0.13-jar-with-dependencies.jar" \
  simlab.shim.SimShim --decks <repo>/studies/human_ceiling/decks/2iA_Jt0d6sM/dck/{derevi,godo_archetype,nadu,rograkh_silas}.dck \
  --games 1 --timeout 900 --max-turns 9 \
  --plans <scratch>/g0a/plans_2iA_Jt0d6sM_v2.json \
  --seat-pilots plan:SimLabHuman,plan:SimLabHuman,plan:SimLabHuman,plan:SimLabHuman \
  --seed-forge 2026101401 --scenario <out>/spike_4p/trial_0.state --out <out>/spike_4p/plan/trial_0.jsonl
```

(the stock arm: no `--plans`, `--seat-pilots stock:Default` x 4). The first
runs, before the runner existed, used the same shim command on a
pre-commit build: the same board loaded, and all three games (1 stock, 2
plan) ended in godo_archetype wins between turns 5 and 9.

## Log excerpts: the applied board for every seat

The shim's `scenario` record, stock arm trial 0 (`shimCommit
967cb71a3eef`), condensed to one line per zone; ids are Forge's card ids,
`sick` is the flag the state set:

```
{"rec":"scenario","game":0,"file":"trial_0.state","sha256":"e4951822...9f66","applied":true,
 "before":"1 UNTAP","turn":5,"phase":"MAIN1","active":"Ai(2)-godo_archetype",
 "priority":"Ai(2)-godo_archetype","atMs":721,"applyMs":1073,"lifeRestored":[],"seats":[...]}

Ai(1)-derevi life 40 poison 0 commanderIds [500]
  Battlefield Derevi, Empyrial Tactician {"id":500,"sick":true,"commander":true}; Command Tower {"id":501,"tapped":true};
              Breeding Pool {"id":502}; Sol Ring {"id":503,"tapped":true}; Birds of Paradise {"id":504,"damage":1,"counters":{"P1P1":1}}
  Hand        Force of Will; Rhystic Study
  Graveyard   Arid Mesa
  Command     Commander Effect
  Library     92 cards, top 3: Ancient Tomb; Mana Crypt; Volatile Stormdrake
Ai(2)-godo_archetype life 35 poison 0 commanderIds [599]
  Battlefield Treasure Token {"id":606,"token":true}; Godo, Bandit Warlord {"id":599,"commander":true};
              Helm of the Host {"id":600,"attachedTo":599}; Mountain {"id":601,"tapped":true}; Mountain x3; Urza's Saga {"id":605,"counters":{"LORE":2}}
  Hand        Lightning Bolt
  Command     Commander Effect
  Library     92 cards, top 3: Sol Ring; Great Furnace; Urza's Cave
Ai(3)-nadu life 30 poison 3 commanderIds [703]
  Battlefield Nadu, Winged Wisdom {"id":703,"sick":true,"commander":true}; Lightning Greaves {"id":704,"attachedTo":703}; Forest; Island
  Hand        Mystical Tutor
  Exile       Force of Negation
  Command     Commander Effect
  Library     94 cards, top 3: Fierce Guardianship; Flusterstorm; Mindbreak Trap
Ai(4)-rograkh_silas life 40 poison 0 commanderIds [807, 808]
  Battlefield Badlands; Steam Vents {"tapped":true}; Mox Opal
  Hand        Dark Ritual
  Graveyard   Lion's Eye Diamond
  Command     Rograkh, Son of Rohgahh; Silas Renn, Seeker Adept; Commander Effect
  Library     93 cards, top 3: Snap; Arid Mesa; Deflecting Swat
```

The runner's board check compares this record with what the writer asked
for, card by card; all 4 trials (2 per arm) had no difference. Forge's own
log, same game, from the discarded opening into the seeded turn:

```
4  MULLIGAN  Ai(3)-nadu has kept a hand of 7 cards
5  TURN      Turn 1 (Ai(4)-rograkh_silas)
6  PHASE     Ai(4)-rograkh_silas' Untap step
7  PHASE     devAi(2)-godo_archetype's Main phase, precombat          <- the state lands here
8  EFFECT_REPLACED  As Breeding Pool enters, you may pay 2 life. If you don't, it enters tapped.
9  LIFE      Life: Ai(2)-godo_archetype 40 > 35
10 EFFECT_REPLACED  Urza's Saga enters with a lore counter on it.
11 LIFE      Life: Ai(3)-nadu 40 > 30
13 PHASE     Ai(2)-godo_archetype's Beginning of Combat Step
14 STACK_ADD Ai(2)-godo_archetype triggered Helm of the Host
16 STACK_ADD Ai(2)-godo_archetype triggered Godo, Bandit Warlord       <- the Helm token's enter trigger
20 PHASE     Ai(2)-godo_archetype's Declare Attackers Step
21 COMBAT    Ai(2)-godo_archetype assigned Godo, Bandit Warlord (811) and Godo, Bandit Warlord (599) to attack Ai(1)-derevi.
```

Each seat's next draw is its seeded library's first card (`zone` records):
turn 6 nadu draws Fierce Guardianship, turn 7 rograkh_silas Snap, turn 8
derevi Ancient Tomb (its explicit top). Godo's own library was shuffled by
the Helm token's search on turn 5, as the card says.

Results (2 trials per arm): stock, godo_archetype won on turn 9 twice
(15.4 s and 16.6 s of game time); plan, godo_archetype won on turn 5 twice
(22.9 s and 23.0 s), with plan-seat telemetry flowing (`search_seen`,
`split`, `added_block`, `instant_hold`, `kingmaker_reaim`, ...). The apply
itself took 0.9 to 1.1 s, 0.7 to 1.5 s into the game.

## Findings that shaped the adapter and the format

- **Enters-the-battlefield replacement effects run during the apply.**
  Forge moves each battlefield card in, so the shock land's "pay 2 life"
  question is asked. On the smoke scenario nadu paid for its Breeding Pool
  in 8 of 8 trials, stock and plan alike, and started at 38 of the file's
  40; the runner's board check caught it (loaded 0/4 per arm). `GameState`
  already re-sets life after the apply, but only for life of 0 or less; the
  shim now does it for every seat and records the change (`lifeRestored`,
  commit `967cb71`). The re-runs loaded 4 of 4 per arm, each with the
  same `lifeRestored` entry (nadu 38 to 40). Other replacement
  effects stand: "as this enters, choose" asks the seat's AI, and the
  state's `tapped` flag overrides "enters tapped".
- **Triggers are suppressed during the apply** (as in puzzle mode): a
  seeded Godo did not search for equipment.
- **Summoning sickness:** Forge clears the flag on every card the state
  creates unless `|SummonSick` is given, and `Card.hasSickness()` already
  folds haste in (Nadu with Greaves reads false), so the record carries
  the flag (`sick`) and Forge's reading (`sickNow`).
- **Turn numbers:** the state sets turn 5 without a turn-began event, so
  the shim moves its tap's turn to 5 after the apply (the turn cap counts
  from there); Forge's first `TURN` entry still says turn 1 and its next
  says turn 6. Tokens are placed first in the battlefield zone.

## No behaviour change without `--scenario`

Same decks, pilots and plans as G0a arm T (pod `2iA_Jt0d6sM`, version-2
plans, all plan seats), and an all-stock arm; `--games 2 --max-turns 12
--seed-forge 2026101500`; no `--scenario`. First 0.17.0 (the G0a jar,
sha256 `c2273bef...`) was run four times with the same seed, then 0.17.1
three times (twice at `4a50c6f`, once at the final `967cb71`; the second
commit touches only the scenario path).

**Seeded games are not fully deterministic, even on one jar.** Whole-run
JSONL differs between two identical 0.17.0 runs. Two sources: the turn cap
is polled every 2 s, so the kill lands at a wall-clock-dependent point
after turn 12 (both arms); and games with plan seats diverge inside the
turn window, first in which land pays for a spell (`Island - {T}: Add {U}`
against `Boseiju, Who Endures - {T}: Add {G}`, game 0 entry 190). So the
comparison is over turns 1 to 12 only, and by variant: runs sharing a
letter wrote byte-identical `entry`, `zone`, `tap` and `agent` records.

| Arm, game | 0.17.0 runs a, b, c, d | 0.17.1 runs a, b (`4a50c6f`), c (`967cb71`) |
|---|---|---|
| stock, game 0 | A A A A | A A A |
| stock, game 1 | A A A A | A A A |
| plan, game 0 | A B B A | A B A |
| plan, game 1 | A B C A | A C C |

Every stock game is identical across all seven runs. Every plan-seat
variant 0.17.1 played, 0.17.0 also played from the same seed (variant B of
plan game 1 appeared once, in a 0.17.0 run). Agent-event records are
identical within each variant. Headers match except `shim`, `shimCommit`
and the two new null fields. On this evidence 0.17.1 without `--scenario`
plays as 0.17.0 does; byte identity of whole runs is not claimed, because
0.17.0 does not have it with itself. (The formal seeding study, E2, is
separate.)

**Re-measured in review (2026-09-28), on a second seed.** The same
comparison, `--seed-forge 2026102800`, eight runs per jar (0.17.0
`b8894e1`, 0.17.1 `967cb71`) at 6 JVMs, turns 1 to 12. Variants of
byte-identical records, and in brackets the variants left once the order
in which the same mana sources were tapped is forgiven (the E2 review
found same-seed pairs that differ only in that order):

| Arm, game | 0.17.0, 8 runs | 0.17.1, 8 runs |
|---|---|---|
| stock, game 0 | A B B A B C D D [A B B A B A B B] | D E A E C B A B [B B A B A B A B] |
| stock, game 1 | A A A A A B B B [same] | B B A B B A A A [same] |
| plan, game 0 | A A B A B A B B [all A] | A B B A A A A A [all A] |
| plan, game 1 | A B A B C A A A [same] | A A C B A B A B [same] |

**Stock games are not deterministic either.** On this seed they split
into five variants (game 0) and two (game 1); "every stock game
identical" above held for seed 2026101500, not in general. The first
splits seen, all on both jars: the order Forge taps mana sources for one
payment (turn 9 of game 0: Exotic Orchard or Savannah first, Savannah for
W or G); a real decision, nadu's turn-7 attack in game 1 (attack or not,
for a stock seat and a plan seat alike, since Forge's own attack code
decides it for both); and plan game 1's third variant, where derevi's
plan seat spends its turn-9 mana differently (in variant A it casts
Derevi from the command zone). With tap order forgiven, every variant
of every game was played by both jars. Headers differ only in `shim`,
`shimCommit` and the two null fields. So the conclusion stands on what
the measurement can show: no split that a single jar does not also show
against itself, and a code path without `--scenario` that is the 0.17.0
call (`match.startGame(game)`) line for line. Scratch:
`harness_review/det/`, `det_compare.py`, `det_norm.py`.

## Cost

Per trial, one JVM and one game: Forge initialisation about 15 s, the apply
about 1 s, then play. Smoke scenario (Godo and Helm, 4 JVMs at once,
`smoke/report.md`): 28 to 83 s of wall time per trial (mean 51 s), 118 s
for 8 trials. At 8 JVMs the
10-scenario suite at 20 trials for one arm is roughly 200 trials x 50 s / 8,
about 21 minutes, inside the 50-minute acceptance line; that is an
estimate from the smoke run, not a measurement of the suite. (Measured
afterwards, `BASELINE.md`: 21.2 min stock, 24.0 min plan, at 8 JVMs.)
