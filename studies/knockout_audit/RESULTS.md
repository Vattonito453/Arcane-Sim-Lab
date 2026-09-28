# Knockout and turning-point hand audit: results

**The "human" readings in this audit are model readings.** Every reading was
made by an independent Claude agent reading the evidence files blind (four
readers in passes A and B, plus a third reading of six games), not by a
person. The owner (Vincent) can overrule any item, or either verdict, by
reading the same sheet: the per-item tables below, the frozen readings in
`readings/`, and the evidence files the readers used (kept in the session
scratch folder, never committed, because run R is Richard's private game log).

Pre-registration: `PREREG.md` (commit `ab01b50`, written before the draw and
before any analyzer output for these runs). Analyzer under audit:
`engine/qa/knockouts.py` blob **`16ff99d9527fb675c4a1d35099430b641f3c4a6d`**
(with `engine/qa/context.py` blob `ed6994bc28795fb94b5212d3dfb89b735e04fed4`),
the blob on `main` at `6e4dee8` and, on 2026-09-28, on every week-3 branch
(`r3/game-story`, `r3/flags`, `r3/harness`, `r3/e2-seeding`). Readings frozen
and `score.py` committed in `22c82d8`, before the analyzer was run on these
files.

## Verdicts

| Audit | Pre-registered pass | Result | Verdict |
|---|---|---|---|
| Knockouts (turn, cause, killer) | >= 38 of 40 | **39 of 40** | **PASS** |
| Turning point | >= 16 of 20 | **8 of 20** | **FAIL** |
| Knockout card (reported, no threshold) | none | 27 of 40 | owner decides |

| | Knockouts | Card | Turning point |
|---|---|---|---|
| Run R (Richard's, shim 0.15.0) | 13 / 13 | 9 / 13 | 5 / 7 |
| Run S (local, shim 0.2.0) | 10 / 11 | 5 / 11 | 2 / 5 |
| Run T (local, stock Forge stdout) | 16 / 16 | 13 / 16 | 1 / 8 |
| **Shim path (R + S)** | **23 / 24** | 14 / 24 | **7 / 12** |
| **Stdout path (T)** | **16 / 16** | 13 / 16 | **1 / 8** |

Every one of the 20 knockout games agrees on every sampled knockout except
S-g06 (1 of its 2). No field of any item lacked a consensus. Six games got a
third reading (pass C).

Both verdicts are robust to every ambiguity found (details under
"Sensitivity"): the knockout audit passes under all three readings of the one
contested value (39, 39 or 40 of 40), and the turning point fails under every
reading (7 or 8 of 20).

## What this means for R1

Applying the PREREG table and the repair plan (WS11 task 1, critique item 23):

- **Knockouts pass.** Per-knockout **turn, cause and killer ship in the R1 UI,
  marked audited** (WS11 task 1). Scope of "audited" (a recommendation, see
  "What the audit did not cover"): the sample exercised `combat_damage`,
  `noncombat_damage`, `poison`, `commander_damage` (stdout path only),
  `alt_win` and `deckout`. No `life_loss` (drain), `life_total`, `lose_effect`
  or `concession` knockout exists in the reading set, so those four causes are
  not audited by this study.
- **Turning point fails.** It may **not** be labelled "Turning point". Per the
  plan it **ships labelled "Biggest swing" or is held; the owner chooses.**
  Recommendation, for the owner to accept or reject: the metric measures the
  largest shift in the winner's share of creature power, so if it ships, call
  it "Biggest board swing", show its before and after shares, restrict it to
  shim runs (stdout agreed on 1 of 8 and its board is inferred), and suppress
  it when the before and after shares are equal (defect T1). Otherwise hold it.
- **Knockout card: no threshold was registered**; the owner decides whether the
  UI names it. 27 of 40. Recommendation: if the UI names a card, word it as
  the largest damage source, not "the card that did it", until defects D1 to
  D3 are fixed, and show the winner's spells that turn beside it (the analyzer
  already emits them as `cast_before`; on these items it carries Triumph of the
  Hordes and Craterhoof Behemoth, the cards the readers named in three of the
  thirteen differences, though not Dragon Tempest, which was cast on an earlier
  turn).
- **Any fix made because of this audit must be re-audited on a fresh draw**,
  not on these items (PREREG, "Pass thresholds and what follows"). A fixed
  turning point can earn the "Turning point" label only by passing a new audit.

## How the readings were combined

Pass A (readers A1, A2) and pass B (B1, B2) each read all 22 games of the
reading set; B paired the games differently from A. All four batches came
back complete (every game, every "has lost" line). A and B differed on **6
scored items in 6 games**, so each of those games got a full third reading:

| Item | Pass A | Pass B | Pass C (third reading) | Consensus | Does C decide the verdict? |
|---|---|---|---|---|---|
| R-g05 Krenko Goblins, card | Elemental Token | Bird Illusion Token | Bird Illusion Token | Bird Illusion Token | Card verdict only (with A it would have agreed) |
| S-g01 Meren Graveyard B3, card | Kolaghan, the Storm's Fury | Deathbringer Regent | Deathbringer Regent | Deathbringer Regent | No (analyzer names a third card) |
| R-g03 turning point, card | Ezuri's Predation | Narset's Reversal | Ezuri's Predation | turn 28, Ezuri's Predation | No (all three give turn 28; the card only matters one turn apart) |
| R-g08 turning point, card | Valgavoth, Terror Eater | Dread Return | Valgavoth, Terror Eater | turn 36, Valgavoth | No (analyzer says turn 37, "combat") |
| T-g07 turning point, turn | 27 | 29 | 29 | turn 29, Tribute to the World Tree | **Yes**: agrees with C; had C sided with A, it would disagree |
| T-g18 turning point, turn and card | 26, Runes of the Deus | 22, Unnatural Growth | 26, Runes of the Deus | turn 26, Runes of the Deus | No (analyzer says turn 14) |

Why the third reading came out as it did, from the evidence:

- **R-g05 Krenko, turn 42**: four unblocked 1/1 tokens dealt 1 each (Bird
  Illusion, Elemental, Bird Illusion, Elemental). READER.md: "the source that
  dealt that player the most ... on a tie, the first one listed", so Bird
  Illusion Token. Pass A named the token whose hit reached 0, which is not the
  rule.
- **S-g01 Meren, turn 50**: Kolaghan, the Storm's Fury dealt 18; Deathbringer
  Regent, a Dragon Token and Keiga dealt 19 each. The most is 19 and the first
  listed at 19 is Deathbringer Regent. Pass A named Kolaghan because 18 equalled
  Meren's life, which is not the rule.
- **R-g03, turn 28**: Stella's Narset's Reversal copied Skrat's Ezuri's
  Predation (the original went back to Skrat's hand); the copy, cast by Stella,
  fought and killed every opposing creature and left Stella twelve 4/4 Beasts.
  I named the card whose effect changed the board (Ezuri's Predation), and
  applied the same principle to R-g08.
- **R-g08, turn 36**: Dread Return returned Valgavoth, Terror Eater; the 9/9
  lifelinker then carried Kess from 22 toward 49 and Stella from 33 to 1.
  Valgavoth is the card whose effect changed the board.
- **T-g07**: turn 27 took the old leader Dnide from 14 to 4 (Shelly finished
  Dnide on 28) and cast Tribute to the World Tree, but left N3cro 18 against
  Shelly 23 with comparable boards. Turn 29 put five counter-boosted mana
  creatures down and took Shelly from 22 to 9; after it the heads-up was
  decided. Turn 29.
- **T-g18**: after Unnatural Growth (turn 22) Dnide fell from 25 to 8 while
  Shelly and NanMan sat near 40, so turn 22 did not decide the game. On turn
  26 Runes of the Deus gave the doubled Wildsear double strike and it killed
  Shelly from 40 in one attack (and NanMan from 37 on turn 28). Turn 26.

**Disclosure on pass C.** The PREREG asks for a fresh third reader. The third
readings were made by the agent running this step (the lead's instruction for
this task), which had seen the pass A and pass B readings, though no analyzer
output, when it read. It read each of the six evidence files in full and
applied READER.md; its readings are frozen in `readings/C.json`. The only
scored verdict it decides is the T-g07 turning point (without it the
turning-point score would be 7 of 20, which fails the same way), plus one card
comparison (R-g05 Krenko).

## Every disagreement, explained

### Knockouts (the pass rule): 1 of 40

**S-g06 Ur-Dragon B3 (deck-out).** Turn 32 and cause `deckout` agree. Both
readers gave the killer as `"self"` (Ur-Dragon's own The Ur-Dragon attack
trigger drew it out: "draw that many cards" for 19 attackers with a nearly empty
library); the analyzer gives no killer (`by: null`). READER.md says the killer
is "null for a deck-out or a concession", which is what the analyzer does
(documented at `knockouts.py:51-52`, applied at `knockouts.py:933-935`). The
readers followed a different clause of the same paragraph ("for a player's own
card ..., the player themselves") and did not print a seat. **Verdict: reader
deviation from READER.md, not an analyzer defect.** Scored as a disagreement
because the PREREG counts a malformed reading as disagreeing; see
"Sensitivity".

### Knockout card: 13 of 40 differ (not part of the pass rule)

| Why | Items | Who matches READER.md's card rule |
|---|---|---|
| Readers named the enabling card, not the damage source | R-g01 Stella and Krenko (Triumph of the Hordes vs Phyrexian Beast Token: the Beasts dealt the poison, Triumph gave them infect); S-g03 Atraxa and Kilo (Dragon Tempest vs Dragon Token: Forge logs the token as the source, and Dragon Tempest's own wording makes the entering Dragon deal the damage); T-g03 Shelly (Craterhoof Behemoth vs Tender Wildguide, which dealt 12, the most) | Analyzer |
| Readers named a card for a deck-out | S-g06 Ur-Dragon (The Ur-Dragon vs none; READER.md: card null for a deck-out) | Analyzer |
| Tie broken the other way | R-g05 Krenko (Bird Illusion vs Elemental Token), S-g01 Meren (Deathbringer Regent vs Keiga, the Tide Star), T-g03 NanMan (Klothys, God of Destiny vs Wildsear, Scouring Maw): READER.md takes the first listed, the analyzer the later hit | Readers (defect D2) |
| Same-named tokens summed | R-g08 Skrat (Goblin Piledriver, 22 alone, vs Goblin Token, six tokens at 8 = 48); S-g06 Atraxa (Carrion Feeder 5 vs Plant Token, five at 1 = 5, then the later-hit tie-break) | Readers, on the reading that a "source" is one object (defect D3; the rule is ambiguous) |
| Analyzer names no card for poison not dealt as infect damage | S-g05 Meren (Karn's Bastion's proliferate added the tenth counter), T-g01 NanMan (Etali, Primal Sickness's trigger gave 11 counters after an ordinary 11-damage hit) | Readers (defect D1) |

On the 7 items in the last three rows the analyzer departs from the
pre-registered card rule; on the other 6 the readers did. The readers'
choices on the first row are arguably more useful to a person, which is why
the recommendation above pairs any card with `cast_before`.

### Turning point: 12 of 20 disagree

The analyzer's turning point is "the turn with the largest shift in board
power toward the eventual winner", where board power is creature count and
power as of entry, smoothed with a 3-power prior per seat, and knocked-out
seats are removed from both ends of a turn (`knockouts.py:73-98`). The readers
were asked for "the one turn on which the game swung decisively toward the
player who eventually won it". The per-turn trace (analyzer internals run on
the audited files after scoring) shows why they part:

| Game | Readers | Analyzer | Why they differ (analyzer's shift at the readers' turn, and its rank) |
|---|---|---|---|
| R-g05 | 33, Brass's Bounty | 37, Galvanic Iteration | The swing was burn and cards: four Guttersnipe triggers dealt every opponent 8 and Stella drew deep; creature power moved little (0.095, rank 3 of 42). **Not in creature power.** |
| R-g08 | 36, Valgavoth | 37, combat | Adjacent turns. Valgavoth's arrival is rank 2 (0.173); turn 37's combat, where Stella's attackers died, edged it (0.206). The one-turn tolerance needs the same card, and "combat" is not Valgavoth. **Near miss.** |
| S-g03 | 30, Utvara Hellkite | 18, Kokusho | Kokusho was the only creature with power on the table: raw share 0% to 100%, shift 0.221. Turn 30 is rank 3 (0.126). **Smoothing lets a lone early creature win (T1).** |
| S-g05 | 47, Simic Ascendancy | 44, combat | The game was won by growth counters on an enchantment; turn 47 moved no creature power (0.0, rank 30 of 50). **Alternate win is invisible.** |
| S-g06 | 32, The Ur-Dragon | 35, Acidic Slime | The runaway leader decked itself; eliminations are excluded by design, and the winner's raw share rising 88% to 100% on turn 32 scores negative (-0.05) because every board shrank. Turn 35 is Meren rebuilding from an empty board, raw 0% to 100%. **Elimination excluded; smoothing (T1).** |
| T-g01 | 25, Runes of the Deus | 21, Wildsear | An aura gave double strike; no creature entered (0.0, rank 19). Turn 21's hint is Wildsear, Scouring Maw arriving. **Aura invisible.** |
| T-g03 | 23, Unnatural Growth | 30, Wildsear | A doubling enchantment; power is read as of entry (-0.052, last of 33). **Doubling invisible.** |
| T-g04 | 21, Siona | 13, Ellivere | On turn 13 the winner already held 100% of the (inferred) creature power and still held 100% after; the smoothed share rose with her own growth, shift 0.163. **A "swing" with no swing (T1).** |
| T-g15 | 42, Felix Five-Boots | 32, Nalfeshnee | The fully equipped commander's hit; equipment does not change power as read (0.07, rank 4). **Equipment invisible.** |
| T-g16 | 39, Flaming Tyrannosaurus | 33, Wildsear | Burn pings killed both remaining opponents in one main phase; both eliminations are excluded, so turn 39 scores 0.0. **Burn and eliminations invisible.** |
| T-g17 | 13, Crystalline Armor | 21, Dragonlord Dromoka | The aura that made Siona a lethal voltron threat (0.0, rank 14). One pass-B reader listed turn 21 as an alternative. **Aura invisible.** |
| T-g18 | 26, Runes of the Deus | 14, Wildsear | An aura plus an elimination (Shelly one-shot from 40), scored 0.0. **Aura and elimination invisible.** |

In 9 of the 12 the decisive event was something the metric cannot see by
construction (burn, an alternate win, an aura, equipment or doubler, or an
elimination: R-g05, S-g05, S-g06, T-g01, T-g03, T-g15, T-g16, T-g17, T-g18);
in S-g03 and T-g04, and again in S-g06, the smoothing produced a swing the raw
shares do not support; R-g08 is a near miss. The readers are not the weak
side here: in 18 of the 20 games A and B named the same turn independently. The
analyzer does well where the swing is a board event made of creatures (Ezuri's
Predation, a reanimated Valgavoth, Razaketh, The Ur-Dragon, Deathbringer
Regent's wipe, Tribute plus five mana creatures): those are the 8 agreements.

## Analyzer defects, for the lead to route (not fixed here)

Knockout pass-rule fields (turn, cause, killer): **no defect found** in 40
scored items, nor in the 23 unscored ones (see "Supplementary").

| # | Where | Failing items | Expected (pre-registered rule) | Actual |
|---|---|---|---|---|
| D1 | `engine/qa/knockouts.py:694-710` `_poison_knockout`: the card comes only from damage lines marked "(as poison counters)" (lines 701-706) | S-g05 Meren Graveyard B3 (turn 41); T-g01 NanMan Felix Five-Boots (turn 41) | Karn's Bastion (the activation whose proliferate gave the tenth counter); Etali, Primal Sickness (its combat-damage trigger gave 11 counters; the log tags `[Damage Source: Etali, Primal Sickness (268) ...]`) | `card: null` in both. `by` is right in both (from "receives N poison counter from P", basis `log`) |
| D2 | `engine/qa/knockouts.py:641-651` `_main_source`, line 650: a tie goes to the later hit | R-g05 Krenko Goblins (42); S-g01 Meren Graveyard B3 (50); T-g03 NanMan Felix Five-Boots (33) | READER.md: first listed. Bird Illusion Token; Deathbringer Regent; Klothys, God of Destiny | Elemental Token; Keiga, the Tide Star; Wildsear, Scouring Maw |
| D3 | `engine/qa/knockouts.py:645-648` `_main_source`: damage summed by card name, so several same-named tokens outrank the largest single creature (deliberate, per its docstring) | R-g08 Skrat's Revenge (29); S-g06 Atraxa Counters B3 (39); unscored: S-g06 Kilo (Gnome Token, eight at 2, over The Ur-Dragon's 9 among nine dragons), S-g01 Atraxa, S-g04 Kilo, R-g06 Skrat, R-g05 Kess ("Dragon Token", "Goblin Token" or "Elemental Token") | The largest single source: Goblin Piledriver (22); Carrion Feeder (5) | Goblin Token; Plant Token. The rule's word "source" admits both readings; the owner should pick one convention before the card ships |
| T1 | `engine/qa/knockouts.py:1184-1187` `_share` with `SHARE_PRIOR = 3.0` (`:128`), selected at `:1466-1480` | T-g04 (turn 13, raw share 1.0 to 1.0, shift 0.163); S-g03 (turn 18, raw 0.0 to 1.0 from one 5-power creature); S-g06 (turn 35, raw 0.0 to 1.0; and turn 32, raw 0.88 to 1.0 scored -0.05) | A swing is a change in the winner's share; a turn whose raw share does not move is not one, and a first creature on an empty table is what the prior was meant to damp (docstring, lines 87-89) | Picks a turn with no raw change as the "turning point" (its prose would read "from 100% to 100%"); lone early creatures still win; a turn where the winner's raw share rose can score negative |
| T2 | Scope of `turning_point` (`knockouts.py:1433-1509`) over `_zone_board` / `_log_board` (`:1018-1161`): creature power as of entry only; knocked-out seats removed from both ends (`:1467`); no life, damage-to-player, counter or alternate-win signal | 9 of the 12 turning-point disagreements (table above) | The turn the game swung decisively | The turn the winner's creature-power share rose most. This is a design limit, not a bug: the metric answers a narrower question than the label claims |

## Sensitivity

- **The deck-out killer `"self"`** (the one knockout disagreement). The PREREG
  schema does not define it. Decided before the analyzer ran on these files and
  committed in `score.py`: scored as malformed (disagreeing), the
  pre-registered rule for a malformed reading and the choice that counts
  against the analyzer. Read as the player's own seat it still disagrees (the
  analyzer gives no killer): 39 of 40. Read as "no killer", which is what
  READER.md asks for a deck-out: 40 of 40. The knockout verdict is PASS in all
  three.
- **"Within one turn" for the turning point** is read as one Forge turn number
  (the sampler's reading). Read as one table round (up to 4 Forge turns), the
  items within reach (R-g05, S-g05, S-g06, T-g01) all name a different card, so
  the score stays 8 of 20.
- **Pass C.** Without the third reader's vote on T-g07 the turning point scores
  7 of 20; without it on R-g05 Krenko the card scores 28 of 40. No verdict
  changes.
- **Clustering.** The 40 knockouts sit in 20 games, so errors within a game
  are correlated. The single disagreement is one item in one game, so the
  clustering cannot hide a second failure mode in these data.

## What the audit did not cover

- Causes absent from the whole reading set: `life_loss` (drains such as Blood
  Artist or paid life), `life_total`, `lose_effect` (an unpaid Pact) and
  `concession`. No local result has a concession or a lose-the-game effect
  (PREREG, "Why these runs"), and no drain or paid life decided a knockout in
  these 22 games.
- `commander_damage` was exercised only on the stdout path (all 6 items are
  run T); the shim path's commander-by-card-id branch (`knockouts.py:732`) is
  unaudited.
- Result files adapted before the 2026-09-01 continuation-line fix: runs S and
  T were audited as re-adapted copies (PREREG, "Why re-adapt"), so the
  analyzer's behaviour on un-re-adapted older files is not measured here.
- Three runs, 22 games, three pods. Richard's run is one of them; the other two
  are local pods on both board paths.

## Supplementary (unscored)

The readers reported every elimination, so the 23 knockouts of the reading set
that were not drawn can be compared too. They are **not** part of either
verdict (PREREG: only the 40 drawn items are scored). Turn, cause and killer
agree on **23 of 23**; the card on 16 of 23 (all seven differences are the D2
and D3 conventions or the readers naming the enabling card). Across all 63
knockouts in the reading set, the analyzer found a knockout for every player
the readers found, and the only pass-rule disagreement is the deck-out killer
above.

## Deviations from the PREREG and READER.md

- **Reader output shape.** All four readers returned their JSON through the
  workflow rather than writing files, with turns as digit strings, confidence
  as `"sure"` instead of high/medium/low, no `note` field, and (B2) an extra
  `"none": false` key on turning points. The agent running this step
  transcribed them verbatim into the scratch folder; `freeze_readings.py` then
  froze the scored fields. `score.py` reads a digit string as its integer.
  Confidence is not scored.
- **Readers departed from READER.md's card rule** in 6 items (listed above) and
  gave a non-seat killer for the deck-out. Those readings were scored as given.
- **Pass C** was not read by a fresh agent (see the disclosure above).
- **The analyzer's source was read** (not run) after the readings were frozen
  and before `score.py` was committed, to learn its output shape. That is when
  its documented "no `by` for a deck-out" was seen; the rule chosen for
  `"self"` is the one that counts against the analyzer, and the verdict is the
  same under all three.
- **Committed readings drop the readers' evidence quotes and free-text
  reasons**, per PREREG "Freeze" (no log text), since run R's log is private.

## Per-item tables

Seats are shown without the `Ai(n)-` prefix; `*` marks a game that had a third
reading. "Readers" is the consensus value (at least two readings agree; there
was always one).

### Knockouts (40)

| # | Item | Forge reason | Readers: turn, cause, killer | Analyzer: turn, cause, by | Verdict | Readers' card | Analyzer's card | Card |
|---|---|---|---|---|---|---|---|---|
| 1 | R-g01 Stella Lee, Wild Card | poison | 34, poison, Skrat's Revenge | 34, poison, Skrat's Revenge | agree | Triumph of the Hordes | Phyrexian Beast Token | differs |
| 2 | R-g01 Krenko Goblins | poison | 34, poison, Skrat's Revenge | 34, poison, Skrat's Revenge | agree | Triumph of the Hordes | Phyrexian Beast Token | differs |
| 3 | R-g02 Skrat's Revenge | life | 27, combat, Kess, Reanimator | 27, combat, Kess, Reanimator | agree | Valgavoth, Terror Eater | Valgavoth, Terror Eater | agree |
| 4 | R-g02 Stella Lee, Wild Card | life | 32, combat, Kess, Reanimator | 32, combat, Kess, Reanimator | agree | Valgavoth, Terror Eater | Valgavoth, Terror Eater | agree |
| 5 | R-g03* Krenko Goblins | life | 34, combat, Stella Lee, Wild Card | 34, combat, Stella Lee, Wild Card | agree | Phyrexian Beast Token | Phyrexian Beast Token | agree |
| 6 | R-g03* Kess, Reanimator | life | 32, combat, Stella Lee, Wild Card | 32, combat, Stella Lee, Wild Card | agree | Phyrexian Beast Token | Phyrexian Beast Token | agree |
| 7 | R-g04 Skrat's Revenge | life | 47, combat, Krenko Goblins | 47, combat, Krenko Goblins | agree | Goblin Token | Goblin Token | agree |
| 8 | R-g04 Stella Lee, Wild Card | life | 67, combat, Kess, Reanimator | 67, combat, Kess, Reanimator | agree | Razaketh, the Foulblooded | Razaketh, the Foulblooded | agree |
| 9 | R-g04 Krenko Goblins | life | 63, combat, Kess, Reanimator | 63, combat, Kess, Reanimator | agree | Razaketh, the Foulblooded | Razaketh, the Foulblooded | agree |
| 10 | R-g05* Krenko Goblins | life | 42, combat, Stella Lee, Wild Card | 42, combat, Stella Lee, Wild Card | agree | Bird Illusion Token | Elemental Token | differs |
| 11 | R-g08* Krenko Goblins | life | 37, non-combat, Stella Lee, Wild Card | 37, non-combat, Stella Lee, Wild Card | agree | Crackle with Power | Crackle with Power | agree |
| 12 | R-g08* Skrat's Revenge | life | 29, combat, Krenko Goblins | 29, combat, Krenko Goblins | agree | Goblin Piledriver | Goblin Token | differs |
| 13 | R-g08* Stella Lee, Wild Card | life | 44, combat, Kess, Reanimator | 44, combat, Kess, Reanimator | agree | Kess, Dissident Mage | Kess, Dissident Mage | agree |
| 14 | S-g01* Meren Graveyard B3 | life | 50, combat, Ur-Dragon B3 | 50, combat, Ur-Dragon B3 | agree | Deathbringer Regent | Keiga, the Tide Star | differs |
| 15 | S-g02 Atraxa Counters B3 | life | 34, combat, Ur-Dragon B3 | 34, combat, Ur-Dragon B3 | agree | Stormbreath Dragon | Stormbreath Dragon | agree |
| 16 | S-g02 Kilo Helm Final | life | 37, combat, Ur-Dragon B3 | 37, combat, Ur-Dragon B3 | agree | Dromoka, the Eternal | Dromoka, the Eternal | agree |
| 17 | S-g03 Atraxa Counters B3 | life | 33, non-combat, Ur-Dragon B3 | 33, non-combat, Ur-Dragon B3 | agree | Dragon Tempest | Dragon Token | differs |
| 18 | S-g03 Kilo Helm Final | life | 30, non-combat, Ur-Dragon B3 | 30, non-combat, Ur-Dragon B3 | agree | Dragon Tempest | Dragon Token | differs |
| 19 | S-g04 Atraxa Counters B3 | life | 55, combat, Ur-Dragon B3 | 55, combat, Ur-Dragon B3 | agree | Scion of the Ur-Dragon | Scion of the Ur-Dragon | agree |
| 20 | S-g05 Ur-Dragon B3 | spell | 50, alt win, Atraxa Counters B3 | 50, alt win, Atraxa Counters B3 | agree | Simic Ascendancy | Simic Ascendancy | agree |
| 21 | S-g05 Meren Graveyard B3 | poison | 41, poison, Atraxa Counters B3 | 41, poison, Atraxa Counters B3 | agree | Karn's Bastion | – | differs |
| 22 | S-g05 Kilo Helm Final | spell | 50, alt win, Atraxa Counters B3 | 50, alt win, Atraxa Counters B3 | agree | Simic Ascendancy | Simic Ascendancy | agree |
| 23 | S-g06 Atraxa Counters B3 | life | 39, combat, Meren Graveyard B3 | 39, combat, Meren Graveyard B3 | agree | Carrion Feeder | Plant Token | differs |
| 24 | S-g06 Ur-Dragon B3 | deckout | 32, deck-out, self | 32, deck-out, – | **disagree** | The Ur-Dragon | – | differs |
| 25 | T-g01 Shelly Siona | commander | 29, commander, Dnide Wildsear | 29, commander, Dnide Wildsear | agree | Wildsear, Scouring Maw | Wildsear, Scouring Maw | agree |
| 26 | T-g01 NanMan Felix Five-Boots | poison | 41, poison, Dnide Wildsear | 41, poison, Dnide Wildsear | agree | Etali, Primal Sickness | – | differs |
| 27 | T-g03 Shelly Siona | life | 28, combat, N3cro Raggadragga | 28, combat, N3cro Raggadragga | agree | Craterhoof Behemoth | Tender Wildguide | differs |
| 28 | T-g03 NanMan Felix Five-Boots | life | 33, combat, Dnide Wildsear | 33, combat, Dnide Wildsear | agree | Klothys, God of Destiny | Wildsear, Scouring Maw | differs |
| 29 | T-g04 NanMan Felix Five-Boots | life | 30, combat, Shelly Siona | 30, combat, Shelly Siona | agree | Renata, Called to the Hunt | Renata, Called to the Hunt | agree |
| 30 | T-g04 N3cro Raggadragga | life | 28, combat, Shelly Siona | 28, combat, Shelly Siona | agree | Siona, Captain of the Pyleas | Siona, Captain of the Pyleas | agree |
| 31 | T-g07* Shelly Siona | life | 31, combat, N3cro Raggadragga | 31, combat, N3cro Raggadragga | agree | Radha, Heir to Keld | Radha, Heir to Keld | agree |
| 32 | T-g15 Dnide Wildsear | life | 38, combat, NanMan Felix Five-Boots | 38, combat, NanMan Felix Five-Boots | agree | Nalfeshnee | Nalfeshnee | agree |
| 33 | T-g15 N3cro Raggadragga | commander | 44, commander, NanMan Felix Five-Boots | 44, commander, NanMan Felix Five-Boots | agree | Felix Five-Boots | Felix Five-Boots | agree |
| 34 | T-g16 Shelly Siona | life | 39, non-combat, Dnide Wildsear | 39, non-combat, Dnide Wildsear | agree | Flaming Tyrannosaurus | Flaming Tyrannosaurus | agree |
| 35 | T-g16 NanMan Felix Five-Boots | life | 39, non-combat, Dnide Wildsear | 39, non-combat, Dnide Wildsear | agree | Flaming Tyrannosaurus | Flaming Tyrannosaurus | agree |
| 36 | T-g16 N3cro Raggadragga | commander | 25, commander, Shelly Siona | 25, commander, Shelly Siona | agree | Siona, Captain of the Pyleas | Siona, Captain of the Pyleas | agree |
| 37 | T-g17 NanMan Felix Five-Boots | commander | 35, commander, Shelly Siona | 35, commander, Shelly Siona | agree | Siona, Captain of the Pyleas | Siona, Captain of the Pyleas | agree |
| 38 | T-g17 Dnide Wildsear | commander | 31, commander, Shelly Siona | 31, commander, Shelly Siona | agree | Siona, Captain of the Pyleas | Siona, Captain of the Pyleas | agree |
| 39 | T-g17 N3cro Raggadragga | commander | 25, commander, Shelly Siona | 25, commander, Shelly Siona | agree | Siona, Captain of the Pyleas | Siona, Captain of the Pyleas | agree |
| 40 | T-g18* Shelly Siona | life | 26, combat, Dnide Wildsear | 26, combat, Dnide Wildsear | agree | Wildsear, Scouring Maw | Wildsear, Scouring Maw | agree |

Every analyzer knockout above is dated by an event of its cause (`dated_by:
event`, 40 of 40); 21 carry `basis: zones` and 19 `basis: log`.

### Turning points (20)

| # | Game | Readers (A, B, C) | Consensus: turn, card | Analyzer: turn, event hint, raw share before > after | Verdict |
|---|---|---|---|---|---|
| 1 | R-g01 | A 30, B 30 | 30, Ezuri's Predation | 30, Ezuri's Predation, 0.15 > 0.857 | agree |
| 2 | R-g02 | A 27, B 27 | 27, Valgavoth, Terror Eater | 27, Reanimate, 0.143 > 0.632 | agree |
| 3 | R-g03* | A 28, B 28, C 28 | 28, Ezuri's Predation | 28, Ezuri's Predation, 0.103 > 1.0 | agree |
| 4 | R-g04 | A 51, B 51 | 51, Razaketh, the Foulblooded | 51, Razaketh, the Foulblooded, 0.0 > 1.0 | agree |
| 5 | R-g05* | A 33, B 33, C 33 | 33, Brass's Bounty | 37, Galvanic Iteration, 0.387 > 0.525 | **disagree** |
| 6 | R-g07 | A 44, B 44 | 44, Valgavoth, Terror Eater | 44, Valgavoth, Terror Eater, 0.333 > 0.652 | agree |
| 7 | R-g08* | A 36, B 36, C 36 | 36, Valgavoth, Terror Eater | 37, combat, 0.583 > 0.875 | **disagree** |
| 8 | S-g02 | A 43, B 43 | 43, The Ur-Dragon | 43, The Ur-Dragon, 0.0 > 0.476 | agree |
| 9 | S-g03 | A 30, B 30 | 30, Utvara Hellkite | 18, Kokusho, the Evening Star, 0.0 > 1.0 | **disagree** |
| 10 | S-g04 | A 34, B 34 | 34, Deathbringer Regent | 34, Deathbringer Regent, 0.0 > 1.0 | agree |
| 11 | S-g05 | A 47, B 47 | 47, Simic Ascendancy | 44, combat, 0.125 > 0.385 | **disagree** |
| 12 | S-g06 | A 32, B 32 | 32, The Ur-Dragon | 35, Acidic Slime, 0.0 > 1.0 | **disagree** |
| 13 | T-g01 | A 25, B 25 | 25, Runes of the Deus | 21, Wildsear, Scouring Maw, 0.286 > 0.615 | **disagree** |
| 14 | T-g03 | A 23, B 23 | 23, Unnatural Growth | 30, Wildsear, Scouring Maw, 0.2 > 0.481 | **disagree** |
| 15 | T-g04 | A 21, B 21 | 21, Siona, Captain of the Pyleas | 13, Ellivere of the Wild Court, 1.0 > 1.0 | **disagree** |
| 16 | T-g07* | A 27, B 29, C 29 | 29, Tribute to the World Tree | 29, Paradise Druid, 0.5 > 0.636 | agree |
| 17 | T-g15 | A 42, B 42 | 42, Felix Five-Boots | 32, Nalfeshnee, 0.0 > 0.6 | **disagree** |
| 18 | T-g16 | A 39, B 39 | 39, Flaming Tyrannosaurus | 33, Wildsear, Scouring Maw, 0.44 > 0.611 | **disagree** |
| 19 | T-g17 | A 13, B 13 | 13, Crystalline Armor | 21, Dragonlord Dromoka, 0.133 > 0.35 | **disagree** |
| 20 | T-g18* | A 26, B 22, C 26 | 26, Runes of the Deus | 14, Wildsear, Scouring Maw, 0.4 > 0.625 | **disagree** |

## Files

| File | What |
|---|---|
| `PREREG.md`, `READER.md`, `draw.py`, `sample.json` | Pre-registration, reader instructions, the draw and its output (earlier commits) |
| `readings/{A1,A2,B1,B2,C}.json` | The frozen readings: turns, causes, seats, cards and confidence only |
| `freeze_readings.py` | Produced `readings/` from the readers' full outputs in the scratch folder |
| `score.py` | The PREREG scoring rules; `--self-mode` for the sensitivity runs |
| `run_analyzer.py` | Runs `knockouts.analyse_game()` on the md5-checked audited files; records the blob |
| `analyzer_output.json` | What the analyzer said for all 22 games (Forge's loss text and `cast_before` dropped) |
| `items.json` | Machine-readable per-item results: every reading, the analyzer, the verdicts, the summary |

Reproduce (the audited run files live in the session scratch folder; run R can
be fetched from the public `/engine/results/{file}` route, S and T re-adapted as
PREREG describes):

```
py studies/knockout_audit/run_analyzer.py <runs_dir> analyzer_output.json
py studies/knockout_audit/score.py analyzer_output.json --out=items.json
py studies/knockout_audit/score.py analyzer_output.json --self-mode=null
```
