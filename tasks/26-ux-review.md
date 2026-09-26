# Sim Lab: UX review and redesign direction

*This synthesis draws on four hands-on walkthroughs of production (http://35.192.104.34/), three research tracks (Magic tools, replay viewers, human-centred and anti-slop design), and two critiques: one from a veteran Commander player and one from a senior product designer. The evidence runs are `sim_20260925_003803` (the playtester's run), `sim_20260925_194533`, `sim_20260907_232221` and `sim_20260902_145933`.*

*For this revision I re-read all eight games of `sim_20260925_003803` from the live read API and checked the load-bearing claims against source:*
- *the phase regex (`web/lib/replay.ts:245`) and the per-phase zone folding (`replay.ts:577-587, 653-667`)*
- *how knockouts are dated (`engine/scorecard.py:62-71`)*
- *the pilot's finisher regex and combo weights (`engine/deck_plan.py:124, 323`)*
- *`_slim()` (`engine/combos.py:90-101`) and the stale inference note (`engine/analysis.py:389`)*
- *the estimate table (`web/lib/format.ts:118`)*
- *the glass page shell (`web/app/globals.css:325-335`)*
- *the existing type and spacing tokens (`Design System/arcane-sim-lab.tokens.css:114-125`)*
- *the 343 Spellbook feature names across 5,582 cached variants in `engine/combo_cache.json`*

---

## 1. Verdict

To an expert Commander player, Sim Lab today feels like a very honest engine dressed in a template, and it tells the story of its games slightly wrong.

**The story is the first problem.** Take game 1 of the playtester's run, which the app calls a poison win for Skrat's Revenge:
- It turned on turn 8. Ezuri's Predation made a Beast for every opposing creature and had them fight. That killed all three opposing commanders and 12 of their 15 creatures, and Skrat's went from 3 creatures (6 power) to 15 (54 power).
- On turn 9, Triumph of the Hordes put 46 poison on Krenko and 19 on Stella. Forge gave neither of them another turn.
- On turn 10, Kess died to 45 combat damage from 14 unblocked attackers, at 35 life.

The app gets this game wrong in five ways:
- It calls the whole game "poison", because `analysis.py` keeps one method per game.
- It dates every knockout to the last turn. Forge prints all the loss lines at game end, and `scorecard.py` trusts them.
- It mislabels the phase at every step of Skrat's turns (a possessive-name parse bug).
- It leaves the two players who are out sitting at the table.
- It sends "Jump to the deciding turn" to turn 10's untap step.

**The combo table is the second problem.** It calls Hullbreaker Horror + Sol Ring a win condition, counts Stella Lee alone as a combo "assembled 8 of 8", and lists 28 variants of one Squirrel Girl line. It never mentions Skrat's actual finishers:
- Craterhoof Behemoth, never cast in 8 games.
- Triumph of the Hordes, cast in 1.
- Ezuri's Predation, cast in 3.

The pilot's plan uses the same Spellbook list and weights every combo piece at 8. That is why, on turn 6 of game 1, Kess used Unmarked Grave to put Sol Ring into its graveyard instead of Blasphemous Act.

**The look is the third problem, and it is the "jank" the owner feels.**
- Every page is one translucent glass sheet over storm art.
- Every primary button is a glowing all-caps button.
- The home page is the most recognisable AI landing layout there is (centred mascot, count-up tally, "What would you like to do today?", four glowing buttons), and it never says what the product does.
- Machine strings leak everywhere: "Kess, vs Stella vs Skrat's vs Krenko", NaN:NaN, T36, env var names.

**Underneath, the honesty machinery beats every competitor's:**
- seats are rotated
- clock-cut draws are kept out of win rates
- predictions are calibrated and state their error
- board provenance is labelled by path
- ledes are computed from data
- hands are exact on shim runs
- every payload carries the AI pilot's stated reasons

Nearly every fix is presentation over data that already exists, plus a few small engine fields.

**Design thesis:** Sim Lab should read like a sharp Commander player's write-up of your pod night. It should be about your deck, in table language, with every claim carrying its sample size and sitting one click from the game that proves it.

**Order of work:**
1. Fix what's untrue.
2. Change how it feels.
3. Test with the playtester.
4. Only then build the big pieces.

§9 has the cut line.

---

## 2. The top 15 problems, ranked

Ranked first by how much each one costs an expert's trust or makes the app feel careless, then by size.

| # | Problem | Size | Phase |
|---|---|---|---|
| 1 | The replay and report get the story of a game wrong | S–M | 1 |
| 2 | "Win conditions" is a modelling problem, not a table problem | L (stopgap S) | 1 stopgap, 2 |
| 3 | The look is the AI template: glass over art, glowing caps, a home page that doesn't say what the product is | S (CSS), M (home) | 1 |
| 4 | The cost and status of a sim are misstated | S | 1 |
| 5 | Names read as machine-made | S | 1 |
| 6 | Unfinished and operator states reach players | S | 1 |
| 7 | The report is about the pod, and its headline number can't carry 8 games | L | 2 |
| 8 | The replay isn't watchable: pacing, navigation, finding the moment | M | 1 partial, 2 |
| 9 | The replay stage: illegible cards, controls off-screen, no zones or stack | M | 1 partial, 2 |
| 10 | Win rates: three numbers for one fact, false precision, stale baselines | M | 1 partial, 2–3 |
| 11 | Telemetry is broken for imported decks and scores other decks' plans | M | 2 |
| 12 | The pilot's reasoning isn't shown, and isn't ready to show raw | M | 2 |
| 13 | The deck page is a 10-screen oracle dump | M | 2 |
| 14 | Type sizes, contrast and colour meanings are in a fog | M | 1 adoption, 2 palette |
| 15 | The playtest sandbox is below the Moxfield/Archidekt baseline | L | 3 |

### 1. The replay and report get the story of a game wrong (S–M)

**Where:**
- `web/lib/replay.ts:245` is `raw.match(/^(.+?)'s (.+)$/)`, a lazy match. Related: `:261` `isCombatPhase`, and `:569-583` `labelOrd`, which falls back to end-of-turn.
- `engine/analysis.py` gives each game one `method`. Game 1 gets "poison".
- `engine/scorecard.py:62-71` `_death_rounds()` dates each knockout by Forge's loss line. Forge prints every loser's line at game end: in game 1, seqs 1012-1015, all on the final turn.
- `replay.ts:468-471` adds up poison but never clears a seat. `replay/[game]/page.tsx:341` sets `decidingIdx` to the start of the last turn.
- `engine/analysis.py:389` and `results/[file]/page.tsx:600` say combo assembly "is inferred from board reconstruction (83-86% exit-match)". On shim runs the replay says the board is read exactly, so the two contradict each other.

**What the player sees in game 1 of the playtester's run:**
- "Skrat's Revenge's Main phase, precombat" parses as player "Skrat" and phase "Revenge's main phase". The header reads "Round 8 · revenge's main phase, precombat" on the turn that decided the game.
- Attack markers vanish at declare blockers: "Goblin Token blocks Phyrexian Beast Token" appears with no attack drawn.
- Shim reads jump to end-of-turn state, so a Squirrel token made in Main 2 shows up during declare attackers.
- The game is labelled a poison win. Kess, the last opponent, died to combat damage.
- Krenko (46 poison) and Stella (19 poison) stay seated at full opacity for 95 more events, although Forge skipped both of their next turns.
- "Jump to the deciding turn" lands on turn 10's untap step, two turns after Ezuri's Predation.
- The scorecard says Skrat's median knockout came on turn 14. Read from the last damage each knockout took, its seven knockouts came on turns 7 to 12, median 9 (a first-pass parse).

**Why it matters:**
- Possessive deck names are the Commander norm ("Edgar's Vampires", "Yuriko's Ninjas"). The parse bug therefore hits most imported decks, and it makes a board the page labels exact show the wrong state.
- A pod has three knockouts per game, each with its own cause and killer. One label per game erases the story.
- An expert who watched game 1 and then reads "poison" stops trusting every other number.

**Fix:**
1. **Parse phase lines against the known player keys,** longest first (`raw.startsWith(stripAi(key) + "'s ")`, or `"' "` for names ending in s). Check `forge_log_adapter.py` for the same pattern. Add a "Skrat's Revenge" fixture, then re-run `board.py` on a shim result and on the stdout fixture.
2. **Record the cause, killer and moment of every knockout** (engine S). The damage lines already say "combat damage", non-combat or "(as poison counters)", and they name the source card. The zones stream says who controls that card. Emit `knockouts: [{player, turn, cause, by, seq}]` per game, derive the game's method from it, and fix `_death_rounds()` to use it.
3. **Out means out, dated by Forge:**
   - A seat is marked out when Forge stops giving it turns. In game 1, Stella and Krenko get no turn after turn 9.
   - The cause comes from Forge's own loss line. The moment is the last logged event of that cause.
   - The seat greys out and its permanents leave the table (rule 800.4a).
   - Until then, poison and commander damage show as numbers with a warning shape, never the word "lethal". The app never applies rule 704.5c itself.
   - The exact moment waits for a shim release that records each loss when Forge applies it.
4. **The turning point replaces "the deciding turn":**
   - It is the turn with the largest shift in board power toward the eventual winner.
   - On shim runs it comes from the zones stream (creature count and total power per seat), with mass exits as the tie-break.
   - On stdout runs it comes from mass Battlefield exits and token bursts in the log, labelled inferred.
   - Game 1: turn 8, Ezuri's Predation. Skrat's share of the table's creature power went from about 15% to about 86%.
5. **Make the combo note path-aware,** as `Tabletop.tsx:292-294` already does for the replay.

### 2. "Win conditions" is a modelling problem, not a table problem (L; stopgap S)

**Where:**
- The "Win conditions" section of `/results/[file]`: `web/app/results/[file]/page.tsx:438-633`, with the h2 at `:451` and the "AI can fire this; results meaningful" chip at `:568`.
- The data comes from `engine/analysis.py`. `engine/combos.py:90-101` (`_slim()`) drops Spellbook's variant family (`of`) and template pieces (`requires`).
- The same combo list feeds the pilot: `engine/deck_plan.py:323` gives every combo piece weight 8.

**What the player sees (37 to 41 rows on the Kess run):**
- Squirrel Girl has 28 near-duplicate rows. Each carries "draw odds predicted ~0.2; too few games to measure this", 33 identical chips in all.
- Hullbreaker Horror + Sol Ring reads "Assembled 1 of 8, Converted 1, AI can fire this". Spellbook's results for that line are infinite colorless mana and infinite storm count, not a win.
- Stella Lee alone reads "assembled 8 of 8". The loop never ran (137 idle online turns).
- Skrat's real finishers never appear. Across the 8 games:
  - Craterhoof Behemoth was never cast.
  - Triumph of the Hordes was cast in 1 game, twice, because Hullbreaker bounced the first one.
  - Ezuri's Predation was cast in 3 games, and Skrat's won 1 of them.
  - Finale of Devastation was cast in 3 games, and Swan Song countered it in game 1.
- At 1440px the table is 1692px wide inside a 1196px scroller. The "Reading" column starts off-screen and there is no scroll hint.
- The pilot inherits the problem. On turn 6 of game 1, Kess cast Unmarked Grave and binned Sol Ring over Blasphemous Act (`tutor_steer steer=Sol Ring over=Blasphemous Act`), because Sol Ring is a Spellbook piece. With Kess, Dissident Mage on the battlefield, Blasphemous Act in the graveyard is a board wipe it can cast. Sol Ring in the graveyard is a dead card.

**Why it matters:**
- The playtester's complaint was "these aren't my win conditions", and they are right twice: engines are called win conditions, and the cards they built the deck to win with are missing.
- "Converted" means "that seat later won", but it reads as a cause.
- Forge's AI does not run combo loops, so any "won with this line" statistic will sit at zero and read as a verdict against the combo.

**Fix:**
- **Track your win cons, card by card.**
  - Owners tag their win-con cards. Archidekt has a "Win Condition" category and Moxfield has tags, so import both when present.
  - Pre-fill suggestions from `deck_plan.py`'s existing finisher tags, labelled "suggested from card text; confirm", and count only tags the owner has confirmed.
  - The report then states logged facts: cast in N games, earliest turn, won those games. Counting casts of a card the owner named is not rules adjudication.
- **Show combo lines by family and band.** One row per Spellbook family, grouped into five bands:
  - Finishers
  - Combat finishers
  - Locks, extra turns and extra combats. Lock alone is 543 of the 5,582 cached variants; infinite turns is 310 and infinite combat phases 218.
  - Engines that need a payoff
  - Commander loops

  §5.3 has the spec.
- **Measure opportunity, not results:** "pieces together" and "with the mana to start it". Add one plain line: "Forge's AI doesn't run combo loops, so these show chances, not results."
- **Fix the pilot's weights with the same taxonomy** (engine work, task 20). Only lines in the Finisher and Combat-finisher bands get combo weight. A tutor that bins a card should prefer what the deck can use from the graveyard.
- **Stopgap this week:**
  - Rename the section "Combo lines (from Commander Spellbook)".
  - Render `produces` as visible chips. Today it only shows in a `title` tooltip.
  - Delete "AI can fire this".
  - Fold variants client-side when they have identical `produces` and share all but one card.
  - Fold lines with 0 assemblies and expected < 1 under "N more lines never came together".
  - Show Spellbook's description and prerequisites on expand. `_slim()` already keeps both.
  - Let the combo cell wrap.
  - Fix the stale inference note.

### 3. The look is the AI template (S for the CSS, M for home)

**Where:**
- `web/app/globals.css:325-335`: `.page` uses `--panel-glass` at 0.85 alpha plus `backdrop-filter`, and it wraps every route's content.
- `web/app/layout.tsx:25-27` mounts a 2.65 MB PNG backdrop on every route.
- `.btn.pri` and `.action-btn` (around `globals.css:398-415`) are uppercase with 0.04em tracking and an always-on 18px cyan glow.
- `DESIGN_SYSTEM.md` §5-6 and the `--size-cta` token ("two lines, uppercase") require this.
- Home:
  - `web/app/page.tsx:98-114` uses pips as tally icons.
  - `:216-283` is the hero and hub.
  - `:248` is "What would you like to do today?"
  - `:254-274` holds four hardcoded hexes.
  - `:297, :395` render loading as empty.

**What the player sees:**
- Every table, log and board sits on smoked glass over storm art, and every primary shouts.
- Home shows:
  - a mascot and wordmark over the art;
  - "43 decks on this engine · 317 games simulated · 46 finished runs · 3,152 rules loaded", counting up from zero, with W, U, R and C medallions as ornaments;
  - a chatbot greeting;
  - four equal glowing all-caps buttons that duplicate the nav;
  - "0 decks" and "No finished runs yet" beside "loading…" while data loads.

**Why it matters:**
- It fails the 10-second test.
- It hits five items on the repo's own AI-tell list in `mockups/design_principles.md` Part 1: #2 glass and glow, #3 stat banner, #6 all-caps, #8 Space Grotesk, #9 centred hero.
- A red medallion beside "46 finished runs" reads as red decks, which breaks DS law 3.
- False zeros tell a returning player they have nothing.
- This is the cheapest lever in the review: under 20 lines of CSS change the feel of every page.

**Fix:**
- **Paper for reading routes:**
  - Make `.page` opaque (`--surface-obsidian`) with a 1px edge.
  - Mount the backdrop only on home, empty states, the running-sim screen and 404.
  - Re-encode it to AVIF/WebP at about 200 KB, with a 750w variant.
- **Buttons:** sentence case at 15px. The primary is a solid cyan fill with dark ink and no glow at rest.
- **Home:**
  - a two-sentence lede, computed from data, that says what Sim Lab does;
  - one primary;
  - sims running from this browser;
  - the latest sims, each as one sentence with commander avatars;
  - sample pods.

  Loading, empty and error are three separate states. No pips as ornament and no hardcoded hexes.
- **Approval:** these changes amend a binding spec, so they go to the owner as one small, reversible amendment with before and after screenshots (§9.6).

### 4. The cost and status of a sim are misstated (S)

**Where:**
- `web/lib/format.ts:118-124` holds `SECONDS_PER_GAME = {2: 2.5, 3: 11, 4: 52}`.
- The `/new` rail and runbar: `web/app/new/page.tsx:258-269, 295`.
- The home estimate `hub-est` at `web/app/page.tsx:283`, also baked into `DESIGN_SYSTEM.md:251`.
- The engine's own figure is `TYPICAL_GAME_SECONDS = 240` at `engine/mtg_engine.py:556`.
- Rotation rounding: `mtg_engine.py:474-476`.
- The only caller of `simStatus` is `web/app/runs/[id]/page.tsx:61`.

**What the player sees:**
- `/new` says "about 14 min" for 4 decks and 16 games; home says "≈ 8 min". The latest 4-deck, 8-game job took 55 min 56 s, and CLAUDE.md gives 40 to 105 min for 16 games. One click later, `/runs` switches to the server's range.
- The button says "Run 16 games" when 3 decks will play 18.
- "1 game, so you can watch this one play out" actually plays 4 games.
- "Seat order is the order you pick" is false, because every run rotates seats.
- Close the tab and the running sim has no address: home and `/results` list finished runs only.
- On a finished job, `/runs` still says "The simulation keeps running" (`:613`).

**Why it matters:**
- This is the only number shown before an hour-long JVM job.
- It breaks CLAUDE.md's rule that three timing numbers stay separate, and its rule to show the played game count and say why.
- People who can't find a running sim start it again, which slows both copies.

**Fix:**
- Delete the client estimate table and expose the engine's `estimate_sim_seconds` (`GET /estimate?decks=4&games=16`).
- Offer whole rotations only, computed per pod: "4 games (each deck starts once)", "8 (twice)", "16 (four times)". Put the played count on the button.
- Say beside the primary: "Usually 40 to 105 minutes. You can close this tab; it lands in Sims when it's done."
- Remember job ids started in this browser (localStorage, inside try/catch):
  - Pin them as "Running now" rows on home and Sims, using the design system's live-dot shape.
  - Put a live dot on the Sims nav item.
- Offer an optional browser notification when a sim finishes. The user clicks to turn it on. No email until accounts exist (task 06).
- Make the running page worth waiting on: it is the one screen where nothing is read, so the art belongs there, with live playback from `/sim-live` and a seat grid that fills in.
- Make the `/runs` copy match the job's actual state.

### 5. Names read as machine-made (S)

**Where:**
- `web/lib/format.ts:10-15`: `shortName` keeps the first whitespace token, comma included. `:27-33` is `runTitle`.
- `web/app/import/page.tsx:78-83` defaults the deck name to the first card.
- `web/lib/replay.ts:873-888`: `commanderGuess` matches the deck name's first word against cast spells.

**What the player sees:**
- "Kess, vs Stella vs Skrat's vs Krenko" as the report h1.
- "The vs Atraxa vs Ant-Man vs Inspirit" and "Living vs NanMan vs Kambal vs Kilo," on other runs.
- Seat plates reading "Kess,".
- No avatar for Skrat's Revenge or Nekusar Punisher.
- "Kambal Taxes B3" in copy.
- The raw filename as the back link while a replay loads.

**Why it matters:** this is the most-read string in the product, and a stray comma in an h1 is the fastest "nobody looked" signal there is.

**Fix:**
- **The deck's name is its identity,** as on Moxfield and Archidekt, and the commander is its face.
  - Short form: the deck name. When the part before a comma is the commander's name, drop what follows the comma. "Kess, Reanimator" becomes "Kess"; "Stella Lee, Wild Card" becomes "Stella Lee"; "Skrat's Revenge" and "Krenko Goblins" stay as they are.
  - Use one name per deck everywhere, pod title included: "Kess vs Skrat's Revenge vs Stella Lee vs Krenko Goblins".
- **Collisions** fall back to full deck names. The gallery has seven Inspirit lists and eight Kilo lists.
- **Put a 24 to 32px Scryfall art-crop avatar beside every deck mention.** Partner and background pairs show as a split circle.
- **Commanders come from the engine, never from a guess.** Publish the `.dck` `[Commander]` names (already parsed at `engine/analysis.py:232-236`) in the run summary, the results index and the game payload, and readapt old results. Batch avatar art through the `cards.ts` collection cache.
- The import name field starts empty, with the commander as its placeholder.

### 6. Unfinished and operator states reach players (S)

**Where:**
- `page.tsx:28-31`: `fmtClock` renders "NaN:NaN" on clock-cut draws. `:702` shows "T36". `:706-717` shows "Draw (draw)".
- `DeckScorecards.tsx:19-23` relabels "combat damage / life loss" as "by combat damage", so a Vito + Exquisite Blood drain would read as combat.
- Raw Forge strings appear in the replay log.
- `coaching/page.tsx:276-302` shows a glowing primary, "Generate coaching report (~$0.01, about 20 s)", above "the button above will fail. Set MTG_LLM_API_KEY in deploy/.env and redeploy".
- `rules/page.tsx:209, 264-268` shows an "ASK" primary while `health.llm` is false.
- `ENGINE_CMD` ("Start it with python3 engine/mtg_engine.py serve 8484") appears on four pages.
- `Chrome.tsx:136` puts ApiBaseSetting ("Engine /engine Change") in the public phone nav.

**Why it matters:** "never disable the primary" was applied mechanically to a feature that cannot work. Operator detail shown to players is the clearest sign that nobody walked the page as a user.

**Fix:**
- Formatter guards: a missing value is an en dash, and an outcome label never repeats its category.
- Draws say why: "Draw: hit the 15-minute clock on turn 10".
- Causes come from the per-knockout data (problem 1). Until that exists, say "life reached 0 (combat or life loss)".
- When `health().llm` is false, hide the Coaching tab and make "Search the rules" the only primary on `/rules`.
- Put ops copy and ApiBaseSetting behind `NODE_ENV !== 'production'`. Players see: "Sim Lab's server isn't answering. Your decks and sims are safe. Try again in a minute."
- Add to `.claude/skills/ui-review`: "no NaN, undefined, raw ids, braces, env vars or file names in rendered text".

### 7. The report is about the pod, and its headline number can't carry 8 games (L)

**Where:** `/results/[file]` (`page.tsx:272-751`), `/decks/[file]` (`web/app/decks/[file]/page.tsx:170-313`) and `/new` (`page.tsx:178-283`). Nothing in `web/app` has a concept of "your deck", and there are no accounts yet (task 06 waits on task 04).

**What the player sees (as the owner of Skrat's Revenge):**
- The lede and headline figures are about Kess.
- My deck's raw rate is the third scorecard, unmarked.
- The modelled estimate is 1.75 screens down and the combos 2.4 screens down.
- "What killed it" sits on another tab, behind a dropdown that defaults to Kess.
- Import ends in a filename and a small link.
- The deck page never mentions the deck's 14 sims.
- The number the page leads with is a win rate from 7 decided games. Its 95% range spans the pod average for every deck except Kess.

**Why it matters:** the user arrives with three questions: how good is my deck, why did it win or lose, and what should I change. The page makes them hunt, then answers the first question with noise.

Eight games can't support a win rate, but they do support measures counted over turns and attackers. For Skrat's Revenge:
- it took 63 turns;
- it faced 129 attackers, the most in the pod;
- it kept its opening seven in 5 of 8 games, with 2.6 lands in the hands it kept, the fewest in the pod;
- it cast its commander in 7 of 8 games.

**Fix:**
- **A focus deck,** recorded on the job (engine S). It comes from the "Your deck" slot on `/new`, or from `?deck=`. The report defaults to it, with a four-deck switcher. Until accounts exist, "your decks" means decks imported in this browser (localStorage, try/catch), and the page says so.
- **Lead with what 8 games can say:**
  - knockouts, with cause and killer;
  - table politics: attackers faced, who knocked out whom, attack re-aims onto the leader;
  - mana;
  - the commander's cast turn;
  - win-con casts.

  Demote the win rate to "Record", labelled a first look. §5 has the layout.
- **"Run 8 more games"** extends the same pod and pools the results (engine M). It is the natural way to grow a sample.
- **Make `/decks/[deck]` the hub** (task 17): Cards · Sims · Playtest tabs and a "Sim this deck" primary. After import, land on it.
- **Answer "what to change" without coaching:**
  - cards drawn but never cast;
  - cards that sat in hand for 5 or more turns (shim hands are exact);
  - what each tutor fetched, and where it put it.

### 8. The replay isn't watchable (M)

**Where:**
- `replay/[game]/page.tsx:21` sets `SPEED_MS {1:300, 2:150, 4:75}`, and `:211` plays every step on one uniform `setInterval`.
- `:342-343` only ever renders 81 log rows.
- `:456-477` is a click-only `div` scrubber.
- `:504-520`: log rows have no click handler.
- `:379-385` and `:525-531` word the same action "Jump" in one place and "Skip" in the other.

**What the player sees:**
- Phase markers and mana taps are 60.5% of game 1's 980 steps and 64% of game 4's.
- "Cleanup step" holds the screen as long as "cast Ruby Medallion". A game at 1x runs 4.9 to 8.6 minutes, mostly dead air. At 4x, spells flash past unread.
- The kill is a wall of rows, one per token: "Phyrexian Beast Token (979) deals 5 combat damage to Krenko Goblins (as poison counters)".
- Clicking a log row does nothing. Dragging the scrubber gives no feedback until release.
- The position readout says "event 846 of 980". The URL never tracks the playhead.
- Home, End, j/k and ? do nothing.

**Why it matters:**
- The viewer's attention goes into the gaps.
- Every good replay viewer navigates in turns and plays, and treats its log and timeline as navigation: 17lands, HSReplay, lichess, Board Game Arena.
- Commander games also turn on the stack, which a pacing scheme built around combat skips.

**Fix:**
- A beats index ranked by impact, so counters, tutors, reanimation, wipes and knockouts count, not only combat.
- Highlights, Turn by turn and Every event modes.
- Damage runs and didn't-block runs collapsed into single lines.
- Clickable, grouped, virtualised log rows.
- A real `role="slider"` scrubber and a keyboard map.
- `?seq=` deep links. Every event already carries `seq` on both paths, so this is UI work only.

Spec in §4.

### 9. The replay stage (M)

**Where:**
- `globals.css:611` sets `.stage 1fr 330px; gap 40px`, copied from the Vercel-palette wireframe `mockups/simlab_v3_replay.html`, and it sits inside `.page` (max-width 1280).
- `globals.css:644` sizes `.tc` at 46x64; `:664, :688` at 30x42.
- `Tabletop.tsx:79` uses a native `title` tooltip.
- `replay.ts:545` computes `BoardState.stack` but never draws it.
- `Tabletop.tsx:123-124, 181` lays seats out in array order in a 2-column grid.
- `replay.ts:577-587, 653-667` applies zone, tap and counter records per phase, not per event.

**What the player sees:**
- At 1440x900 the stage starts at y=358 and the transport sits at y≈1025-1256, so you see the top seats or the controls, never both. The table gets 826 of 1440px.
- At 375px the four seats stack 1,366px tall.
- Card text is unreadable. Hovering gives a delayed OS tooltip, and the table has zero focusable elements.
- There is no graveyard, exile, library or command zone, which matters for a reanimator deck whose plan is its graveyard.
- The stack is invisible, so the turn-7 counter war (Triumph, Negate, Hullbreaker's bounce) is three unexplained log lines.
- Turn passes in a Z across the 2x2 grid, not clockwise.
- The active player is marked by a 12px grey "· active".
- On shim runs a permanent appears from its phase's first event, so stepping through a busy Main 1 shows spells on the battlefield before their cast line.

**Why it matters:**
- In Magic the card is the unit of meaning.
- Scrubbing is a look-and-drag loop, and it breaks when the control is off-screen.
- The tiles fail WCAG 2.1.1.
- The app already has `useCardPreview`. `/decks` and `/playtest` use it; the replay doesn't.

**Fix:**
- **Prerequisite (engine S):** stamp every shim zone, tap, counter and agent record with the `seq` of the log entry just before it.
  - `shim_raw_*.jsonl` is one stream in emission order, parsed line by line in `shim_log_adapter.parse_shim_jsonl`, so this is a small change plus a `readapt.py` run.
  - Measure how often a card appears before its cast line, before and after.
- **Then build the stage:**
  - a theatre that fits the viewport, with a sticky transport;
  - clockwise seats around a centre "In focus" column;
  - permanents as grouped rows with small art thumbnails;
  - lands collapsed to a strip that shows untapped colours;
  - a zone rail (task 19);
  - a phase ladder;
  - combat arrows.

Spec in §4.

### 10. Win rates: three numbers for one fact, false precision, stale baselines (M)

**Where:**
- `page.tsx:164` divides wins by all games; `DeckScorecards.tsx:112-116` divides by decided games.
- `PredictionPanel.tsx:52-111` and `engine/predict.py:153-157` set the interval to expected ± LOO MAE, independent of sample size.
- The "Winner" column on `/results`: `web/app/results/page.tsx:136, 202-217`.
- The home leaderboard: `page.tsx:187-206`.
- `engine/SIM_CALIBRATION.md:52-58`.

**What the player sees:**
- Kess is "50%" in the lede, "4 of 7 57%" on its card, and "Simulated 50.0%" in the prediction table.
- "Power Cosmic 25%" is crowned Winner of a 4-deck run, which is exactly an even share.
- Talrand won 0 of 6 decided games yet shows "Expected 28.2%, 24.3 to 32.2", ranked above a deck that won.
- The rails show 57% vs 0% from n=7, although 0/7 has a 95% range of 0 to 35%.
- The home leaderboard pools decks from different pods and disclaims its own ranking in fine print.
- Only the even-share marker is shown, with no archetype baseline. The baselines themselves (38% for creature decks, 12% for engine decks) were measured under stock Forge at the old 120 s clock. SIM_CALIBRATION says to re-measure them "before they are shown to a user as a threshold".

**Why it matters:**
- Two numbers for one fact make a careful reader assume the maths is wrong.
- False precision is exactly the overclaim `SIM_CALIBRATION.md` exists to prevent.
- It is also the weakness of the direct competitor, Grim.Cards ("97.3 power · 1 sim"), and the place Sim Lab can visibly beat it.

**Fix:**
- Use decided games as the single denominator everywhere, stating the exclusion once, inline. Have the engine publish the rate so pages can't drift.
- Show whole percents below 30 decided games, and one small range chart per pod (§5.2).
- Suppress the model's estimate below 12 decided games, and widen its range with sample size.
- Replace "Winner" with "Leader", showing "tie" or "no clear leader" where that's the truth.
- Rank the home leaderboard by points above each pod's average, with n shown, or delete it.
- **Baselines:** re-measure them under the plan agent and the current clock (engine M), then show them as a tick on each row. Until then, show the pod average only, labelled. CLAUDE.md ("show archetype baselines") and SIM_CALIBRATION ("re-measure before showing") currently disagree, and the owner should settle it (§9.6).

### 11. Telemetry is broken for imported decks and scores other decks' plans (M)

**Where:**
- `engine/mtg_engine.py:866` calls `compute()` without a commander.
- `engine/deck_telemetry.py:68-91`: `_commander_of` fails for decks in `/data/decks/*`.
- `web/app/results/[file]/telemetry/page.tsx:198-199, 266-285` hardcodes the rows.

**What the player sees:**
- Kess, Reanimator and Skrat's Revenge both say "No commander could be identified", while the bundled decks resolve fine.
- Every deck's only plan rows are "Charge counters 0.12/g Partial" and "Proliferate 0/g Never fired". These are Atraxa-era metrics, counted across all seats.
- The lede for a reanimator deck reads "The table logged charge counters 0.12 times a game and proliferate 0."
- The coach (`coach.py:109`) is fed the same rows.

**Why it matters:** the user's own deck gets the broken view and the house decks get the working one. Template leakage like this is the texture of generated output.

**Fix:**
- Pass the deck's `[Commander]` line through `_find_deck()`, and add a test for `/data/decks`.
- Delete the universal rows.
- Fold the useful parts (knockouts, commander, win-con casts) into the per-deck report (§5).

### 12. The pilot's reasoning isn't shown, and isn't ready to show raw (M)

**Where:** every shim result carries `game.agent_events` (fields: turn, player, event, detail; no phase or seq) and `game.rubric`. Nothing in `web/` references `agent_events`.

**What's in game 1:**
- Useful reasons:
  - `finisher_hold Triumph of the Hordes creatures=1 need=3 instead=Elven Chorus`.
  - Three `kingmaker_reaim` events (Stella twice, Krenko once) that moved attacks onto Skrat's.
  - `tutor_steer steer=Hullbreaker Horror over=Blasphemous Act`: into the graveyard, and Persist returned it on turn 7.
  - `counter_fire Triumph of the Hordes threat=10.0`.
- Things that must not be shown as reasons:
  - `block_skip blockiness-roll`: a deliberate random skip from the humanized personality.
  - Diagnostics such as `search_seen … agree=false pickedW=6 planW=8`, and eight `instant_hold … pass` lines.
  - The Sol Ring entomb.
- A data disagreement: the rubric's final block entry reports 0 blocks from 1 available creature, while the log shows Ledger Shredder and Valgavoth blocking.

**Why it matters:**
- "Why did they do that?" is the question only this product can answer, and it is the evidence an investor wants to see.
- Shown raw, the notes would caption dice rolls as reasons and put known pilot bugs in front of both audiences.
- The owner's own finding is that the agent does not win more than stock Forge.

**Fix:**
- A whitelist of translated codes. They show by default in the study modes and are off by default in Highlights.
- A one-time note that the pilots are humanized with deliberate randomness.
- A "Flag this play" control in study mode.
- Rubric data kept off the table until it agrees with the log.
- Nothing ships before the `deck_plan` weight fix (problem 2).

§4.8 has the details.

### 13. The deck page is a 10-screen oracle dump (M)

**Where:** `web/app/decks/[file]/page.tsx:28-69, 246-300`; `globals.css:869-877`.

**What the player sees:**
- 75 rows at 92px each (9,370px tall), with the full oracle text of cards this audience already knows.
- Costs as raw braces (`{1}{G}{G}{G}`) in 11.5px ink-4 mono.
- No curve, colour demand, bracket, commander banner, record, or link to the deck's sims.
- "99 cards", where every deckbuilder counts 100.
- All 99 cards briefly listed under "Unidentified" while card facts load.

**Why it matters:** Moxfield and Archidekt have trained this audience to expect dense grouped columns with a docked preview. Raw braces are the strongest "unpolished" signal a Magic site can show.

**Fix:**
- A compact 3 to 4 column list grouped by type ("Creatures 25"), each row quantity · name · cost glyphs.
- Oracle text only in a docked preview.
- A stats strip: curve 0 to 7+, type counts, coloured pip demand against sources.
- A header: art banner, colour identity, bracket (from Commander Spellbook's estimate), "100 cards", record.
- A List / Visual / Full text toggle kept in the URL.
- Skeletons while loading, never "Unidentified".

### 14. Type sizes, contrast and colour meanings are in a fog (M)

**Where:**
- **The tokens already exist, but almost nothing uses them.** `arcane-sim-lab.tokens.css:114-125` defines `--size-meta` 12, `--size-data` 13, `--size-body` 15, `--size-h2` 19, `--size-h1` 34, and `--sp-1..9` on a 4px base. `globals.css` has 141 `font-size` declarations and only 2 of them use tokens. The raw sizes: 31 at 12.5px, 23 at 12px, 18 at 13px, 11 at 11px, 9 at 13.5px, 8 at 11.5px.
- **Mono and faint ink dominate.**
  - `.mono { font-size: 0.93em }` (`:163`) compounds into sizes like 12.09px and 12.555px.
  - 48% of the results page's text nodes are JetBrains Mono.
  - 482 of its 628 text nodes are ink-3 or ink-4.
- **Fields people type into have a weak focus cue and faint edges.**
  - `outline: none` on `input.txt`, `textarea.paste` and `.inp input` (`:522, :574, :577`) overrides the global focus ring.
  - `--hairline-strong` measures 1.45:1 against panels.
- **Colours collide with mana colours in the tokens file:**
  - `--arcane-violet` and `--pip-b` are both `#A855F7`.
  - `--state-failed` and `--pip-r` are both `#EF4444`.
  - `--state-done` and `--pip-g` are both `#10B981`.
  - The replay draws attackers in `--state-failed`.
- **Deck results use job-status glyphs.** Krenko's 0 of 7 looks like a crashed job, and Skrat's 1 of 7 wears the hollow "queued" circle.

**Why it matters:**
- This is much of the unnamed "jank". Five sizes crammed between 11 and 13.5px flatten the hierarchy, and a mono face carrying prose makes everything read like a log.
- `DESIGN_SYSTEM.md` §8 promises WCAG 1.4.11 and 2.4.7, and breaks both on the fields people type into.
- Law 3, "a colour never means two things", is broken at the token level.

**Fix:**
- Map the raw sizes onto the existing tokens, add one 26px title step, and lint raw `font-size`.
- Use mono only for figures and ids.
- Restore the focus ring, and add a `--control-edge` token at 3:1.
- Use status shapes for job state only.
- Retire violet as a UI accent, and give combat its own token.

§6 has the details.

### 15. The playtest sandbox is below the Moxfield/Archidekt baseline (L)

**Where:**
- `web/app/playtest/[deck]/page.tsx:230-246`: moves are drag-only.
- `:452-461`: the library is a `role=button` with no tabIndex.
- `:280-315`: buttons are nested inside a role=button.
- `globals.css:906-921`: counter buttons are 18px and appear only on hover.

**What the player sees:**
- Skrat's opening hand held Finale of Devastation and Nature's Rhythm, and the sandbox can resolve neither: there is no library search, no look-at-top-N, no standalone shuffle and no undo.
- Tokens are all named "Token".
- Reset has no confirmation.
- Keyboard users can't send a card to the graveyard.
- On a phone, hand-to-graveyard is a 600px drag.
- The zone label reads "Battlefield (tap to tap)".

**Why it matters:** it fails WCAG 2.1.1, 2.5.7 and 2.5.8, and an enfranchised player compares it with Moxfield once and leaves.

**Fix:**
- A per-card action menu: tap, to hand, graveyard, exile, top or bottom of library, counters.
- Keyboard shortcuts matching Moxfield and Archidekt habits (D, M, N, S, Ctrl+Z, ?).
- Library search, look at top N, shuffle and undo.
- Named tokens from Scryfall `all_parts`.
- A playmat layout, a confirmation on reset, and 44px targets.

All of it stays rules-free: the user decides, and the app only moves cards.

**Below the line, still worth fixing:**
- **First run:** a new playtester has no decks and meets 43 flat tiles, dev variants included. The first-run home should offer one "Paste your list" primary and three sample pods, with test lists behind a toggle.
- **Gallery** (task 12):
  - Group decks by commander (seven Inspirit and eight Kilo variants share art).
  - Show "Decks imported here" first.
  - Make the colour filter a subset filter.
- **Import** (task 13):
  - Fetch Moxfield and Archidekt links directly, as the task specifies. Show export instructions only when a fetch fails.
  - Remove the three dead "coming soon" tabs and the lede that promises fixes that don't exist.
  - Support partner and background commanders.
- **Page basics:** every route's title is "Arcane Sim Lab"; there is no favicon, no `<main>` and no skip link; there are eight bare "Watch" links.
- **Rules search:** `/rules` misses 903.9a for the commonest Commander question, and cuts excerpts mid-word.
- **Card preview:** `CardPreview.tsx:239` shows the previous card until the new image decodes (fix with `key={src}`), and has em dashes in its aria-label.
- **Delete button:** "Delete deck" sits at the same weight as the primary.

---

## 3. Information architecture

### 3.1 The nouns

One concept has seven names today: simulation, sim, run, gauntlet, pod, result, report. Cut them to six nouns, enforced everywhere.

| Noun | Means | Never call it |
|---|---|---|
| **Deck** | A Commander list: its name, with its commander's art | decklist file, `.dck` |
| **Sim** | N seat-rotated games of 2 to 4 decks, running or finished | run, gauntlet, result, report, job |
| **Pod** | The decks in a sim | (fine as a descriptor) |
| **Game** | One game in a sim | round, match |
| **Replay** | Watching one game | playback |
| **Playtest** | Solo, rules-free goldfishing | test |

- "Sim" is the brand word and what players say ("I simmed it").
- **"Turn N" means the table round:** everyone's Nth turn. The replay's "Round 9" becomes "Turn 9". Forge's global counter (T36) is never displayed.
- "Engine", "telemetry", "event" and "job" leave user copy.

### 3.2 Navigation

`[archivist head] Sim Lab     Decks   Sims (•)   Playtest   Rules                 [New sim]`

- Four noun items and one action button. The action is styled secondary, so the page's own primary stays the only primary.
- The Sims item carries a live dot while a sim started from this browser is running.
- Inside a sim, the tab set never changes: **Summary · Games · Coaching**.
  - Coaching is hidden while `llm` is false.
  - Telemetry folds into Summary.
  - A replay is a sub-state of Games, not a tab set of its own.

### 3.3 The primary loop

```
Import deck ──> Deck hub ──"Sim this deck"──> New sim (your deck + opponents preset + rotations + honest duration)
     ^                                                   |
     |                                                   v
 Update deck <── "Worth a look" <── Summary (your deck) <── Sim page (running: live playback; you can leave)
 (diff since                           |        \
  last sim)                            |         "Run 8 more games" (same pod, pooled)
                                       v
                          Games as stories ──> Replay, opening on the turning point ──> next game ]
```

Two loops are missing today:
- **Change the deck, sim again against the same pod, compare.** This needs deck versions, a "same pod as last time" preset, and a "since last sim" diff on the hub showing cards in and out and whether the record moved beyond noise.
- **Grow the sample** with "Run 8 more games".

Both loops need sims indexed by deck. Real ownership needs accounts (task 06); until then "your" means "from this browser", and the page says so.

### 3.4 Page map

| Route | Purpose | Replaces / task |
|---|---|---|
| `/` | What Sim Lab is (2 computed sentences), one primary, running sims from this browser, latest sims with avatars, sample pods | Hero, tally, hub |
| `/decks` | Decks imported here first, then sample decks grouped by commander; sort by recently simmed | 43 flat tiles (task 12) |
| `/decks/new` | Paste box or Moxfield/Archidekt link (fetched directly), live checks, win-con tagging, save, then land on the hub | `/import` (task 13) |
| `/decks/[deck]` | **The hub.** Header: art banner, identity, bracket, 100 cards, record. Tabs: **Cards · Sims · Playtest** | Card dump (task 17) |
| `/sims` | All sims, running ones pinned first; a "Leader" column; deck chips filter | `/results` |
| `/sims/new?deck=` | "Your deck" slot, opponents with presets ("Same pod as last time", bracket fields), rotations, engine-sourced duration | `/new` |
| `/sims/[id]` | **One URL, two states.** Running: live playback, progress, "you can close this tab". Finished: the Summary (§5) | `/runs/[id]` + `/results/[file]` |
| `/sims/[id]/games/[n]` | Replay (§4) | `/results/[file]/replay/[game]` |
| `/sims/[id]/coaching` | Only when live | Always-visible dead tab |
| `/playtest/[deck]` | Goldfish | Same |
| `/rules` | "Search the rules" (plus Ask when live), with chips for 903, 704, 613, 506-511 | Same |

The words matter more than the paths. If routes do change, redirect every old `/results/...` link, because playtesters share them.

---

## 4. Replay viewer redesign spec

### 4.1 What people open a replay for

In order:
1. **How did it end?**
2. **What turned it?**
3. **What did the table do about it?** Counters, blocks, who attacked whom.
4. **Why did they do that?**
5. **What did my deck draw and do?**

The default view answers (1) and (2) within five seconds. The log, the stack and revealed hands answer (3). Pilot's notes answer (4), in the study modes. Seat focus answers (5).

Watching is lean-back and studying is lean-forward, so the viewer supports both: a directed Highlights mode beside a free stepper.

### 4.2 Desktop wireframe (1440x900, one viewport), on game 1's turning point

```
+------------------------------------------------------------------------------------------------------+
| < Sim  (K)(S)(St)(Kr) Kess vs Skrat's Revenge vs Stella Lee vs Krenko Goblins   Game [1] 2 3 ... 8   |  A 44px
|                                                                          Board: read (i)   [Link]    |
| Turn 8 · (S) Skrat's Revenge   Beginning > MAIN 1 > Combat > Main 2 > End      Turning point          |  B 28px
+----------------------------------------------------------------------------+-------------------------+
| +- 1 (K) Kess ---------- 34 -+ +-- IN FOCUS ---+ +- 2 (S) Skrat's Revenge -- 31 -+ | [Moments]  Log        |
| | Kess, Dissident Mage       | |  +---------+  | | ACTIVE · ACTING               | |                       |
| | Lib 58 Gy 12 Ex 1  Cmd -   | |  | Ezuri's |  | | Lib 70 Gy 6  Cmd: Squirrel    | | T4  Kess: Unmarked    |
| | [a] Hullbreaker Horror 6/7 | |  |Predation|  | |   Girl (not cast)             | |     Grave bins        |
| | [a] Kess, Dissident Mage   | |  |  200px  |  | | [a] Citanul Hierophants 3/2   | |     Hullbreaker       |
| | [a] Ledger Shredder 1/3    | |  +---------+  | | [a] Circle of Dreams Druid    | | T6  Skrat's: Finale,  |
| | Lands 9 · 3 up  (U)(U)(R)  | |  Cast by      | | [a] Squirrel Token 1/1        | |     Swan Song counters|
| | Hand 5 [faces]             | |  Skrat's      | | Lands 8 · 1 up  (G)           | | T7  Skrat's: Triumph; |
| +----------------------------+ |  Revenge      | | Hand 3 [faces]                | |     Negate, Hullbreak-|
| +- 4 (Kr) Krenko Goblins 18 -+ |  Stack (1)    | +-------------------------------+ |     er bounces it     |
| | [a] Goblin Token 1/1   x6  | |  1 Ezuri's    | +- 3 (St) Stella Lee ------ 35 -+ |>T8  Skrat's: Ezuri's  |
| | [a] Krenko, Mob Boss 3/3   | |    Predation  | | [a] Stella Lee, Wild Card     | |     Predation         |
| | [a] ...3 more              | |               | | [a] Baral, Chief of Compliance| | T9  Skrat's: Triumph, |
| | Lands 10 · 0 up            | |               | | Lands 9 · 2 up  (U)(U)        | |     Stella, Krenko out|
| | Hand 2 [faces]             | |               | | Hand 6 [faces]                | | T10 Kess out: 45 dmg  |
| +----------------------------+ +---------------+ +-------------------------------+ |                       |
+----------------------------------------------------------------------------+-------------------------+
| (K)   ▁▂▃▃▄▄▅▅▂▂▁ ✕     power per turn, life as a thin line                                          |  G timeline
| (S)   ▁▁▁▂▂▂▂█████████                                                                               |    4 x 20px
| (St)  ▁▁▁▁▁▂▂▁▁ ✕                                                                                     |    + ruler
| (Kr)  ▁▂▂▃▃▄▅▅▁▁ ✕                                                                                    |
|        1   2   3   4   5   6   7   8^  9   10                                                        |
| |<< turn   < play   [  PLAY  ]   play >   turn >>|   Highlights · Turn by turn · Every event   1x   ?  |  H 44px sticky
+------------------------------------------------------------------------------------------------------+
```

*Illustrative. These come from game 1 of `sim_20260925_003803`: the turn, the stack card, Stella's and Krenko's life, Hullbreaker's persisted size, the Moments list and the power trend. The other seat contents, and Kess's and Skrat's life totals, are placeholders.*

**Space budget:**
- At 1440x900: header 44 + ladder 28 + table ~560 + timeline ~100 + transport 44 = 776px.
- At 1366x768, the commonest laptop (about 650px after browser chrome): the timeline collapses to one 40px strip and the table to about 500px.
- Horizontally, the table spans 1440 − 340 (right rail) − 48 (gutters) ≈ 1050px. A 208px centre column leaves about 420 x 280px per seat.

The replay needs to escape the standard `.page` shell: a `.page--theatre` variant with no max-width, no glass and no 36px padding.

### 4.3 Regions

**A. Header strip.**
- Contents:
  - a back link to the sim;
  - four commander avatars and the pod title;
  - a game switcher, where each chip shows the winner's avatar, or an en dash for a draw (`[` and `]` move between games);
  - a provenance chip ("Board: read exactly", or on stdout runs "Board: inferred from the log, 86% exit match") that opens the full TabletopNote;
  - a copy-link icon.
- The page title is the result: "Game 1: Skrat's Revenge wins on turn 10". Never "Game 1".
- Delete the page-level note "Replays fold the event log into board state locally" (`page.tsx:492-495`). On shim runs it contradicts the chip.

**B. Phase ladder.**
- Read-only and compact, after MTG Arena's deliberately minimal ladder. It shows "Turn 8 · (avatar) Skrat's Revenge", then Beginning · Main 1 · Combat · Main 2 · End, with the current step filled.
- Combat expands into attack, blockers and damage only during combat.
- The right end of the row carries the current beat's caption ("Turning point", or a key-moment line) and is empty otherwise.
- The ladder replaces every "X's Upkeep step" row as a playback stop.

**C. Table: clockwise seats with stable geometry.**
- Seat 1 top-left, 2 top-right, 3 bottom-right, 4 bottom-left. Turn passes clockwise, as at a real table and in SpellTable's four-quadrant grid.
- Seats never reflow during playback. Focus is available on demand (4.4).

Seat anatomy, top to bottom:
1. **Plate:**
   - A 40px commander avatar (split circle for partners), the short deck name, and the commander's name as a subtitle.
   - **Life is the loudest numeral on the plate** (28px tabular). A ±delta chip shows for about 900ms on change, and stays static under reduced motion.
   - Poison and commander-damage chips (task 14) appear only when non-zero. They switch to the warning shape at 7 poison and 15 commander damage, and show plain numbers with no verdict word.
   - **ACTIVE** marks whose turn it is.
   - **ACTING** separately marks whoever cast or activated the current beat. Off-turn plays are half of Commander: Stella's Swan Song on Skrat's turn 6, Kess's Chaos Warp during Skrat's attack on turn 10.
2. **Zone rail** (shim runs; task 19):
   - Library · Graveyard · Exile · Command, each a count that opens a popover of the actual cards at the playhead.
   - A crown glyph (inline SVG, not a WotC symbol) marks the commander wherever it is, with "cast 2x · tax 4" from Command→Stack records, or "not cast" when it never left.
3. **Permanents as grouped rows, creatures first:**
   - Each row has a 28px art thumbnail, the name, P/T and a count ("Phyrexian Beast Token 4/4 ×12 · 3 tapped").
   - Rows fit more names into the space than tiles do: a 420x280 seat fits one row of four 96px tiles, but a dozen text rows.
   - The full card image docks in the centre column on hover or focus.
   - A "Card view" toggle shows art tiles for small boards.
4. **Lands strip:** "Lands 9 · 3 up (U)(U)(R)". Untapped colours come from Scryfall's `produced_mana` field, which is display data, not a rules read. That way a viewer can see "Stella has two blue up" before the counter.
5. **Hand:**
   - On shim runs, where hands are exact, faces show under a "Show hands" toggle that defaults to on. Seeing Stella hold Counterspell is what makes a counter war watchable.
   - On stdout runs, card backs.
6. **An "Entered this turn" marker,** read from the zone stream. This is a fact. "Summoning sick" would be a rules inference, so it isn't shown.

- **Active seat:** a 2px cyan frame. This is the sanctioned glow for live activity, and the only one on the page.
- **Out:** the plate reads "Out, turn 9: poison (Skrat's Revenge)", the board clears (rule 800.4a), and the seat keeps its place at reduced opacity.

**D. Centre column, "In focus" (208px).** The one place the eye goes each beat, after HSReplay's played-card spotlight and 17lands' stack card.
- When the stack is non-empty:
  - it shows the top object as a Scryfall `normal` image at 200px, with "Cast by Skrat's Revenge";
  - it shows "→ targeting Triumph of the Hordes", parsed from Forge's `targeting [...]`. Forge names a spell target the same way, which is also how a counter war is detected;
  - below it, a numbered stack list with each caster's avatar.
- When the stack is empty, it shows the hovered or focused card, or failing that the last card to resolve.
- It depends on the seq stamping in problem 9. Without it, main-phase beats show resolved permanents before their casts.

**E. Combat overlay.**
- One arrow per defender, from the attacking seat's creature rows to the defender's plate, labelled "10 attackers · 46 power → Krenko".
- Attacking rows lift and take a dedicated `--combat` accent: a warm hue that matches neither `--pip-r` nor `--state-failed`.
- Blockers get a dashed connector to the creature they block.
- Duplicate names collapse: "10× Phyrexian Beast Token".

**F. Right rail (340px): Moments | Log.**
- **Moments** is the default tab in Highlights mode. It lists the game's key moments, typically 6 to 10, each with its turn, the actor's avatar and one line. Clicking a moment seeks to it.
- **Log** is covered in 4.7.

**G. Timeline.** One lane per seat, in turn order, with the seat's avatar at the left, all on a shared x-axis of turns.
- **Board power is each lane's main mark:** creature count and total power per seat, from the shim zones stream.
  - In Commander, life lags the board. Game 1's lanes split at turn 8 while Stella still sat at 35 life.
  - Life is a thin line scaled to the game's maximum (Kambal sat at 50 in the same sims). Poison shows as dots, and ✕ marks a knockout.
  - On stdout runs, lanes show life and a nonland-permanent count labelled inferred.
- **Four glyphs,** inline SVG and always the same four:
  - ◆ commander cast
  - ▼ mass removal (3 or more nonland permanents leaving in one phase)
  - ◇ counter war (a spell targeting a spell)
  - ✕ knockout

  The turning point gets a labelled flag on the ruler. A "combo came together" glyph waits for the combo rebuild, because it would read the same assembly signal that counts Stella alone as assembled.
- **Playhead:** one vertical line crosses all lanes. The timeline is a `role="slider"` with pointer-capture drag that seeks on `pointermove`, throttled to animation frames. Hovering shows a tooltip ("Turn 8 · Skrat's Revenge · Ezuri's Predation").

**H. Transport (sticky, 44px).**
- Previous turn · previous play · Play/Pause · next play · next turn.
- A mode selector (Highlights · Turn by turn · Every event).
- Speed from 0.5x to 4x, persisted in localStorage inside try/catch.
- "?" for the keyboard map.
- A position readout that says "Turn 8 of 10", not "event 846 of 980".
- Key hints live in button titles.

### 4.4 Surviving dense boards

Commander boards win with tokens: Skrat's won with a dozen Beasts and a pile of Squirrels. In order:
1. **Group identical permanents** into one row with ×N, keeping tokens separate from originals. The replay already does this correctly.
2. **Collapse lands** to the strip.
3. **Past about 10 rows, show "+N more",** which opens **Seat focus**:
   - The seat expands to the full table.
   - The other three become strips along the top, each showing avatar, life, hand, creature count, total power and the top three threats by power.
   - Press 1 to 4 or click a plate to focus; 0 or Esc returns.
   - Nothing reflows on its own.

This is SpellTable's Focused layout, used on demand. Cockatrice's four even strips are the documented failure.

On a combat beat, overflowing attackers render first in the attacking seat, because the attack is the point of the beat.

### 4.5 Beats, tiers and pacing

`lib/replay.ts` builds a beats index over `timeline.steps` and tiers each step by impact, not by event type:

| Tier | Steps | Highlights | Turn by turn | Every event |
|---|---|---|---|---|
| 0 | phase markers, mana abilities, `player_control`, `match_result`, reminder text | skipped (the ladder shows them) | skipped | 250ms |
| 1 | land drops, ordinary casts and resolves, triggers | skipped | 600ms | 600ms |
| 2 | attacks, blocks, collapsed damage and didn't-block runs, life and poison changes, a nonland permanent leaving, commander casts, tutors with their destination, reanimation (Graveyard→Battlefield) | the biggest, by board change | 900ms | 900ms |
| 3 | the turning point, counter wars, mass removal, knockouts | 1800ms, caption held | pause at turn end with a one-line summary | 1500ms |

Times are at 1x.

- **Highlights** is the default for the Play button. It plays tier 3 plus the tier-2 beats with the largest board change, capped near 90 seconds at 1x. Game 1 plays as:
  - Hullbreaker binned (turn 4)
  - Finale countered (turn 6)
  - Hullbreaker reanimated, and the Triumph counter war (turn 7)
  - Ezuri's Predation (turn 8)
  - Bedevil countered, and Triumph's poison attack (turn 9)
  - Exhume, and the final attack (turn 10)
- **Turn by turn** pages through computed turn summaries: "Turn 9, Skrat's Revenge: Triumph of the Hordes; 15 attackers at Stella and Krenko; Krenko 46 poison, Stella 19; both out."
- Arrow keys step through visible beats; Alt+arrow steps through raw events.

### 4.6 Key moments and the turning point

Key moments come only from logged events, the zone stream and, after the rebuild, combo data. Never from oracle text. They are:
- the turning point (problem 1);
- knockouts, with cause and killer;
- mass removal and token bursts;
- counter wars, detected from `cast X targeting [<spell text>]`. The agent's `counter_fire` misses opponents' counters: Stella's Counterspell on Bedevil left none;
- tutors, with their destination (`search_seen … dest=Graveyard`);
- reanimation;
- commander casts.

The replay's lede: "Skrat's Revenge won on turn 10. It turned on turn 8, when Ezuri's Predation killed all three opposing commanders and 12 of their 15 creatures; poison finished Stella and Krenko on turn 9 and combat finished Kess."

Its primary is **[Watch the turning point]**. The duplicated "Jump / Skip to the deciding turn" links go away.

### 4.7 The log (Log tab)

- **A virtualised full list** instead of the 81-row window, so Ctrl-F works. Every row is a `<button>` that seeks. The current row stays highlighted and in view.
- **Sticky, collapsible turn headers:** "Turn 8 · (avatar) Skrat's Revenge".
- **Filter chips:** Key plays · Combat · one per seat · Pilot's notes · Everything.
- **Grammar rewritten in `lib/replay.ts`:**
  - Damage runs collapse: "10 Phyrexian Beast Tokens: 46 poison to Krenko (now 46)".
  - Didn't-block runs collapse: "Kess didn't block 14 attackers".
  - "Life: Kambal Taxes B3 50 > 47" becomes "Kambal 50 → 47 (−3)".
  - Strip `[Card: … Activator: … SpellAbility: …]`. Drop "has restored control over themself" and the match-score line.
  - "Turn 18" becomes a game-over row.
  - Instance ids appear only when two same-named objects need telling apart (the existing disambiguation at `replay.ts:192` stays).
- Every card name is a hover or focus target that fills the In Focus column and pulses the matching row on the table.
- Fix the current-row overflow jitter by replacing the negative margin with `padding-inline` + `box-shadow` (`globals.css:734`).

### 4.8 Pilot's notes

The notes are a whitelist of codes, translated into player language and always worded as the pilot's stated reason, never as right or wrong. They show by default in Turn by turn and Every event, and are off by default in Highlights. A "Pilot's notes" toggle is available in all modes.

| Code (game 1) | Rendered |
|---|---|
| `tutor_steer steer=Hullbreaker Horror over=Blasphemous Act`, with `dest=Graveyard` (turn 4) | "Kess binned Hullbreaker Horror with Unmarked Grave; its plan ranked it over Blasphemous Act." |
| `finisher_hold Triumph of the Hordes creatures=1 need=3 instead=Elven Chorus` (turn 4) | "Skrat's held Triumph of the Hordes (1 creature; it waits for 3) and cast Elven Chorus." |
| `kingmaker_reaim moved=2 onto=Skrat's Revenge leaderThreat=8` (turn 5) | "Krenko moved 2 attackers onto Skrat's Revenge, which it rated the table leader." |
| `counter_fire Triumph of the Hordes threat=10.0 bar=6.0` (turn 7) | "Kess answered Triumph of the Hordes: rated a major threat." |
| rubric mulligans (pregame) | "Skrat's took the free mulligan (1 land), mulliganed again (1 land) and kept 6 with 3 lands." |
| `block_skip blockiness-roll` (turn 8) | Not a reason. Study mode only: "No block. This pilot skips some blocks at random by design." |
| `search_seen`, `instant_hold`, `instant_window`, unknown codes | Never shown to players. Unknown codes are logged for developers. |

- **Anchoring:** agent events carry turn and player but no phase or seq. Until the seq stamping lands, attach each note to the first beat in its turn that names its card.
- **A one-time explainer** on first view: "The pilots are Forge's AI with Sim Lab's plan layer, and they're humanized: some choices are random on purpose."
- **"Flag this play"** in study mode records a link to the moment in a review queue the owner reads. It uses the API-key write path. Misplays will be visible regardless: on turn 9, Hullbreaker bounced itself with a dozen Beasts as legal targets, and that is in the log whatever the notes say. The product needs a way to hear about such plays.
- **The rubric stays off the table.** Its final entry says 0 blocks from 1 available creature, while the log shows two blocks. Until it agrees with the log, it belongs in the scorecard's combat detail, not on a plate mid-replay.
- **Ship order:** the `deck_plan` weight fix first (otherwise the Sol Ring entomb would become a note), then the whitelist. Keep the code dictionary next to the shim's code list.

### 4.9 Beginning and end

- **Pregame:** each seat's kept hand, fanned at readable size, with mulligan notes that name the free mulligan ("took the free mulligan, then went to 6"). On shim runs, hands are exact, which no Arena or MTGO replay can show.
- **End card,** laid over the table at the final step on an opaque surface. It shows:
  - the winner's avatar and "Skrat's Revenge wins, turn 10";
  - knockouts in order, each with turn, cause and killer: "Stella Lee: turn 9, poison. Krenko Goblins: turn 9, poison. Kess: turn 10, combat damage.";
  - the turning-point card at full size. For a 14-creature alpha strike, the killing card is meaningless;
  - [Watch the turning point] and [Next game].
- **Draws:** "Cut off by the 15-minute game clock on turn 10, with Stella (33), Krenko (17) and Kess (8) still in. Skrat's Revenge was already out." Draws hide the turning-point link.

### 4.10 Keyboard map (shown by `?`)

| Key | Action |
|---|---|
| Space / K | Play or pause |
| ← / → | Previous or next play |
| Shift+← / Shift+→ | Previous or next turn (kept from today) |
| Alt+← / Alt+→ | Previous or next raw event |
| N / P | Next or previous key moment |
| T | Turning point |
| Home / End | Pregame or end card |
| [ / ] | Previous or next game |
| 1 to 4 | Focus a seat; 0 or Esc returns |
| − / + | Slower or faster |
| M | Cycle mode |
| H | Show or hide hands |
| C | Copy link to this moment |
| ? | This sheet |

When the timeline has focus: ←/→ step, PageUp/PageDown move by turn, Home/End jump to the ends.

### 4.11 Mobile (375 x 812)

```
+-------------------------------------+
| < Sim   Game 1 of 8   [<] [>]  (i)  |
| Turn 8 · (S) Skrat's · Main 1       |
| (K)34  [(S)31]  (St)35  (Kr)18      |  seat bar: tap to pin, ring = active
+-------------------------------------+
|  ONE SEAT, full width               |
|  plate · zone rail                  |
|  permanents as rows                 |
|  Lands 8 · 1 up (G)                 |
|  Hand 3                             |
|            [stack mini-card, tap] ->|  floats when the stack is non-empty
+-------------------------------------+
| (K)▁▂▃▂ (S)▁▁█ (St)▁▂▁ (Kr)▁▃▁      |  4 lanes x 10px
| |<<  <  [ PLAY ]  >  >>| Highlights |  sticky
+-------------------------------------+
  [ Moments | Log ]  bottom sheet, drag up
```

- One seat at a time, following the active seat by default. Tapping a seat in the bar pins it ("Following: Kess (pinned)"), and swiping moves between seats. This follows Untap.in's mobile seat bar and SpellTable's Focus mode.
- A long press on a card opens a bottom-sheet preview.
- Combat shows as a banner in the active seat ("10 attackers · 46 power → Krenko"), with a tap to jump to the defender.

### 4.12 Honesty on stdout (non-shim) runs

- Keep the path-aware provenance, shrunk to the header chip.
- Hide the zone counts and hand faces that the stdout path cannot know, with a line under the zone rail: "Not recorded on this run".
- Cards of unknown type stay in "Unidentified", never guessed onto the battlefield.
- Board-power lanes and turning points derived from inference are labelled inferred.
- The event log remains authoritative and always one click away.

### 4.13 What data exists vs what needs engine work

| Feature | Source | Status |
|---|---|---|
| Phase ladder | phase events | **Exists**; needs the parse fix |
| Exact board, hands, token P/T | shim `zones` (types, pt, token) | **Exists** (shim ≥ 0.3.0), but **per phase** |
| Per-event board accuracy on shim runs | the preceding entry's `seq` on each record | **Engine S** + readapt; prerequisite for In Focus and Highlights |
| Board on stock runs | stdout inference | **Exists**, labelled inferred |
| Zone counts | zone stream (shim) | **Exists** on shim runs (task 19 still open for graveyard, exile, library) |
| Stack spotlight, spell targets | `stack_add`/`stack_resolve`, `BoardState.stack`, `targeting [...]` | **Computed, never drawn**; targets are a client parse |
| Acting player | the actor named on each cast or activation line | **Client** |
| Untapped colours | tap state + Scryfall `produced_mana` | **Client** (a cache field) |
| Board power per seat | zone `pt` sums, or rubric `attackPower` | **Exists** on shim runs |
| Knockout cause, killer, moment | damage lines + controller from zones + Forge's turn order | **Engine S**; also fixes `scorecard.py` dating |
| Exact elimination moment | shim records the loss when Forge applies it | **Engine S-M** (GPL shim repo, thin adapter) |
| Commander names per seat | `.dck` `[Commander]` | **Engine S** (payload, results index, readapt) |
| Commander damage | damage events + commander identity | **Client**, once commanders are in the payload (task 14) |
| Deep links | `seq` on every event, on both paths | **Exists; UI only.** Readapt renumbers events (the fixture went 2,874 → 2,975), so a stale link falls back to the start of its turn |
| Pilot's notes | `game.agent_events` (turn, player, event, detail) | **Exists, unrendered**; seq anchoring comes after stamping |
| Rubric | `game.rubric` | **Exists**; disagrees with the log on game 1's final block |
| Duration on clock-cut draws | `duration_ms` missing; raw has "Took 900948 ms" | **Engine S**: adapter fallback |
| Card images and art crops | Scryfall hotlinks via the `cards.ts` cache | **Exists**; batch the avatars |

---

## 5. Results page redesign

### 5.1 Hierarchy: verdict, then why, then evidence, then raw

```
Sims / Kess vs Skrat's Revenge vs Stella Lee vs Krenko Goblins                      8 games · 25 Sep
(K)(S)(St)(Kr)  every deck started from every seat twice · Forge AI with Sim Lab's pilot · boards read exactly
Every knockout here came from attacks (2 of 22 as poison). Forge's AI wins with creatures and doesn't
run combo loops, so combo lines show chances, not results.                     How to read this sim

 [ (S) Skrat's Revenge 1-6 · focus ]  [ (K) Kess 4-3 ]  [ (St) Stella Lee 2-5 ]  [ (Kr) Krenko Goblins 0-7 ]

Record
  Skrat's Revenge won 1 of 7 decided games (average in a 4-player pod is 25%). Eight games is a first
  look: the range is 3% to 51%, so this sim can't tell it apart from average yet.
  [ range chart, whole pod, §5.2 ]      [Watch its win: game 1]   Watch its fastest loss   Run 8 more games

Knockouts
  Knocked out 7 times, all by attacks, on turns 7 to 12. The table went after it: 129 attackers faced,
  the most in the pod (Krenko 121, Kess 94, Stella 70).        who knocked out whom · each row filters Games

Win cons
  Ezuri's Predation cast in 3 games (won 1). Triumph of the Hordes in 1 (won it). Craterhoof Behemoth never.
  Combo lines from Commander Spellbook: none came together.                         (§5.3)

Mana
  Kept its opening seven in 5 of 8 games, with 2.6 lands in the hands it kept, the fewest in the pod.

Commander
  The Unbeatable Squirrel Girl was cast in 7 of 8 games. In the one game Skrat's won, it never left
  the command zone.

Worth a look
  Drawn but never cast · sat in hand 5+ turns · what each tutor fetched, and where it put it

Games
  story rows, won then lost (§5.4)
---------------------------------------------------------------------------------------------------
The pod side by side          comparison table (§5.5) · seat grid
How to read this sim          one disclosure: rotation, decided games, clock cuts, model basis
```

*Figures are from `sim_20260925_003803`, with Skrat's Revenge as the focus deck. The knockout turns assume problem 1's dating fix; today's scorecard says 14.*

- **Labels, not questions.** Short sentence-case labels (Record, Knockouts, Win cons, Mana, Commander, Games). Each is followed by one computed sentence, then the figure. FAQ-style question headings are a template tell of their own.
- **The line under the title is computed for this sim** ("every knockout here came from attacks") and links to the full disclosure. It replaces footnotes; it doesn't add to them.
- **Game length gets context only with a source.** When the model's human dataset records game length, compare against it (Kess's median win here came on turn 17). No invented benchmark until then.
- **Pod balance:** when Commander Spellbook's bracket estimates differ across the pod, say so under the title ("Kess: bracket [n]; Krenko Goblins: bracket [m]"). A mismatch often explains 4-of-7 vs 0-of-7 better than any range.
- The focus deck is the default, and the switcher changes the whole report. The pod-level lede moves into the pod section.
- **Delete:**
  - the four headline figures, which restate the lede;
  - "Still standing at the end of 57% of them", which in a four-player game always equals the win rate.

### 5.2 Presenting win rates honestly

1. **One denominator: decided games.** State the exclusion once, inline: "4 of 7 decided (57%); 1 game hit the clock and isn't counted." The engine publishes the rate.
2. **One small range chart per pod,** replacing the rails and the prediction table:

```
                  0%        25%|       50%        75%       100%
                            average
 (K) Kess        ....[=====o==|===================]....      4 of 7
 (St) Stella Lee .[===o========|=====]...                    2 of 7
 (S) Skrat's     [=o===========|==]                          1 of 7   focus
 (Kr) Krenko     o=============|                             0 of 7
                 o sim result + 95% range     | average in a 4-player pod
```

   - Wilson 95% ranges on decided games: Kess 25-84%, Stella 8-64%, Skrat's 3-51%, Krenko 0-35%.
   - The model's estimate, when shown, is a hollow dot, because it is inferred. Below 12 decided games it is suppressed, with the note "Too few games for a model estimate."
   - Archetype baseline ticks join each row once the baselines are re-measured (problem 10). Engine and combo archetypes carry a "floor" tag.
   - The chart is deliberately small. At 8 games its job is to show honestly that the sample is thin, not to be the hero of the page.
3. **Whole percents** below 30 decided games. No decimals on eight-game runs.
4. **Say what more games would buy:** "Telling a 35% deck from an average one takes about 70 decided games." (Near 25%, the Wilson half-width is about ±14 points at 32 games and ±10 at 72.) The "Run 8 more games" action sits beside it.
5. **State the model's basis in plain words:** "Trained on 66 precons played by people, with stock Forge. This sim used Sim Lab's pilot on custom decks."
   - Each deck's existing `explanation` renders under its row.
   - If the model and the sim rank the decks differently, the lede's second sentence says so. There are never two unexplained verdicts.
6. **Leaders, not winners:** "Kess 57% (+32 over average)". Show "tie" for ties, and "no clear leader" at or below 1/N.
7. **Show the rotation instead of only stating it:** a deck-by-seat grid with a win mark in each cell.

### 5.3 Win cons, rebuilt the way a player expects

**Label:** "Win cons". **Answer line** (computed): "Skrat's won 1 game, after Ezuri's Predation on turn 8. Craterhoof Behemoth was never cast. No Commander Spellbook line came together."

**Part 1: the cards you win with.** These are owner-tagged; suggestions from `deck_plan` stay marked until the owner confirms them.

```
Skrat's Revenge · win cons                        cast in    won those    note
  Ezuri's Predation                               3 of 8     1            turning point of game 1
  Triumph of the Hordes                           1 of 8     1            first cast bounced by Hullbreaker
  Craterhoof Behemoth                             0 of 8     –            drawn in [n] games
  Finale of Devastation (tutor)                   3 of 8     1            countered by Swan Song in game 1
  + Tag a card
```

*Cast and won counts come from the 8 games. "Drawn in" is computed per run; hands are exact on shim runs.*

**Part 2: combo lines (from Commander Spellbook).** One row per Spellbook family, never per variant, grouped into five bands:
1. **Finishers:** Spellbook's results include "Win the game", infinite damage or life loss to opponents, or infinite opponent mill.
2. **Combat finishers:** infinite hasty tokens or infinite power. The deck still has to attack.
3. **Locks, extra turns and extra combats.**
4. **Engines that need a payoff:** infinite mana, storm, ETB/LTB, untaps, draw.
   - Payoffs come only from Spellbook's own data: a larger combo in the same 99 that includes the engine's cards and produces a win.
   - Otherwise the row reads "No payoff in this 99 that Commander Spellbook lists."
5. **Commander loops:** the commander plus prerequisites. "Together" must never mean "commander on the battlefield".

How the bands are maintained:
- **The band map** is a table in `analysis.py`, with a test that fails when the cache holds a feature name the map doesn't (343 today). Unmapped features go to "Other lines", not to Engine. The map belongs to whoever owns `analysis.py`, and the failing test is the reminder.
- **Owners can annotate a line's band** ("this is how my deck wins"), stored as deck data, because Spellbook's result list can leave out what a line does in a given 99. Sim Lab never derives a band from card text itself.
- **`_slim()` keeps more fields:** `of`, `requires`, `bracketTag` and each card's initial zone. The cache is then refreshed for the 102 cached lists. Until then, the stopgap folds variants with identical `produces` that share all but one card.

```
Skrat's Revenge  (The Unbeatable Squirrel Girl)
  Combat finisher                                                        Commander Spellbook ->
  The Unbeatable Squirrel Girl (commander) + one of 5 [Concordant Crossroads, Thousand-Year Elixir, ...]
                                           + one of 5 [Cryptolith Rite, Enduring Vitality, ...]   25 variants
    Needs      [Spellbook prerequisite]
    Together   0 of 8 games (about 0.2 expected in 8 from draw odds)
  2 more lines never came together (each expected under once in 8 games)

Kess  (Kess, Dissident Mage)
  Engine: infinite colorless mana, infinite storm count                  Commander Spellbook ->
  Hullbreaker Horror + Sol Ring + [template piece]
    Payoffs    [from Spellbook: combos in this 99 that include these cards and win, or "none listed"]
    Together   1 of 8 games; Kess won that game. The AI doesn't run this loop.

Stella Lee  (Stella Lee, Wild Card)
  Commander loop
  Stella Lee (commander) + [Spellbook's prerequisites]
    On the battlefield in 8 of 8 games; the loop never ran. The AI doesn't run loops, so read Stella's
    results as a floor.
```

*Illustrative layout. The slot lists and deck names come from the playtester's run; bracketed placeholders are Spellbook fields.*

- **Stats per family count any variant:**
  - games in which the pieces were together;
  - games with the mana to start it: Spellbook's `manaNeeded` against untapped sources, on shim runs, labelled;
  - earliest turn;
  - "won that game".

  There is no "won with it". The AI doesn't loop, so it would read 0 forever and look like a verdict.
- **Expand** shows Spellbook's structure verbatim (Initial card state · Notable prerequisites · Steps · Results) and links to `commanderspellbook.com/combo/{id}`. Sim Lab never re-explains the steps.
- The commander gets a crown chip on its piece, and template pieces get a muted chip.
- **Order within a deck:** finishers first, then by games together. Fold anything never together with expected < 1.
- **"One card away"** belongs in Worth a look: the cards that would complete the most finisher lines, taken from Spellbook's near-combos.
- The words "win condition" are reserved for Part 1 and the Finishers band.

### 5.4 Games as story rows

Replace the Game / Winner / Ended / Duration / Decided by / Replay table, which today mixes "T36" with "round 10", shows NaN:NaN, and repeats the winner:

```
 1  (S) Skrat's Revenge · turn 10      out: (St) t9 poison · (Kr) t9 poison · (K) t10 combat
    Turning point, turn 8: Ezuri's Predation.                                [Watch the turning point]
 6  Draw · hit the 15-minute clock on turn 10    out: (S) · still in: Stella 33, Krenko 17, Kess 8
```

- The whole row links to the replay, opening at its turning point.
- Deck chips filter the list ("Kess 4 · Stella Lee 2 · Skrat's 1 · Draw 1"). Clicking a killer in Knockouts filters it too, which ties statistics to evidence.
- Sorts for choosing what to watch:
  - your deck's wins;
  - its fastest loss;
  - the closest finish (three players alive going into the last turn);
  - counter wars;
  - board wipes;
  - comebacks.
- Wall-clock duration moves to Sim details. Every winner gets the same identity marker.

### 5.5 The pod side by side

Replace the four prose scorecards with one comparison table. Decks are columns, each headed by art, pips and W-L, plus a pod-average column. Rows:
- **Outcome:** median win turn, median knockout turn.
- **Table:** attackers faced, knockouts dealt, leader re-aims received.
- **Mana:** missed land drops per 10 turns, kept-7 rate (with the free mulligan counted separately), lands in kept hands.
- **Combat:** blocked %, chump share, attackers committed. These sit behind "Combat detail".

Highlight only the cells that differ meaningfully from the pod average.

### 5.6 What moves and what dies

- **Telemetry:** Knockouts, Commander and Win cons absorb the useful parts. The universal charge-counter and proliferate rows are deleted. "Watched cards" gets a visible "Track a card" field, autocompleted from the decklist; today it needs a hand-typed `?watch=`.
- **Coaching:** hidden until live. When it ships, it reads the win-con casts, knockouts, combo lines and comparison figures, quotes its numbers, and names a replacement for every cut. "Matchups" becomes "Who beat you".
- **Every card name** on these pages gets `CardPreview`, and every deck mention gets its avatar.

---

## 6. Visual language

The Arcane system gives Sim Lab an ownable identity: commissioned pips, the brass archivist and painted plates. It also bakes the AI look into the binding spec, and its colour rule is broken at the token level.

**Direction: art is ceremony, data is paper.** Keep one signature moment and make the data interior the craft.

### Keep, cut, change

| Element | Decision | Why |
|---|---|---|
| **Backdrop art** | **Change.** Only on the home masthead band (about 220px, scrimmed), empty states, 404 and the running-sim screen. Reading pages sit on opaque `--bg-void` / `--surface-obsidian`. Re-encode to AVIF/WebP (about 200 KB, with a 750w variant). Fix the spec's plane name: hedrons read as Zendikar to players, and the spec says Dominaria. | Reading data over high-contrast art costs attention on every glance. |
| **Glass** | **Chrome only:** header, sticky transport, popovers, card preview. `.page` becomes opaque with a 1px edge. | Glass over data is tell #2 in `design_principles.md`. |
| **Glow** | **Live activity only:** a running sim's dot, the active seat, the playhead while playing. Primaries become solid cyan with dark ink and no glow. Delete `--atmosphere-leylines` and the gradient buttons. | Always-on glow is decoration; on live things it is information. |
| **All-caps** | **Cut.** Sentence case at 15px. Retire `--size-cta`'s "two lines, uppercase". | Tell #6. "NEXT TURN: UNTAP ALL, DRAW 1" reads as shouting. |
| **Mascot** | **Keep, quietly.** Its head as the nav mark and favicon (`mascot-brass-archivist-head.webp`). The full figure in empty and waiting states, with no speech and no byline. | A brass artifact creature suits a lab and is IP-safe. It earns warmth where the product is empty or waiting. |
| **Cinzel** | **Keep:** wordmark only, once per page. | The one flourish. |
| **Painted pips** | **Keep for identity at 18px and up** (tiles, headers, plates, filters). **Never as ornament** (the home tally). **Commission a flat cost-glyph set** for sizes under 18px (W U B R G C, hybrid, and a generic numeral disc); the spec itself says the black skull disappears below about 20px. Until then, painted pips at 18px; never braces. | Raw braces are the strongest "unfinished" signal; WotC symbols stay off-limits. |
| **Status shapes** | **Shapes, no hues,** except live cyan. Failed also carries the word "Failed". Job state only, never deck results. | `--state-done` = `--pip-g` and `--state-failed` = `--pip-r`. |
| **Violet** | **Retire as a UI accent.** Secondary buttons become neutral (ink border). | `--arcane-violet` = `--pip-b`. |
| **Combat** | **A dedicated `--combat` token:** a warm hue distinct from `--pip-r` and `--state-failed`, used only for attacks. | Combat is the one place a hue buys speed (Arena's attackers read at a glance). Its own token keeps law 3 intact. |
| **Typefaces** | **Fix usage first:** mono only for figures, ids, seeds and the raw-log toggle; Space Grotesk for prose; `tabular-nums` on every number. Whether to replace Space Grotesk is a later owner call, made by setting the scorecard and the log in two or three candidates and reading them. | The measured problem is mono carrying 48% of the text and five sizes crammed between 11 and 13.5px, not the family. |
| **Home §5-6 of the spec** | **Cut** the tally, the prompt line and the four-button hub. | The spec mandates tells #3, #6 and #9. |
| **A11y contract, law 5 "fixes subtract", em-dash rule, ink floor** | **Keep and enforce.** | The best parts of the system. |

### Typography: adopt the tokens that already exist

| Token | Size | Use | Absorbs |
|---|---|---|---|
| `--size-meta` | 12 | Captions, table headers, chips. **The floor for anything read.** | 11, 11.5, 12 |
| `--size-data` | 13 | Table cells, log rows | 12.5, 13, 13.5 |
| `--size-body` | 15 | Prose, ledes, buttons | 14, 15 |
| `--size-h2` | 19 | Section labels | |
| `--size-title` (new) | 26 | Page titles | |
| `--size-h1` | 34 | Home masthead only | |

- Life totals on replay seat plates use 28px, a replay-only exception.
- Retire `--size-eyebrow` (11px, below the floor) and `--size-cta`.
- Delete `.mono { font-size: 0.93em }`.
- Lint raw `font-size` outside `:root`.
- Give each page two or three `--ink-1` / `--ink-max` anchors. Today 482 of the results page's 628 text nodes are ink-3 or ink-4.

### Spacing and density

- Adopt `--sp-1..9` (4px base) and lint raw px spacing. There are about 290 raw values across 31 sizes today.
- Set `.btns { display:flex; gap: var(--sp-2); flex-wrap: wrap }` globally. This fixes the touching buttons on `/rules`.
- Make tables denser: 36px rows, right-aligned tabular numbers under right-aligned headers. This also fixes `.telet`, which centres headers over left-aligned numbers. The saved space goes to the replay board, which needs size.
- Show filters only when a list passes about 20 rows.

### Colour roles for data

| Role | Treatment |
|---|---|
| Interaction (links, focus, primary, playhead, selection) | Cyan `--mana-cyan` / `--mana-cyan-ink` |
| Live activity | Cyan + glow (the only glow) |
| Colour identity, mana | WUBRG painted pips and flat cost glyphs, nothing else |
| Seat identity | Commander art avatar + seat number + position. **No seat hues** (every hue collides with a mana colour); the timeline uses lanes instead |
| Observed facts | Ink ramp, filled marks |
| Modelled or inferred values | Hollow marks + the word "modelled" or "inferred" |
| Pilot's notes | Register, not hue: a "Pilot" label, italic, thin ink-3 left rule |
| Combat | `--combat` accent + lift + arrows; dashed connectors for blocks |
| Warning thresholds (7+ poison, 15+ commander damage, too few games) | A `--warn` token that isn't a WUBRG hue, paired with the diamond shape and a word |
| Controls | `--control-edge` at 3:1 or better against the surface; `--hairline` for decorative dividers only |

Add `@media (forced-colors: active)` so status shapes draw with borders; today they vanish in High Contrast mode. Stay dark-only until the type and spacing debt is paid.

---

## 7. Voice and microcopy

**Principles**
1. **Write like a player writing up pod night:** "Kess won 4 of 7", "knocked out on turn 8", "took the free mulligan". No engine words and no Forge turn counter.
2. **Computed, never canned.** If a sentence would read the same on another sim, delete it.
3. **Every number carries its denominator and its comparison,** in the same sentence and in table words: "average is 25%", not "even share".
4. **Facts plain, opinions labelled.** The model's estimate is "modelled"; the pilot's reasons are "Pilot's note". Never "results meaningful".
5. **Caveats sit next to their number,** in a few words. The long hedge paragraphs collapse into one "How to read this sim" disclosure.
6. **Sentence case everywhere,** buttons included. No chatbot greetings, exclamation marks, puns ("tap to tap") or whimsy ("hasn't sat down at a table yet").
7. **Use table slang correctly.** "Swing" means an attack, so the decisive moment is the "turning point". "Win cons" are the cards a deck wins with, not every Spellbook line.
8. **Dark features say so in player language** and show no primary. Operator detail never reaches players.
9. **No em dashes** (house rule). Use an en dash for empty values and a true minus sign (−16).

**Before and after (real strings)**

| Where | Before | After |
|---|---|---|
| Home, main line | "What would you like to do today?" | "Paste a Commander list. Sim Lab plays it in four-player games against three other decks, every seat piloted by Forge's AI, rotating seats so nobody keeps the first turn. Then it shows you how your deck won, how it lost, and every game to watch." |
| Home, estimate | "two decks ≈ 5 s a game · four decks ≈ 8 min for 16" | (beside the primary on New sim) "Four decks, 16 games: usually 40 to 105 minutes. You can close this tab; the sim lands in Sims when it's done." |
| New sim, games | "1 game, so you can watch this one play out" | "4 games (each deck starts once)" |
| New sim, empty rail | "Seat order is the order you pick" | "Every deck takes every seat, so order doesn't matter." |
| Report h1 | "Kess, vs Stella vs Skrat's vs Krenko" | "Kess vs Skrat's Revenge vs Stella Lee vs Krenko Goblins" (with four avatars) |
| Game 1 method | "poison" | "Skrat's Revenge, turn 10. Out: Stella and Krenko (poison, turn 9), Kess (combat, turn 10)." |
| Combo section h2 | "Win conditions" | "Combo lines (from Commander Spellbook)"; "Win cons" is reserved for the owner's tagged cards |
| Combo chip | "AI can fire this; results meaningful" | "Together in 1 of 8 games; Kess won that game. The AI doesn't run this loop." |
| Combo chip (×33) | "draw odds predicted ~0.2; too few games to measure this" | (once, above the list) "Lines you'd expect less than once in 8 games are folded below." |
| Games table, draw | "Draw (draw)" · "NaN:NaN" | "Draw: hit the 15-minute clock on turn 10 (Skrat's Revenge already out)" · "–" |
| Replay link | "Jump to the deciding turn" / "Skip to the deciding turn" | "Watch the turning point" |
| Replay log | "Life: Kambal Taxes B3 50 > 47" | "Kambal 50 → 47 (−3)" |
| Replay log (×10 rows) | "Phyrexian Beast Token (979) deals 5 combat damage to Krenko Goblins(as poison counters)." | "10 Phyrexian Beast Tokens: 46 poison to Krenko (now 46)" |
| Replay readout | "Game 1" · "event 846 of 980" · "Round 8 · revenge's main phase, precombat" | "Game 1: Skrat's Revenge wins on turn 10" · "Turn 8 of 10" · "Turn 8 · Skrat's Revenge · Main 1" |
| Record line | "Winner: Power Cosmic 25%" | "No clear leader: Power Cosmic won 25%, the average for a 4-player pod." |
| Coaching (dark) | "Generate coaching report (~$0.01, about 20 s)" … "Set MTG_LLM_API_KEY in deploy/.env and redeploy" | Tab hidden. If reached directly: "Coaching isn't switched on for this server yet." No button. |
| Engine down | "Start it with python3 engine/mtg_engine.py serve 8484" | "Sim Lab's server isn't answering. Your decks and sims are safe. Try again in a minute." [Try again] |
| Import primary | "SAVE DECK TO ENGINE" | "Save deck" |
| Playtest zones | "Battlefield (tap to tap)" · "Hand (tap to play)" | "Battlefield" · "Hand" (the hint appears once in the lede) |
| Scorecard | "Still standing at the end of 57% of them." | (deleted) |
| Deck page lede | "Imported, so it can be deleted from here." | "100 cards: 35 lands, 25 creatures, curve peaks at 3. Simmed 14 times; won 8% of decided games (average 25%)." *(computed per deck)* |
| Empty deck sims | (none) | "No sims for this deck yet." [Sim this deck] |

---

## 8. Craft details that signal a player made this

Each one changes a real screen.

1. **The deck's name with its commander's face,** everywhere: an art-crop avatar, a split circle for partners, no stray commas.
2. **"Turn 8" means the table round.** Forge's T30 never appears, and median turns are never fractional.
3. **Mana costs are drawn, never braced.** Generic mana is a numeral disc, and "tax 4" is drawn the same way.
4. **The commander is tracked the way players track it:** a crown wherever it is, "cast 2x · tax 4", cast turn against its mana value, and "not cast" when it stayed home (Squirrel Girl in the one game Skrat's won).
5. **Every knockout has a turn, a cause and a killer,** on game rows and on the end card.
6. **Lands read "9 · 3 up (U)(U)(R)".** Open mana by colour is how players read a counter window.
7. **Counter wars play out on the stack:** the spell, what it targets, who answered, and the hands that made it possible.
8. **ACTIVE and ACTING are different marks,** because off-turn plays are half the game.
9. **The table's politics are visible:** attackers faced, who knocked out whom, re-aims onto the leader. "The table went after your deck" is the most Commander-native sentence the report can write.
10. **Mulligans are said properly:** "took the free mulligan, then went to 6", with the kept hand fanned.
11. **Numbers are set with care:** a true minus sign, whole percents under 30 games, en dashes for empty values, right-aligned tabular figures.
12. **A bracket on every deck header and tile,** from Commander Spellbook's estimate, and a pod-balance note when brackets differ.
13. **"Watch its win: game 1", not "Watch",** deep-linked to the turning point. Also "Watch its fastest loss".
14. **A docked card preview** that never covers what you're scanning, on every card name in tables, the log, combo lines and coaching.
15. **Per-route titles** ("Game 1 · Kess vs Skrat's Revenge vs Stella Lee vs Krenko Goblins · Sim Lab") and a favicon from the archivist's head.
16. **The warm-up line says what is true:** "Forge is loading its card database and shuffling four decks." Never a generic spinner.

---

## 9. Roadmap

Dependency tags:
- **[UI]** means UI only.
- **[eng S/M/L]** means engine or data work of that size.
- **[owner]** means a decision or spend only Vincent can make.

There is one developer, so every phase has a cut line.

### 9.1 Engine prerequisites, in order

1. **Commander names** in the run summary, results index and game payload, plus a readapt of old results. [eng S] About eight UI items depend on this; if it slips, phase 1 slips.
2. **Per-knockout cause, killer and moment,** with `scorecard.py`'s dating fixed to use it. [eng S]
3. **The phase parse fix** in `replay.ts`, with the same pattern checked in `forge_log_adapter.py`, a "Skrat's Revenge" fixture, and `board.py` re-run on the shim and stdout fixtures. [UI + adapter check]
4. **`GET /estimate`.** [eng S]
5. **A path-aware combo note** (`analysis.py:389`). [eng S]
6. **Shim records stamped with the preceding entry's `seq`,** plus a readapt. Measure how often cards appear early, before and after. [eng S] Prerequisite for phase 2's theatre.
7. **`_slim()` keeps `of`, `requires` and `bracketTag`,** plus a cache refresh for the 102 lists. [eng M] Prerequisite for the combo rebuild.
8. **The focus deck recorded on the job.** [eng S]
9. **Pilot weights** (`deck_plan.py:323`, task 20): combo weight only for finisher-band lines, and graveyard-aware tutor destinations. [eng M] Prerequisite for Pilot's notes.

### 9.2 Phase 1: truth and feel (realistically 2 to 3 weeks)

| # | Change | Problems | Dependency |
|---|---|---|---|
| 1 | **Paper for reading routes:** opaque `.page`; backdrop only on home, empty, running and 404, re-encoded; sentence-case primaries with no glow at rest | 3 | [owner] DS amendment A (one decision, with screenshots) |
| 2 | **Get the story right:** phase parse fix, per-knockout causes, out seats dated by Forge and cleared, the turning point with "Watch the turning point", the path-aware combo note | 1 | prerequisites 2, 3, 5 |
| 3 | **Names and avatars** everywhere | 5 | prerequisite 1 |
| 4 | **Purge machine strings:** NaN, T36, "Draw (draw)", raw Forge strings; ops copy behind a dev flag; Coaching and Ask hidden when `llm` is false | 6 | [UI]; [eng S] duration fallback |
| 5 | **Combo stopgap:** rename, `produces` chips, delete "AI can fire this", client-side family fold, fold lines that never came together, Spellbook description on expand, a line saying the AI doesn't run loops | 2 | [UI] |
| 6 | **Replay basics:** fits one viewport with a sticky transport (`.page--theatre`); bookkeeping skipped in playback; clickable log; collapsed damage and didn't-block runs; `CardPreview` on tiles; `?seq=` links; Home, End and ? keys | 8, 9 | [UI] |
| 7 | **Home and duration:** computed lede, one primary, running sims from this browser, recent sims with avatars; engine estimate, whole rotations, played count on the button, close-tab copy, state-true `/runs` copy | 3, 4 | [owner] amend DS §5-6; prerequisite 4 |
| 8 | **Type adoption:** raw sizes mapped to existing tokens plus a 26px title; mono out of prose; focus ring restored; `--control-edge`; `.btns` gap; per-route titles; `<main>` and skip link | 14 | [UI] |
| 9 | **Win-rate hygiene:** decided games everywhere, whole percents, headline strip and survival tautology deleted, status glyphs off deck results, "Leader" instead of "Winner" | 10 | [UI] |

### 9.3 Validation gate (before any phase 2 item)

- **Test with people.** Sit the playtester who complained, plus two or three other Commander players, in front of scripted tasks:
  - "How did Skrat's Revenge do?"
  - "Why did it lose game 3?"
  - "Find the turn game 1 was decided."
  - "Which of your win cons got cast?"

  Measure time to answer, wrong answers, and where people looked, on both the current build and phase 1.
- **Instrument the app.** Add server-side aggregate counters for replay opens, the furthest step reached, turning-point clicks and report sections reached. No personal data. Without these, Highlights and the pacing work can't be judged.
- Phase 2's order follows what the test shows.

### 9.4 Phase 2 (1 to 2 weeks each)

| Item | Problems | Dependency |
|---|---|---|
| **Replay theatre:** clockwise seats, In Focus with stack and targets, grouped permanent rows, lands strip with colours, zone rail, phase ladder, ACTIVE/ACTING, combat arrows, seat focus, end card, pregame hands, "Show hands" | 9 | prerequisites 1, 6; task 19 |
| **Replay pacing:** impact tiers, three modes, board-power timeline with four glyphs, Moments tab, virtualised grouped log with filters, keyboard map | 8 | prerequisite 6 |
| **Report v1:** focus deck and switcher, labelled sections (Record, Knockouts, Win cons, Mana, Commander, Worth a look), range chart, pod table with table politics, story rows with sorts and filters, rotation grid | 7, 10 | prerequisites 2, 8 |
| **Win cons and combo lines:** owner tagging with `deck_plan` suggestions, per-card casts, five-band families, band-map test, owner annotations, Spellbook layout on expand | 2 | prerequisite 7; [owner] where tags live |
| **Pilot's notes:** whitelist, study-mode default, explainer, "Flag this play" queue | 12 | prerequisites 6, 9 |
| **Telemetry fix and fold** | 11 | [eng S] |
| **Deck page:** grouped list, docked preview, stats strip, header facts, view toggle, skeletons | 13 | [owner] commission flat cost glyphs; [eng S] Spellbook bracket |
| **Running sims:** pinned rows, nav dot, optional browser notification, running page with live playback | 4 | [UI] |
| **Import** (task 13) and **gallery / first run** (task 12) | below the line | [eng S] partner commanders in `convert_decklist.py` |
| **Palette:** violet retired, monochrome status shapes, `--combat`, `--warn`, forced-colors support | 14 | [owner] DS amendment B |

### 9.5 Phase 3 (multi-week)

| Item | Problems | Dependency |
|---|---|---|
| **The loop:** deck hub Sims tab (task 17), deck versions, "since last sim" diff, "same pod as last time", "Run 8 more games" with pooled results | 7 | [eng M] versioning, sims indexed by deck, pooling |
| **Accounts,** so "your" means yours | 7 | tasks 04, 06 |
| **One `/sims/[id]` page with two states,** old routes redirected | 4, 7 | [eng S] job→result mapping |
| **Model honesty:** range widened with sample size, basis stated, estimate suppressed below 12 decided games; **baselines re-measured** under the plan agent | 10 | [eng M] `predict.py`, `archetype.py` |
| **Exact elimination records** from the shim | 1 | [eng S-M] GPL shim repo, thin adapter |
| **Playtest to baseline** | 15 | [eng S] `all_parts` in the `cards.py` cache |
| **Coaching relaunch** | 6 | [owner] `MTG_LLM_API_KEY`; [eng M] `coach.py` |
| **Rules search:** a golden set of 20 Commander questions, 903/704 boosting, sentence-boundary excerpts | below the line | [eng M] |

### 9.6 Owner decisions

1. **DS amendment A** (phase 1): opaque reading surfaces, backdrop limited to ceremony screens, sentence-case primaries without resting glow, home §5-6 removed. One reversible change, with before and after screenshots.
2. **DS amendment B** (phase 2): violet retired as an accent, monochrome status shapes, `--combat` and `--warn` tokens, `--size-cta` and `--size-eyebrow` retired. Later and optional: whether to replace Space Grotesk.
3. **Baselines:** settle CLAUDE.md ("show archetype baselines") against SIM_CALIBRATION ("re-measure before showing"). Recommendation: re-measure, then show.
4. **Spend:** a flat cost-glyph set for sizes under 18px.
5. **Where owner data lives** before accounts exist: win-con tags and band annotations as deck data, editable with the API key.
6. **A feedback queue** for "Flag this play", and who reads it.

### 9.7 Backlog alignment

| Task | This review |
|---|---|
| 12 Deck picker gallery | Adopt the layout; its "glass panels, Space Grotesk" clause follows DS amendments A and B |
| 13 Deck link import | Adopt as specified (direct fetch); export instructions only as the fallback when a fetch fails |
| 14 Commander damage | The plate chip and warning threshold in §4.3 |
| 16 Post-run rollup, gap 2 | Subsumed by Report v1's computed ledes |
| 17 Deck history page | The deck hub's Sims tab and "since last sim" diff |
| 19 Hidden zones | Hands have shipped; the zone rail in §4.3 is the remainder |
| 20 Plan-driven tutor targeting | Add the Sol Ring entomb as evidence; prerequisite 9 |

### 9.8 What not to do

- **No 0-100 power score, letter grade or one-decimal composite.** Honesty is the edge over Grim.Cards.
- **No gameplay creep.** No opponent, adjudication or declared outcome in Playtest, and no "you would have won" in replays.
- **Never decide what happened in a game from oracle text.** Card roles from text may be suggested (the pilot already uses them), but only an owner's tag makes a card a win con in the report, and bands come from Spellbook plus owner annotation.
- **Never apply a rules verdict in our code:** no "lethal", no "summoning sick". A player is out when Forge says so.
- **Don't replace the log with the board,** and don't upgrade stdout boards to "exact".
- **No seat hues and no rainbow timeline.**
- **Don't make follow-active reflow the desktop default.**
- **No game counts that aren't whole rotations,** never a single-seat rate, and no baseline ticks until the baselines are re-measured.
- **No LLM-written ledes or headings.**
- **No server-rendered share images containing card art;** that would rehost Scryfall images.
- **No count-ups, entrance animations or bounce hovers.** Motion only on change.
- **No new disclaimer paragraphs.**
- **No Pilot's notes before the pilot's weights are fixed,** and never an "unrecognised note" shown to players.
- **Nothing clever in the shim.** Notes cross the boundary as data; translation lives in our code.

---

## 10. Design principles for every future screen

1. **Name it the way it's said at the table.** Deck names with commander art, "turn N" as players count it, "turning point" rather than "swing", and win cons as the cards a deck wins with. No engine token, filename, id, env var or brace ever renders.
2. **Get the story right before making it pretty.** Every knockout has a cause, a killer and a turn. Every phase label names the right player. A seat that is out is out.
3. **The user's deck is the subject.** Every analysis screen defaults to the focus deck and answers how good it is, why, and what to change before saying anything about the pod.
4. **Lead with what the sample can carry.** Counts over turns and attackers come before win rates over 8 games, and every rate carries its denominator, the pod average and a range.
5. **Every statistic links to the game that shows it.** A killer filters the games, a game opens at its turning point, and a win con jumps to the turn it was cast.
6. **Facts in ink, inference labelled, verdicts from Forge.** Observed values are filled; modelled values are hollow and named; the pilot's reasons say "Pilot's note" and never judge.
7. **Collapse what's the same; fold what didn't happen.** Variants into families, damage runs into one line, lines that never came together into "N more". If deleting an element loses nothing, delete it.
8. **Art is ceremony, data is paper.** Art only where nothing is read. Glow means live. A colour means one thing, and WUBRG means mana.

---

## Decisions on the critiques

**Accepted, with the evidence checked:**
- **My draft got game 1's story wrong.** Re-reading the payload confirms three things. Ezuri's Predation turned the game on turn 8. Triumph's poison took out Stella and Krenko on turn 9, and Forge skipped their later turns. Kess died on turn 10 to 45 combat damage at 35 life. I rewrote the lede, the end card, the game row and the examples. The "swing" (slang for an attack) is now the "turning point", defined by board power rather than life.
- **The combo problem is modelling, not only layout.** This revision adds:
  - per-card win cons, owner-tagged, with `deck_plan` suggestions;
  - a fifth band for locks, extra turns and extra combats;
  - no "won with it" statistic;
  - the pilot's combo-weight fix. The weight is verified at `deck_plan.py:323`, and the Sol Ring entomb is in game 1's agent events.
- **The shim board is accurate per phase, not per event** (`replay.ts:577-587, 653-667`). Seq stamping is now a named prerequisite.
- **`seq` already exists on every event,** so deep links are UI work only. **The type and spacing tokens already exist,** so the work is adoption, not a new ramp.
- **Pilot's notes:** a whitelist, off in Highlights, an explainer about humanized randomness, a flag loop, and corrected translations. The turn-5 re-aim was Krenko's, and Hullbreaker went to the graveyard.
- **Also taken on board:**
  - Priorities and process: the "feel" lever moved to the top of phase 1; a validation gate and instrumentation; identity stated honestly (per browser until accounts exist); task 13 as specified.
  - Honesty fixes: stale baselines not shown; the stale inference note fixed; the combo glyph deferred; the rubric kept off the plates.
  - New analysis: per-knockout causes, table politics, commander tracking, stranded cards and tutor targets.
  - Replay details: open mana by colour, ACTING distinct from ACTIVE, revealed hands, the free mulligan, seats clearing, grouped rows instead of 56px tiles, the 1366x768 budget, and life lanes scaled to the game's maximum.
  - Report details: "Run 8 more games", bracket and pod balance, sorts for choosing a game to watch, short labels instead of all-caps questions, and "average" instead of "even share".
  - Document fixes: no twee copy, a trimmed precedent list and craft list, and §6 now placed before §7.
- **One new finding from checking the evidence.** `scorecard.py:62` dates knockouts by Forge's end-of-game loss lines, so every "median knockout turn" is really the game's end. Skrat's reads 14; its knockouts actually came on turns 7 to 12.

**Pushed back or adjusted:**
- **Clearing out seats without waiting for the shim.** The designer wanted no out state until the shim records eliminations; the veteran wanted seats cleared at once. Forge's own facts serve both. Forge stops giving an out player turns, and its loss line names the cause. So the seat clears at the last logged event of that cause, and our code never applies the poison rule. A shim release will make the moment exact later.
- **Commander names as the pod title.** I kept one name per deck everywhere: the deck's name, shortened only when it begins with its commander's name, with the commander's art beside it. A title that says "Squirrel Girl" over a body that says "Skrat's Revenge" makes readers map two labels onto one deck.
- **Combat colour.** Neither fully hue-free nor pip red. A dedicated `--combat` token makes attacks read at a glance while red still means red mana.
- **Hullbreaker + Sol Ring as a table-clearing bounce lock.** I adopted owner annotations but not the claim. On its own, the loop spends each Hullbreaker trigger returning its own pieces, and every trigger aimed at an opposing permanent strands one of them. So the line makes mana and storm, and clears a board only with payoffs in the 99. That is exactly why bands come from Spellbook data plus the owner's word, never from our reading of the cards.
- **A human game-length benchmark ("human pods finish by turn 9 or 10").** Not adopted without a source. The report compares against the prediction model's human dataset if it records game length, and says nothing otherwise.
- **"Kess had one blocker."** The log shows Ledger Shredder and Valgavoth blocking on the final turn, while the rubric records 0 blocks from 1 available creature. That disagreement, not only the wording of the note, is why rubric data stays off the table.
- **"The range chart communicates nothing at 8 games."** Kept, but small and no longer the hero. Showing that every range spans the average is the honest message, and the report now leads with the counts that 8 games can carry.
- **Pilot's notes hidden by default.** They are off in Highlights but on by default in both study modes. The differentiator should be one mode away, not buried in a setting.
- **Font family.** I accept that the swap is unevidenced, and it is out of the type work. I still count Space Grotesk as a tell on the repo's own list, so it stays an optional owner decision after the usage fix.