# Market scan, exit analysis, and monetization plan

Researched 2026-08-03. All third-party numbers are cited estimates (Similarweb,
Graphtreon, PitchBook summaries) unless they come from a company's own page.
Treat traffic and Patreon figures as order-of-magnitude, not audited.

**Not legal or investment advice.** The legal notes are market observations that
should feed the lawyer conversation `deploy_plan.md` already schedules.

---

## 0. The headline

Three findings change the plan:

1. **Someone is already shipping this exact product.** `grim.cards` launched in
   2026: a custom build of **the open-source Forge engine**, AI-vs-AI gauntlet
   per submitted decklist, a 0–100 Power Score with letter grade, and
   "card-level coaching and counterfactual suggestions." Same engine, same
   mechanic, same coaching pitch. It is free and it publishes a methodology
   white paper. This is not a hypothetical competitor.
2. **Ads cannot fund a simulation product.** Every incumbent has a near-zero
   marginal cost per user (static deck pages). Ours is a 4 GB JVM for 10–60
   minutes. Gaming display RPM is roughly $2–6 per thousand sessions, the
   bottom of the niche table. The ads-first monetization order in `CLAUDE.md`
   is inherited from a category with different economics and does not survive
   contact with our cost structure.
3. **The exit asset is the results corpus, not the code.** Acquirers in this
   category buy audience and data. `engine/sim_results/` is currently
   gitignored and described as disposable because "all of it regenerates by
   running a sim." That is true of the bytes and false of the asset: a corpus
   of *user-submitted decklists paired with outcomes* cannot be regenerated,
   and it is the only thing here that is both unique and unambiguously ours.

---

## 1. Competitive landscape

Crowded at the edges, genuinely thin in the middle. Roughly 15–20 tools compete
for MTG deck-builder attention, two of them at enormous scale, and a 2025–2026
wave of small AI-flavored entrants. But only one other product does
**full-rules batch simulation of a submitted deck**, and it is nine weeks old.

### Tier 1 — Scale incumbents (not direct competitors, but they own the audience)

| Product | Scale | Model | Notes |
|---|---|---|---|
| **Moxfield** | ~15M visits/mo (Similarweb, Dec 2025) | Patreon only, est. $6K–27K/mo, ~3,400 paid members | Independent, founder-owned (John and Harry). Best-in-class editor. Goldfish playtest built in. |
| **EDHREC** | ~15M visits/mo (Similarweb, Oct 2025) | Display ads + affiliate | Owned by **Space Cow Media** |
| **Archidekt** | Large, second to Moxfield | Free core, ~$2/mo Patreon removes ads | Also Space Cow Media |
| **MTGGoldfish** | Large | Ads + premium | Content-led |
| **Scryfall** | Large | Donations | Infrastructure. We depend on it. |

Note carefully: **Space Cow Media owns EDHREC, Archidekt, Cardsphere,
Commander Spellbook, and Commander's Herald**, and has expanded into Flesh and
Blood (FABREC.gg) and WoW (RaidFeats.gg). They acquired Cardsphere on
2023-11-01. They are a serial acquirer of exactly this category — and
`engine/combos.py` already depends on their Commander Spellbook API. They are
simultaneously the most likely buyer and a supplier we are dependent on.

### Tier 2 — Direct competitors (simulation / evaluation)

| Product | What it does | Overlap |
|---|---|---|
| **Grim.Cards** | Forge-engine AI-vs-AI gauntlet, Power Score 0–100 + letter grade, card coaching, leaderboard. Free. Founded 2026 by Steve Spencer, Riverton UT. | **Near-total.** See §2. |
| **Playgroup.gg** | Win rates from *real tracked human games* (10,982 stock precon games), plus **Playgroup Live**, a full browser Commander client with rules adjudication, 2–6 player pods, voice chat. Free. | Same question, different and arguably better evidence. See §5. |
| **ManaTap.ai** | Monte Carlo mulligan/draw simulation, AI chat, deck checker. Freemium: 2,000 sims free, 20,000 on Pro. | Partial. Hypergeometric math, not rules simulation. |
| **Rate My Decks / ScrollVault** | Static power scoring from 12 factors, bracket calculators, Game Changer detection. Free. | Competes for "how good is my deck?" without any simulation. |

### Tier 3 — Playtest / goldfish tools

MTGRocks Playtest, EDHcheck Deck Tester, playsim.live, TableCommander,
Tabletop Simulator mods, Moxfield's built-in playtester. All free, all
zero-marginal-cost, several with no account required. These make our planned
goldfish sandbox (`tasks/08-goldfish-mode.md`) table stakes rather than a
differentiator.

### Tier 4 — Future entrants

- **Space Cow Media** could bolt simulation onto Archidekt and reach 15M
  visits on day one.
- **Moxfield** already has the deck data and the trust; a "simulate this deck"
  button is a sprint for them.
- **WotC/Hasbro** — Magic did **$1.72B in FY2025, up 59%**, and Q1 2026 was up
  36% with the Wizards + Digital segment up 26%. They have the wallet and, per
  D&D Beyond, the appetite (§4).
- **Untapped.gg / HearthSim** — a real analytics company (from HSReplay.net),
  Premium at **$7.99/mo**, already in MTG Arena. They understand this business
  better than anyone else on this list.

---

## 2. Grim.Cards: read this section twice

From their own white paper (`grim.cards/case-study/2026-07-01`), covering
2026-05-14 to 2026-07-01:

- **4,808 games** across **223 submitted decks** (195 Commander, 28 Standard)
  from **107 distinct users**.
- Fixed gauntlet of five meta-representative opponents per format, held
  constant as the controlled variable.
- Custom build of the open-source Forge engine, AI-vs-AI only.
- They *do* disclose the AI-piloting limitation explicitly, and they refuse to
  draw strategy conclusions ("No strategy conclusions are drawn",
  "correlation is not causation throughout").

**What this tells us:**

- We are not behind. 107 users in seven weeks is a pre-traction product. The
  category is unproven, not captured.
- They have chosen honesty as a positioning too, which removes "we are the
  honest one" as a standalone wedge.
- **They do not appear to seat-rotate.** The white paper describes a fixed
  gauntlet and never mentions rotation or turn-order correction. In a
  four-player format where turn order is a large effect, their Commander win
  rates carry an uncorrected positional bias, and their headline finding
  ("the opponent matters more than any single construction variable",
  matchup spreads of 18.5–45.5 points) is exactly what seat bias plus a
  fixed five-deck gauntlet would manufacture. `engine/SIM_CALIBRATION.md`
  mandates rotation. **This is our single sharpest technical differentiator
  and it is defensible in public, with numbers.**
- A **0–100 Power Score with a letter grade** is a product lesson worth
  stealing on the merits: it is the artifact the audience actually wants,
  and it is compatible with honest presentation if the grade is
  archetype-adjusted and the confidence interval is shown. Our current plan
  leads with a prose verdict, which is more honest but less shareable. Ship
  both: a scored, shareable headline over an honest interval.

**Do not conclude the market is taken.** Conclude that the differentiators
have to be sharper than "we simulate decks," because that sentence is now
someone else's homepage.

---

## 3. Positioning map

Two axes actually matter:

- **X: evidence source** — static heuristics/consensus → Monte Carlo math →
  full-rules AI simulation → real human game telemetry
- **Y: output depth** — a number → a report → a coached action plan

```
                    coached action plan
                            │
              Grim.Cards ───┼─── [WHITE SPACE: rotation-correct sim
                            │      + telemetry + specific swaps
   ManaTap ─────────────────┤      with attributed evidence tiers]
                            │
        report              │                    Playgroup.gg
                            │                    (real games, thin coaching)
   RateMyDecks ─────────────┤
   ScrollVault              │
        a number            │
                            │
  ──────────┼───────────┼───┼───────────┼──────────────────┼──────
        heuristics   Monte Carlo    full-rules sim    human telemetry
```

**The white space is the top-right-of-center:** simulation evidence that is
*methodologically defensible* (rotation, archetype baselines, floor labeling)
fused with telemetry the sim alone cannot produce, delivered as specific
swaps with each recommendation tagged by evidence tier
(`[sim-evidence]` / `[consensus]` / `[theory]` — already in the §6 plan of
`frontend_architecture.md`). Nobody occupies it. Grim.Cards is closest and is
missing rotation and telemetry. Playgroup.gg has better evidence and almost no
coaching.

---

## 4. Exit analysis

### The comps

| Deal | Price | Date | Read |
|---|---|---|---|
| **D&D Beyond → Hasbro/WotC** | **$146.3M cash** | Apr 2022 | The ceiling case. A fan-built digital toolset with ~10M registered users, bought by the IP owner. Proves WotC buys rather than only sues. |
| **TCGplayer → eBay** | up to **$295M** | Oct 2022 | Marketplace economics, not tool economics. Different category. |
| **Mobalytics → ESL FaceIt Group** | undisclosed | Mar 2025 | Sobering. Raised $13.9M over 5 rounds, exited for an undisclosed sum. Undisclosed after $13.9M raised usually means "not a headline." |
| **Cardsphere → Space Cow Media** | undisclosed | Nov 2023 | The realistic base case for a tool of our size. Terms not disclosed, community-preservation framing. Almost certainly small. |
| **Overwolf** | raised $150M | — | Platform aggregator; buys and distributes companion apps. |

### What an acquirer is actually buying

Not the code. In every deal above, the assets were **audience, data, and
distribution**. This has a direct and uncomfortable implication for the
`CLAUDE.md` GPL posture: the process boundary is worth maintaining because
compliance is cheap and hygiene matters in diligence, but the exclusivity
argument is doing less work than the doc claims. Nobody is paying a premium
for our Python because it is un-GPL'd. They are paying for users and for a
dataset they cannot rebuild.

**So the asset to deliberately manufacture is the corpus.** Every gauntlet run
pairs a *user-submitted decklist* with *outcomes, telemetry, and a full event
log*. That is:

- unique (no one else has user-deck → simulated-outcome pairs at scale)
- not GPL-encumbered (Forge produced the games; we own the collected records)
- impossible to backfill (a competitor needs the same user submissions)
- the training substrate for a better AI pilot, which is the only mechanism
  here with a real scaling advantage

Right now `engine/sim_results/` is gitignored, 108 MB, and documented as
disposable. Correct for the raw 31 MB of `forge_raw_*.log`. **Wrong for the
decklist → summary → telemetry triple.** Recommendation in §6.

### Realistic exit bands

| Scenario | Buyer | Price band | What it requires |
|---|---|---|---|
| **Base** | Space Cow Media, Moxfield, a TCG content roll-up | **$50K–$1.5M** | 50–300K monthly visits, a defensible dataset, clean GPL/IP hygiene, modest revenue |
| **Good** | Untapped.gg/HearthSim, Overwolf, eBay/TCGplayer | **$2M–$10M** | Category-defining data authority, real subscription revenue ($20–80K MRR), the corpus as the moat |
| **Long shot** | Hasbro/WotC | **$20M–$100M+** | Becoming the de facto analysis layer for Commander with millions of registered users, i.e. the D&D Beyond path. Low probability. |
| **Most likely actual outcome** | — | **a profitable small business, no exit** | This is a good outcome. Plan for it. |

Be clear-eyed: the median outcome in this category is an undisclosed
low-six-figure acquisition or a lifestyle business. Build for cash flow, and
treat the exit as an option the corpus keeps open rather than the plan.

---

## 5. Biggest threat

**Playgroup.gg**, and not because of their play client.

Their win rates come from **real tracked human games** — 10,982 of them for
precons alone, with published inclusion thresholds (20+ tracked games from 10+
distinct pilots). Against that, "our AI simulated it" is the weaker claim in
every conversation, permanently. Worse, their data has a **network effect**:
every user who tracks a game makes their dataset better. Our simulation output
does not improve when users arrive; it is deterministic compute. They have a
flywheel and we have a cost center.

They also give away a full browser Commander client with automatic rules
adjudication, 2–6 player pods, and voice chat — which drives the tracking that
feeds the flywheel.

**Two consequences:**

1. **The moat has to be the corpus plus the pilot, not the simulation itself.**
   A humanized `PlayerController` trained on our accumulated corpus is the one
   asset that improves with scale (`frontend_architecture.md` §5 treats this as
   an optional post-launch quality upgrade — it is closer to the whole moat).
   Simulation quality is our flywheel or we do not have one.
2. **Consider partnership over competition.** Their weakness is coaching depth
   and per-deck specificity: they can tell you a precon's win rate, not what to
   change in *your* list. That is exactly our output. A data partnership (their
   human telemetry calibrating our sim, our coaching served on their decks) is
   more valuable to both sides than a fight, and it directly answers the
   calibration problem `SIM_CALIBRATION.md` currently solves with hand-tuned
   archetype baselines.

### One legal observation, flagged not resolved

`CLAUDE.md` treats an opponent, rules adjudication by the app, or a declared
win/loss as tripwires requiring legal review. **Playgroup Live and
TableCommander both cross all three, publicly, today, and explicitly claim Fan
Content Policy coverage.** WotC's enforcement history in this space is real but
narrow: the notable takedown is **Card Conjurer (Nov 2022)**, and the stated
grounds were reproduction of trademarks, logos, card text, *and artwork* — an
asset-reproduction problem, not a gameplay problem.

This does not make a play client safe, and it does not change the
recommendation to keep our posture conservative. It does mean the tolerated
boundary appears wider in practice than the doc assumes, and that the real
tripwire may be **asset reproduction** rather than gameplay. Worth putting
in front of the lawyer as a specific question, because it is cheap to ask and
it affects the goldfish-mode scope.

---

## 6. Monetization plan

### The economics that decide this

A gauntlet run is 10–60 minutes of a 2-vCPU box. At ~$25/mo that is roughly
**$0.02–0.05 of compute per run**, but the binding constraint is capacity, not
cost: one box supports on the order of 2 concurrent runs, so **~70–100 runs/day
per box**.

Now price the two funding models against a run:

- **Ads:** a user who runs one sim might view ~10 pages. At a gaming-niche
  $2–6 RPM that is **$0.02–0.06 of ad revenue per run** against $0.02–0.05 of
  compute. Gross margin is approximately zero, and it goes negative the moment
  you add a worker to clear the queue.
- **Subscription:** a $6/mo subscriber running 4 gauntlets costs ~$0.15 of
  compute. **~97% gross margin**, and revenue scales with the exact thing that
  drives cost.

Moxfield confirms the ceiling on goodwill funding from the other direction:
~15M visits/month converts to roughly **$11K/mo and ~3,400 paid members**.
That is a conversion rate well under 1% and roughly $0.0007 of revenue per
visit. **This audience does not pay much, and it does not pay voluntarily.**
Any plan that needs this audience to donate its way through a compute bill
fails.

### Ranked paths

**1. Affiliate on the coaching output — highest revenue per user, zero legal
exposure, ship first.**

TCGplayer pays **3.5%** with a 48-hour first-referrer attribution window.
A Commander upgrade basket is realistically $30–100, so a converting user is
worth **~$1.00–3.50** — one to two orders of magnitude better than ads per
user. And the fit is exact: our flagship output is *a list of specific cards to
buy, with evidence for why*. That is the highest purchase-intent surface in
the hobby, and unlike EDHREC's "85% of decks run this," we can say the sim
measured the difference. AetherHub already proves the pattern (they let
creators substitute their own affiliate code). Add Card Kingdom as a second
option so the recommendation does not look bought.

**2. Subscription for simulation capacity — the only model aligned with cost.
Ship second, after the lawyer conversation.**

Gate *capacity and depth*, never insight:

| Tier | Price | Contents |
|---|---|---|
| Free | $0 | 1 quick read/mo (1 pod × 16), full replay, full rules Q&A, public leaderboard |
| **Pro** | **$5.99–7.99/mo** | Rotated 4-pod gauntlets, priority queue, unlimited quick reads, deck history and version diffing, coaching on every version |
| Creator/Pod | $19–49/mo | Bulk runs, custom gauntlets, exportable data, embeddable results |

Market precedent makes this an easy conversation rather than a novel risk:
**GrimDeck $3.99/mo**, **Untapped.gg Premium $7.99/mo**, **ManaTap Pro** gates
simulation counts specifically, **Archidekt ~$2/mo** removes ads, and Moxfield
takes Patreon money at scale. `CLAUDE.md` currently orders ads first and flags
any paid tier as the risky category needing legal review beforehand. Keep the
legal review — but the framing to bring to it is that we charge for **compute
and our own analysis**, never for WotC IP, and that the category has
established norms.

**3. Creator and publisher deals — small volume, high willingness to pay,
nobody is serving it.**

Content creators need "we ran 1,000 games" segments and precon reviewers need
numbers on release day. Selling gauntlet runs and embargo-window precon
benchmarks at $200–2,000 per engagement is real money against our actual cost
curve, and every deliverable is also marketing. This is the fastest path to
first revenue and the cheapest distribution we have.

**4. Ads — a floor on zero-marginal-cost pages only.**

Run them on rules Q&A, public leaderboards, and shared replays, where a
pageview costs nothing. Never let ad revenue be the thing paying for a JVM.
Expect $2–6 RPM.

**5. Patreon — cultural credit, not a business.**

Cheap to add, well-liked, zero legal surface. Budget it as $0–2K/mo at our
plausible scale, and do not let it delay #1 or #2.

### Recommended sequence

1. **Now:** TCGplayer + Card Kingdom affiliate links on every coaching swap and
   every decklist view. Nothing else changes. This is a day of work and it is
   the highest revenue per user available.
2. **Now:** start persisting the corpus properly (§7).
3. **Pre-launch:** the lawyer conversation, covering the paid tier *and* the
   asset-reproduction question from §5.
4. **At launch:** free tier + Patreon + ads on static pages. Measure how many
   users run a second gauntlet — that retention number decides whether Pro is
   viable at all.
5. **Launch + 60 days:** ship Pro at $5.99 if and only if repeat-run retention
   justifies it. Do a creator deal in the same window.

---

## 7. Concrete recommendations for the repo

1. **Persist the corpus. This is the exit asset and we are currently deleting
   it.** Add a durable, compact per-run record — decklist hash and normalized
   list, gauntlet id, seat-rotated results, telemetry, win method, and a
   pruned event digest — written to a real store, not `sim_results/`. Keep
   discarding `forge_raw_*.log` (31 MB of the 108 MB, nothing reads it) and
   keep discarding the fat adapted JSON if storage bites. Never discard the
   decklist → outcome pair.
2. **Make seat rotation a public, marketed claim.** Grim.Cards appears not to
   rotate. `SIM_CALIBRATION.md` already requires it. Write the comparison up
   with numbers and publish it — it is the most credible differentiation we
   have and it costs one blog post.
3. **Add a shareable scored headline over the honest interval.** A 0–100
   archetype-adjusted score with a confidence interval and the floor label,
   sitting above the prose verdict. Grim.Cards is right that the audience
   wants a number; our calibration discipline is what makes the number
   defensible.
4. **Reorder the monetization language in `CLAUDE.md` and
   `frontend_architecture.md`** once the lawyer signs off, and record the
   reason: ads-first is a zero-marginal-cost strategy and our marginal cost is
   a JVM.
5. **Reprioritize the humanized `PlayerController`.** It is currently an
   optional Phase 3 quality upgrade. It is the only asset that compounds with
   the corpus, which makes it the moat. Move it up.
6. **Open a conversation with Playgroup.gg.** Their human telemetry is the
   calibration input `SIM_CALIBRATION.md` currently approximates by hand.
   Complementary, not competitive.
7. **Note the Space Cow Media dependency.** `engine/combos.py` depends on
   Commander Spellbook, owned by the most likely acquirer and a potential
   competitor. Cache aggressively (already done) and keep a fallback path so a
   single API decision cannot break the product.

---

## 8. Revision (2026-08-03): the agent is the wedge

> **CORRECTION, 2026-08-04.** The central claim of this section was tested and
> **not supported.** The precon correlation pilot (512 games,
> `studies/precon_correlation/PILOT_RESULTS.md`) found that agent v3 does *not*
> predict human precon win rates better than stock Forge: Δr = −0.063, 95% CI
> [−1.249, +1.068], and the agent was worse on every calibration measure
> (weighted Pearson 0.006 vs 0.499; calibration slope 0.167 vs 0.472; mean
> absolute gap 22.0 pp vs 17.7 pp).
>
> Caveats that keep this from being a verdict: n=8 decks, the control gauntlet
> was too weak, and censoring was asymmetric (agent 19.9% vs stock 7.8%). A
> re-run on a fixed instrument could change it.
>
> **What survives:** the behavioural-resemblance numbers below are measured from
> agent telemetry and are untouched. What fails is the *further* inference that
> resemblance buys predictive validity.
>
> **What this section got right:** "the moat is the measurement apparatus, not
> the heuristics." The pilot chose between this section's two claims and
> vindicated that one. See §9 for the corrected position.

Added after reviewing the measured agent-vs-stock numbers in
`engine/SIM_CALIBRATION.md` and `training/ai_vs_human_analysis.md`. This
section supersedes the emphasis in §5, which under-weighted the pilot.

### The measured gap

| Behavior | Stock Forge | Agent v3 | Human reference |
|---|---|---|---|
| Attack-split rate | **0%** (244/244 single-defender) | 22.7% | "constantly" |
| Block rate | 8-14% | 23.2% | routine blocks |
| Mulligan rate | ~3% (keeps 7 in 97% of 1,786 hands) | 23.7% | 15-25% |
| Commander deploy (median) | turn 30+ for synergy decks | player-turn 5 | player-turn 4-5 |
| Casts tutors | **never** | yes, with steered searches | always |
| Pursues own win condition | **never** | gated line-of-sight pursuit | every human winner |

Stock Forge is at or near zero on five of six axes. The Card-Forge wiki
concedes the same publicly ("best with Aggro and midrange, poor to ok in
control, pretty bad for most combo"), which means every competitor inherits a
*documented* ceiling they have accepted.

### Why this is a wedge and not a nice-to-have

Grim.Cards runs stock Forge AI, and their white paper discloses the
consequence: their win rates "are not predictions of how those decks would
perform at a table," and "Results describe AI engine behavior on the submitted
decklists." That disclaimer is their ceiling, and they state it because they
have no alternative. We are the only ones who have measurably moved it. The
answer to their disclaimer is a table of numbers.

### But the moat is the measurement apparatus, not the heuristics

Hand-tuned heuristics are a one-time engineering asset that a funded
competitor can match in months. The defensible asset is
`engine/humanness_scorecard.py` + the human reference corpus +
`training/behavior_bands.py` Wilson intervals. Without it, "our AI is more
human" is unfalsifiable marketing. With it, it is a citable table, and nobody
reproduces the table without building the corpus by hand.

**Therefore the 7-game corpus is the bottleneck on the moat, not the shim.**
`training/BEHAVIOR_CAPTURE.md` already establishes that 40 games gives ±4-5%
on split rate, "tight enough to say the agent is inside the human band as a
measurement, not a direction." Nearly every current claim in
`SIM_CALIBRATION.md` is annotated "n=8, direction only." The highest-leverage
work available is tallying games, and it is not code.

### The validation trap, stated plainly

**"More human-like" and "more predictive" are different claims, and only the
second one sells coaching.**

The scorecard measures behavioral resemblance. Customers buy predictive
validity: if the sim says 38%, do they win 38% at their table? Resemblance is
a plausible proxy, but behavior tallies cannot establish the link.

~~Evidence that this is already live: `SIM_CALIBRATION.md:80` records that the
agent **compressed the win-rate spread** (38/25/25/12 vs stock 67/17/17/0),
and the archetype baselines are consequently flagged as stale stock-AI numbers
"until re-measured under the agent at scale." The pilot improved and the
yardstick broke. There is currently no external ground truth to say which
spread is closer to reality.~~

**Corrected 2026-08-04.** That paragraph had two problems and both cut against
it as evidence.

1. It misquoted its own source. `38/25/25/12 vs 67/17/17/0` splices the v1
   *agent* tuple onto the v3 *stock* tuple from a different pod. The v1 line
   actually read `38/25/25/12 vs stock 38/38/12/12`.
2. The underlying claim has been retracted. Re-measured at `--clock 900` with
   the post-fix shim, 64 seat-rotated games per arm across all three pods, the
   pooled spread delta is **+3.7 pp (expansion), 95% CI -0.9 to +7.5** — the
   opposite sign from compression. It was never measurable in the first place:
   at n=8 with four decks, four *identical* decks average a 14.1 pp spread SD,
   larger than the claimed effect. See `SIM_CALIBRATION.md`, "Win-rate spread
   re-measured."

**This does not weaken the wedge argument; it sharpens this subsection's own
thesis.** The measured-gap table above is agent telemetry (splits, blocks,
mulligans, tutor casts, commander deploy timing) and is untouched by the
retraction. What is gone is the *outcome-level* number, and this subsection's
whole point was that resemblance and predictive validity are different claims.
The single outcome number in the repo turning out to be noise is that point
demonstrated rather than contradicted. The honest position is now unambiguous:
**we have measured that the agent behaves more like a human, and we have not yet
measured that it predicts better than stock.** Nothing should be sold on the
second claim until `studies/precon_correlation/` reports.

### The fix: Playgroup.gg's precon dataset is a ready-made validation set

This supersedes the §5 framing of Playgroup as purely a threat.

Their precon tier list is **66 stock precons across 10,982 tracked human
games**, with published inclusion thresholds (20+ games from 10+ distinct
pilots). Stock precons are a fixed, known 100 cards, so they convert to `.dck`
exactly via `engine/convert_decklist.py`. That gives a clean experiment:

1. Sim all 66 precons under stock Forge; correlate predicted against their
   observed human win rates.
2. Sim all 66 under agent v3; correlate again.
3. If agent v3's correlation beats stock Forge's, that is **proof of
   predictive validity** on an independent dataset we did not construct.

This is the single most credible thing this product could publish. It converts
the agent work from an internal quality claim into a public, contest-proof
result, and it reframes Playgroup from rival to referee. It also answers the
only question that matters commercially: why trust these win rates.

Sequence it *after* the corpus reaches ~40 games, so the behavioral claims and
the predictive claim land together.

### Consequences for asset protection

If the pilot is the advantage, the GPL boundary stops being hygiene and
becomes the asset-protection strategy. Task 07's rule ("if the Java file
contains strategy knowledge rather than plumbing, it's on the wrong side") is
now the most commercially important line in the repo, and the Stage 5 note
that "mechanisms live in the shim" deserves an audit. The line-of-sight gate
is a mechanism; **the policy governing when the gate opens is strategy.** If
that logic sits in Java it is GPL and it leaves with the shim.

An acquirer retargeting to Arena's rules engine discards the shim and keeps
`engine/deck_plan.py`, the personality and policy parameters, the human
corpus, and the scorecard. Invest accordingly.

### Revised ranking of what to build

1. Human corpus to ~40 games (unblocks every claim; not code)
2. Precon correlation study against Playgroup's data (the proof)
3. Shim strategy-leakage audit (protects the asset)
4. Re-measure archetype baselines under the agent (restores the yardstick)
5. Affiliate links (§6, unchanged — still the fastest revenue)

---

## 9. Corrected position after the pilot (2026-08-04)

The pilot cost 512 games and answered a question that mattered. Acting on it
requires no further simulation.

### Reposition the agent: from accuracy to believability

The claim "the humanized agent makes win rates more accurate" is unsupported.
The claim it should be replaced with is one the existing evidence already
carries: **the agent makes simulated games look like Magic.** Stock Forge splits
attacks 0% of the time, blocks 8-14%, keeps 7 cards in 97% of hands, and never
casts a tutor. Agent v3 sits inside or near human bands on all of those.

That is a **replay and coaching-credibility** value, not a prediction value:

- A user watching a replay where nobody ever blocks or splits attacks does not
  trust the tool, whatever the win rate says.
- Coaching that narrates plausible games reads as credible; coaching built on
  "swing at face and hope" does not.

This is defensible with data we already have, and it is worth real money in a
product whose flagship features are a replay theatre and a coaching report. It
is simply a different claim from "our numbers are more accurate," and the two
should stop being conflated.

### The differentiator is now the honesty layer, and it is cheap

The pilot produced measurements nobody else in this market has:

| finding | why it is a differentiator |
|---|---|
| Playgroup's tier list is **46% sampling noise** | Their per-deck error bars are wider than their tier boundaries |
| Stock Forge scores **Spearman 0.530** | Sim has *some* predictive validity — quantified, not asserted |
| Calibration slope **0.47** | Sim compresses roughly 2:1; a 30% sim result is not a 30% real result |
| Archetype bias **+30.2 pp creature vs +13.0 pp non-creature** | Forge's win rates partly measure AI pilotability, not deck strength |

Grim.Cards ships a 0-100 Power Score and a letter grade with no error bars.
Playgroup ships tier boundaries finer than their own noise. **We can ship every
number with a confidence interval and an archetype caveat, because we measured
them.** That position costs zero additional compute and is hard to copy without
repeating the work.

Note this also revises §2: "they run stock Forge" is *not* by itself the
competitive weakness claimed there, since stock Forge turns out to have real
predictive signal. The weakness is that they present it without error bars.

### Where the moat actually sits now, in order

1. **The corpus** (§4, unchanged). Still the exit asset, still being deleted.
2. **The measurement apparatus** (§8's surviving claim, now strengthened by the
   pilot). The scorecard, the human corpus, the ground-truth join, the
   pre-registered method.
3. **Coaching quality**, untested either way.
4. **The agent** — as a believability layer, not an accuracy layer.

### Do these, none of which need a sim run

1. **Affiliate links** on every coaching swap (§6). Still the fastest revenue
   and entirely independent of everything above.
2. **Persist the corpus** (§7.1). Still the exit asset; still discarded today.
3. **Ship the honesty layer**: confidence intervals and an archetype caveat on
   every displayed win rate, plus the compression note ("sim spread is about
   half of real spread"). `SIM_CALIBRATION.md` asserts these qualitatively; the
   pilot gives numbers.
4. **Stop conflating the two agent claims** in any doc or copy: resemblance is
   measured, predictive advantage is not.
5. **Consider publishing the pilot.** "What Forge-based simulation can and
   cannot tell you about a Commander deck, measured against 10,982 human games,
   including a null result about our own agent" is a credibility artifact
   Grim.Cards' white paper cannot match, and pre-registering then reporting a
   null against your own product is rare enough in this space to be a moat of
   its own. Share with Playgroup before publishing (§1 diplomacy note).

### Do not do these

- Do not rewrite or tune the agent on n=8. The finding is not that strong.
- Do not abandon the agent either. It is not disproven, and its believability
  value is separate and already evidenced.
- Do not launch the 168-264 hour full run to chase this. If the question ever
  matters commercially, fix the instrument and re-run the 8-deck pilot for
  ~6-8 hours first.

## Sources

- [About Grim.Cards](https://grim.cards/about) · [Grim.Cards](https://grim.cards/) · [Grim.Cards simulation case study, 2026-07-01](https://grim.cards/case-study/2026-07-01)
- [Playgroup.gg precon tier list and methodology](https://playgroup.gg/commander/precons) · [Playgroup Live](https://playgroup.gg/playgroup-live) · [Playgroup.gg legal](https://playgroup.gg/legal)
- [ManaTap.ai mulligan simulator](https://www.manatap.ai/tools/mulligan)
- [EDHREC about us](https://edhrec.com/about-us) · [EDHREC acquires Cardsphere](https://blog.cardsphere.com/edhrec-acquires-cardsphere/)
- [Moxfield Patreon estimates, Graphtreon](https://graphtreon.com/creator/moxfield) · [Moxfield Patreon stats](https://patreonstats.com/creator/moxfield) · [moxfield.com traffic, Similarweb](https://www.similarweb.com/website/moxfield.com/) · [edhrec.com traffic, Similarweb](https://www.similarweb.com/website/edhrec.com/)
- [Untapped.gg Premium](https://mtga.untapped.gg/premium) · [Untapped.gg company](https://untapped.gg/en/company)
- [GrimDeck deck builder comparison and pricing](https://grimdeck.com/blog/best-mtg-deck-builder-sites)
- [Hasbro to acquire D&D Beyond](https://investor.hasbro.com/news-releases/news-release-details/hasbro-acquire-dd-beyond-fandom) · [Forbes on the $146.3M price](https://www.forbes.com/sites/robwieland/2022/04/13/hasbro-acquires-dd-beyond-for-1463-million/)
- [eBay acquires TCGplayer](https://investors.ebayinc.com/investor-news/press-release-details/2022/eBay-Acquires-TCGplayer/default.aspx) · [TechCrunch, up to $295M](https://techcrunch.com/2022/08/22/ebay-acquiring-trading-card-marketplace-tcgplayer-295m)
- [Mobalytics profile and ESL FaceIt acquisition, Tracxn](https://tracxn.com/d/companies/mobalytics/__LuEwOUQusuEtwTUvqZyCoGtRJ23eHBU1_jkf12aXx9s) · [Mobalytics financials, Crunchbase](https://www.crunchbase.com/organization/mobalytics-2/company_financials)
- [TCGplayer affiliate program](https://docs.tcgplayer.com/docs/tcgplayer-affiliate-program) · [Commission details](https://getlasso.co/affiliate/tcgplayer/) · [AetherHub affiliate integration](https://aetherhub.com/Article/Updates-to-the-TCGPlayer-Affiliate-program)
- [Display ad RPM by niche, 2026](https://toolsignal.site/articles/blog-display-ad-rpm-by-niche-2026)
- [Magic FY2025 revenue $1.72B](https://www.gosugamers.net/entertainment/news/77968-magic-the-gathering-delivers-a-whopping-us-1-7-billion-year-as-hasbro-posts-major-revenue-growth) · [Hasbro Q4/FY2025 results](https://investor.hasbro.com/news-releases/news-release-details/hasbro-reports-fourth-quarter-and-full-year-2025-financial) · [Hasbro Q1 2026](https://marketchameleon.com/articles/b/2026/5/20/hasbro-q1-2026-magic-the-gathering-revenue-growth)
- [Forge headless sim mode, Card-Forge wiki](https://github.com/Card-Forge/forge/wiki/AI) · [Running AI vs AI headless](https://slightlymagic.net/forum/viewtopic.php?f=52&t=20283)
- [Wizards C&Ds Card Conjurer](https://techraptor.net/tabletop/news/wizards-cds-card-conjurer-causing-closure) · [WotC Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy)
- [Best deck testers, Draftsim](https://draftsim.com/mtg-deck-tester/) · [GTO Wizard pricing, PokerNews](https://www.pokernews.com/news/2026/03/gto-wizard-subscription-plans-new-features-pricing-50908.htm)
