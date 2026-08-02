# Arcane Sim Lab — Design System (build spec)

Seed file for Claude Code. Canonical source: `Arcane_Sim_Lab_Design_System.md`.
Tokens live in `arcane-sim-lab.tokens.css`. **Never hardcode a hex — always use a token.**

Arcane Sim Lab is an automated playtesting, goldfish simulation and matchup
analytics platform for Magic: The Gathering Commander/EDH.

---

## Assets in this repo

| File | What it is |
|---|---|
| `arcane-sim-lab.tokens.css` | Tokens + primitives. Drop into `:root`. |
| `art/backdrop-hedron-ruins.png` | Default backdrop plate (1448×1086). |
| `art/backdrop-argent-spires.png` | Alternate daylit plate — splash only. |
| `Arcane Sim Lab Design System.dc.html` | Visual spec + canonical screen. |

Mascot and mana badges are **inline SVG**, defined in spec §2.2 and §5.1 — copy
the markup, don't export them to raster.

---

## 0. The five laws

1. **Arcane automation, not a dashboard.** High fantasy + scientific precision.
   Serif display over monospace data. If it looks like a generic SaaS admin panel, it's wrong.
2. **Glass floats over art.** Content sits on frosted panels above the Dominaria
   backdrop — never directly on the artwork. Legibility beats atmosphere every time.
3. **Cyan is interaction. Violet is secondary. WUBRG is data.**
   A colour never means two things at once. See §3.
4. **Glow is a state, not decoration.** `--glow-cyan` marks the primary action and
   live activity. Nothing else glows.
5. **Fixes subtract.** If a problem seems to need a new decorated component,
   the component is the problem.

---

## 1. Type

| Role | Token | Spec |
|---|---|---|
| Logo / wordmark | `--font-display` Cinzel | 28px, 700, uppercase, `.08em` |
| Page prompt | `--font-ui` | 22px, 400 |
| Section header | `--font-ui` **(sans, not serif)** | 19px, 600 |
| CTA / button | `--font-ui` Space Grotesk | 18px, 700, uppercase, 2 lines |
| Body | `--font-ui` | 15px / 1.65 |
| Data, tallies, % , timestamps | `--font-data` JetBrains Mono | 13px, 400 |
| Meta / caption | `--font-ui` | 12px / 1.55 |
| Eyebrow | `--font-data` | 11px, uppercase, `.16em` |

**Cinzel appears exactly once per page — the wordmark.** Everything else is Space
Grotesk; one serif moment keeps it ceremonial. Figures inside prose are weight-600,
not a different family. Mono is for detail views (run ids, filenames, hex values),
not the home screen.

### Punctuation in copy

**No em dash (`—`) in anything a user reads.** Pick the mark that says what the
dash was vaguely gesturing at:

| The dash was joining | Use | Example |
|---|---|---|
| two independent clauses | a period | `The engine refused the run. Is another simulation in progress?` |
| a claim and its explanation | a colon | `Not covered: the retrieved excerpts don't reach this question` |
| two tightly coupled clauses | a semicolon | `Assembled, never fired; win rate is a floor` |
| an aside to the main clause | parentheses | `top win rate (Ur-Dragon B3)` |

An em dash is almost always a decision the writer declined to make, and a
screen reader gives it no useful pause. Forcing the choice makes the sentence
say what it means.

**Empty values use an en dash (`–`), not an em dash.** A table cell or headline
figure with no value shows `–`. That is the conventional mark for "no data" and
it is visually distinct from the minus sign and from a hyphen.

**Scope is everything a user can read**: JSX text, string literals, `aria-label`,
`title`, `placeholder`, page metadata, and any engine string that reaches the
UI (error messages, the archetype "why" sentences).

**Two exemptions.** Card text from Scryfall keeps its em dashes verbatim, because
it is Wizards' printed text shown under the Fan Content Policy and rewriting it
would be false: `Legendary Creature — Phyrexian Angel Horror`, `Choose one —`.
Code comments and repo docs are not copy and are unaffected.

---

## 2. Ink & contrast (WCAG 2.2 AA — non-negotiable)

| Token | Hex | Ratio on `--bg-void` | Use |
|---|---|---|---|
| `--ink-max` | `#FFFFFF` | 19.3:1 | Winner, leader, emphasis |
| `--ink-1` | `#E6EDF3` | 15.1:1 | Headings |
| `--ink-2` | `#C3CEDA` | 10.8:1 | Rows, body |
| `--ink-3` | `#A9B7C6` | 9.0:1 | Sim subtext, "most run" |
| `--ink-4` | `#7A8899` | 4.9:1 | **Floor.** Footer, disclaimer |
| `--ink-on-fill` | `#0B1418` | 11.4:1 | Label past ~60% of a fill (bright end) |

**The fill carries its own scrim.** `--winrate-fill` holds deep teal for a fixed
`--label-budget` (165px) before ramping to bright cyan. **The stops are absolute,
never percentages** — a percentage dark zone scales with the bar and slides out
from under the label on short rows, which is exactly how this component breaks.
Deck name and runs count sit inside that 165px, take `--text-shadow-on-fill`, and
truncate with an ellipsis rather than running onto the bright end. Use
`--winrate-fill-bare` for any bar that carries no label (progress tracks).

Nothing dimmer than `--ink-4` may carry text — dimmer greys are hairlines only.
The Fan Content disclaimer and Scryfall credit are legal obligations: they render
at `--ink-4`, never below.

**On glass** (`--panel-glass` over scrimmed artwork) all ratios improve slightly;
still measure against `--bg-void` as the worst case.

---

## 3. Colour rules

**Interaction (UI only)**
- `--mana-cyan #00E5FF` — primary CTA, focus ring, active nav, live/running state
- `--arcane-violet #A855F7` — secondary accent, panel highlights, analytics affordances
- Violet as **text** must use `--arcane-violet-ink #C89BFA` (7.4:1). Raw `#A855F7`
  is 4.8:1 — acceptable for large text and borders, not for 12px metadata.

**Identity (data only)** — `--color-sun / water / skull / fire / tree`.
Permitted on: deck rows, pod seats, card metadata, filters.
Forbidden on: buttons, links, focus states, progress bars, status dots.

> ⚠️ **Blue and black pips sit near the UI accents.** `--pip-b` shares a hex with
> `--arcane-violet`, and `--pip-u` is a near neighbour of `--mana-cyan`. They are
> disambiguated by **form, not hue**: a pip is always a disc with an inset
> silhouette (§4); interaction is always a control surface, border or glow.
> Never place a pip inside a button.

**Rarity** — `--rarity-common/uncommon/rare/mythic`. Card-level accents only.
Note `--rarity-rare` shares a hex with `--color-sun`; rarity appears only on card
tiles, identity only on deck rows, so they never co-occur.

**Colour is never the only channel.** Winner = brightest ink + column position.
Status = dot *shape* (§7). Identity = glyph *shape* + colour.

---

## 4. Mana pips (IP-safe)

WotC mana symbols are **prohibited**. Do not use official mana circles, and do not
use emoji — they render inconsistently and read as unserious. Each pip is a
**filled disc with a distinct inset silhouette**, so identity survives greyscale
and colourblindness. Disc colour alone never carries meaning.

| Colour | Disc | Core | Silhouette |
|---|---|---|---|
| White (W) | `--pip-w #F5E9C8` | `--pip-w-core` | Gold core |
| Blue (U) | `--pip-u #67B7E8` | `--pip-u-core` | Teardrop |
| Black (B) | `--pip-b #A855F7` | `--pip-b-core` | Void core |
| Red (R) | `--pip-r #EF4444` | `--pip-r-core` | Flame |
| Green (G) | `--pip-g #10B981` | `--pip-g-core` | Tree |

Markup is the inline SVG in spec §5.1 — a ringed disc (dark fill, coloured
1.5px stroke) with the silhouette inset. `.mana-badge--inline` 18px beside a
deck name, `.mana-badge--seat` 20px in a sim seat strip, gap 4–6px, always
WUBRG order. Do not recolour by CSS; do not substitute emoji or a WotC mana
circle. Pips are data — **never place one inside a button.**

---

## 5. Layout

- Page max width `--max-width 1280px`, gutter `--gutter 40px`
- **Full-bleed artwork behind everything** (see §11). **No text on bare art.**
- Mascot sits above the wordmark, centred; the pair anchors the upper third
- Two-column data area: `1fr 1fr`, gap 40px, both columns on ONE glass panel
- Deck rows `--row-h 64px`; action buttons `--action-h 78px`; controls 44px
- Narrow breakpoint 390px: columns stack, CTAs go full-width in a vertical stack,
  tally banner scrolls horizontally with snap

**Page order (home):** header + mascot → rolling tally banner → "What would you like
to do today?" + action hub → two-column data panel → media block → footer.

---

## 6. Components

### Masthead
Mascot seated **directly above** the `ARCANE SIM LAB` wordmark, upper-centre —
not beside it. The two form one locked brand unit; no sub-title beneath.
Mascot: the inline SVG in spec §2.2 — cheerful brass-and-bronze artifact robot,
seated, holding a fan of three cards, cyan visor and a dashed arcane aura ring.
Rendered at 200px with `.masthead-robot-mascot`. Ship it as inline SVG, never a
raster export, so the brass gradient and glow stay crisp at any density. Account widget top-right as a translucent
pill: avatar + name + chevron, `--r-control`, 44px tall.

### Rolling tally banner
`--bar-instrument`, `--r-action`, 1px `--hairline-strong` border, hairline
dividers between cells. Counters are **inline, not stacked**: a 34px rounded icon
badge, then "**52,365** decks tested" on one line (figure 17px/600 `--ink-max`,
label 16px/400 `--ink-1`).

**Calculators & Tools notch** — a tab hanging off the banner's bottom edge:
same fill and border, `border-top: none`, `border-radius: 0 0 10px 10px`,
flanked left and right by hairlines fading to transparent. Easy to miss; it is
part of the banner, not a separate nav.
Numbers roll on load over `--dur-tally`, easing out. **Respect
`prefers-reduced-motion`** — render the final value immediately.
Wrap in `aria-live="off"`; the rolling animation must not be announced.

### Action hub
Four `.action-btn` of **equal footprint** (78px tall, 18px uppercase, 26px icon
left). Only border colour and glow rank them; labels wrap to two lines rather
than shrinking, so the row reads as one instrument panel.
1. `RUN NEW SIMULATION` — `.action-btn--primary`, bolt, cyan glow
2. `SIM HISTORY & ANALYTICS` — `.action-btn--violet`, bar chart
3. `IMPORT DECK` — `.action-btn--blue`, download
4. `EXPLORE DECKLISTS` — `.action-btn--neutral`, magnifier

The primary carries its cost estimate beneath it ("two decks ≈ 5 s · four ≈ 8 min").
**Never disable the primary.** Keep it live and state the blocker beside it:
"Pick at least 2 decks — you have 1."

### Data panel
One glass sheet (`--panel-glass`, `--panel-blur`, `--r-panel`) holding both
columns. **Panels never nest** — rows inside use `--row-ground`, not a second panel.

- **Top decklists** — `.deck-row`, 64px tall, 8px gap. Grid `52px 1fr 60px`:
  hatched thumbnail flush to the left edge with matching corner radius; then the
  body, which carries **the win-rate fill as its background** (width = win %,
  `--r-fill`) with the deck name + pips on top and the runs count beneath, both
  in the normal ink ramp plus `--text-shadow-on-fill`; then the percentage
  right-aligned in a fixed 60px column
  **outside** the fill, so the figures stack readably however long the bars run.
- **Most recent sims** — hairline-separated, no row fill. Title (16px,
  `--ink-max`), then `winner + win% · games · age` (14px, `--ink-3`, winner
  phrase bolded to `--ink-1`), then a seat strip of 17px pips.
  Whole row is the link; no repeated "Watch" column.

### Media block
Full-width white display-ad container anchored above the footer, `--r-panel`,
`--sp-5` clear on all sides. Labelled `Advertisement` at `--size-eyebrow` / `--ink-4`.
Intentionally isolated from the dark UI. Never inside a glass panel.

---

## 11. Background imagery

**Art direction.** High-fantasy Dominaria: ancient moss-covered stone archways and
ruins, floating diamond hedron monoliths drifting through an atmospheric sky,
subtle blue-violet mana leylines in the clouds. Cool slate blue, deep emerald
moss, warm cyan/violet horizon glow. 16:9, twilight, epic and still. The art is a
stage, never a subject — **keep the upper third uncluttered**, horizon in the
lower third; the masthead and mascot land above it.

**Three-layer stack, always in this order:**

1. `--atmosphere` + `--atmosphere-leylines` — twilight sky gradient beneath the
   art, so a failed image load still reads as sky rather than a black rectangle
2. The art itself — `art/backdrop-hedron-ruins.png` (1448×1086),
   `object-fit: cover`, `object-position: 50% 0`. Painted to this spec: floating
   hedrons rim-lit from the horizon, ruin arches at both edges, standing stones
   receding to a warm horizon, moss, leyline wisps, film grain. Its upper third
   is deliberately quiet and its base falls to near-black.
3. `--backdrop-scrim` (linear, light at sky → heavy at base) then
   `--backdrop-vignette` (radial, `rgba(13,15,18,.60)` at the edges)

**Plate library.** Two plates ship; both are 1448×1086 and both are cropped by
`object-fit: cover`, so compose to the centre, never to the corners.

| Plate | Token | Use |
|---|---|---|
| `backdrop-hedron-ruins.png` | `--backdrop-art` | **Default, all app screens.** Storm-lit ruins, violet-cyan hedrons, near-black base — the masthead sits in the quiet centre sky. |
| `backdrop-argent-spires.png` | `--backdrop-art-alt` | **Splash and marketing only.** Daylit capital. Bright and busy at every height, so it must be paired with `.backdrop--bright` (heavy scrim + `saturate(72%) brightness(84%)`). Never behind data. |

Use the `.backdrop` primitive — it composes all of it. At app root use
`.backdrop .backdrop--app`, which is position-fixed so the scene holds still as
the page scrolls. Content panels on top take `.glass-panel` (`--panel-glass` at
0.85, `--panel-blur` 12px, `--panel-border`).

> **Superseding source spec §3.2.** The written spec hardcodes
> `background-image: url('https://images.unsplash.com/photo-1518709268805-…')` on
> `body, .app-root`. **Do not use it.** Three reasons: the photo is woodland, not
> Dominaria ruins; an external hotlink breaks offline rendering and can rot; and
> Unsplash's terms require visible photographer attribution, for which that rule
> provides no slot. Ship `art/backdrop-hedron-ruins.png` instead.
>
> `background-attachment: fixed` from the same rule is also dropped — it is
> unreliable on iOS Safari and forces full-viewport repaints on scroll.
> `.backdrop--app` gets the same locked-scene effect with `position: fixed`.

**Generation prompt:**

> High-fantasy landscape of ancient overgrown stone ruins on Dominaria, floating
> diamond monoliths in the sky, mystical mana leyline energy swirling in clouds,
> twilight lighting, epic atmospheric mood, dark fantasy UI background style
> --ar 16:9 --v 6.0

---

## 7. Status & progress — shape, not hue

| State | Mark | Colour |
|---|---|---|
| Running | Filled circle + cyan glow | `--state-running` |
| Queued | Hollow circle, 1px stroke | `--state-queued` |
| Done | Filled square | `--state-done` |
| Failed | Filled circle | `--state-failed` |

Distinguishable with no colour vision at all.

- A **queued** job draws no progress bar it doesn't have — dashed track, no fill.
- Any wait over 10 s shows a live estimate and an escape route ("notify me instead").
  Four decks over sixteen games is 8–14 minutes and must never look instant.
- Completion swaps the page header **in place** and announces via `aria-live="polite"`.
  The page never grows a second heading beneath itself.

---

## 8. Accessibility contract

| Criterion | Rule |
|---|---|
| 1.4.3 | All text ≥ 4.9:1. `--ink-4` is the floor. |
| 1.4.1 | No meaning by hue alone — winner is position + brightness, status is shape. |
| 1.4.11 | Glass borders and control edges ≥ 3:1 against their backdrop. |
| 2.4.7 | 2px `--mana-cyan` focus ring at 2px offset on every focusable element. |
| 2.5.8 | 56px rows, 44px controls — past the 24px floor and 44px platform guidance. |
| 3.3.2 | Every field has a persistent visible label. Placeholder is a format hint only. |
| 4.1.3 | Run completion announced via live region. |
| 2.3.3 | Rolling tallies and glow pulses honour `prefers-reduced-motion`. |

---

## 9. Compliance (WotC Fan Content Policy)

- No official mana symbols — geometric glyphs only (§4)
- No "Magic: The Gathering" or "Planeswalker" branding in chrome
- Card images via Scryfall, hotlinked, attributed
- Footer disclaimer, always present, `--ink-4` minimum:
  > Sim Lab is unofficial Fan Content permitted under the Wizards of the Coast
  > Fan Content Policy. Card images via Scryfall. 3,152 rules · 262 keywords.

---

## 10. Do not

- Hardcode hexes — use tokens
- Put an identity dot inside a button, or cyan/violet on a data row
- Use emoji as UI (mana dots, status, section markers)
- Use a colour as the only carrier of meaning
- Disable a primary button without saying why
- Draw a progress bar for a queued job
- Put body text below `--ink-4`
- Set Cinzel on anything but the wordmark
- Put an em dash in copy — use a period, colon, semicolon or parentheses (§1).
  Scryfall card text is the only exemption
- Use an em dash for an empty value; that is an en dash (`–`)
- Give `--winrate-fill` percentage stops — the dark zone must be absolute
- Brighten the first stop of `--winrate-fill` — it is load-bearing for legibility
- Let a deck name or runs count exceed `--label-budget` without truncating
- Place text on unscrimmed artwork
- Ship art without both the scrim and the vignette
- Use a backdrop with a busy upper third — the masthead needs quiet sky
- Glow anything that is not the primary action or a live job
- Add a gradient outside `--winrate-fill`
- Nest a panel inside a panel — glass sheets do not stack
