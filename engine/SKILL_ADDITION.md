# Ready-to-merge section for the `mtg-deck-master` skill

I can't edit installed skills from this session (they're a read-only cache here).
Two ways to fold this in:

1. **Easiest:** in a new conversation, say "update my mtg-deck-master skill using
   engine/SKILL_ADDITION.md" — the skill-creator flow can then rebuild and let you
   re-install it via Settings > Capabilities.
2. Or paste the section below into the skill's SKILL.md yourself.

---

## SECTION TO ADD to mtg-deck-master SKILL.md

### Real deck simulation (Forge backend)

When the user asks to "sim this deck", "test this deck", "win rate", "goldfish",
or "how does this deck perform", use the local simulation engine instead of
theorycrafting:

**Prerequisites** (ask user to run once): `bash "<workspace>/MtG Rules Engine/engine/setup_forge.sh"`

**Workflow:**

1. **Export the deck** to Forge `.dck` format (exact card names; singleton + commander):

   ```
   [metadata]
   Name=<Deck Name>
   Deck Type=Commander
   [Commander]
   1 <Commander Name>
   [Main]
   1 <Card>
   ...
   N <Basic Land>
   ```

   Save to `MtG Rules Engine/engine/decks/<name>.dck`. Main must total 99.

2. **Choose opponents**: default gauntlet is `krenko_goblins.dck` (aggro),
   `drana_vampires.dck` (midrange), `talrand_control.dck` (control),
   `selvala_ramp.dck` (ramp) — pick 3 for a 4-player pod, or let the user specify.

3. **Run**:
   ```bash
   cd "MtG Rules Engine/engine"
   python3 run_sim.py --decks <userdeck>.dck krenko_goblins.dck drana_vampires.dck talrand_control.dck \
       --deck-dir ./decks --games 20
   ```

4. **Read results** from `sim_results/sim_<latest>.json`:
   - `summary.win_rates` — headline number per deck
   - `games[].turns[]` — per-turn events; mine for: average game length,
     which turn the user's commander first resolves, death causes
   - If Forge errored on a card name, the raw log names it — fix the `.dck` and rerun.

5. **Report** win rate with sample size caveat (20 games ≈ ±20pp; run 100+ for
   real signal), typical game pattern, and 2-3 concrete deck changes, each backed
   by either sim evidence or a rules citation from the engine
   (`python3 mtg_engine.py rule <n>` / `search <query>`).

**Caveats to always mention:** Forge AI is a decent-but-not-expert pilot; combo
decks and politics-heavy strategies under-perform in AI hands; win rates are vs
this specific gauntlet, not a meta average.

---

END OF SECTION
