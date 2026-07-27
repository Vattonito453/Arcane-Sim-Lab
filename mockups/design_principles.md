# Sim Lab — UI design principles (from research)

Research pass over published teardowns of acclaimed product UIs (Linear, Vercel/Geist,
Stripe), the Refactoring UI methodology, enterprise data-table guidelines, and the
"vibe-coded design tells" literature. This doc is the binding spec for all Sim Lab
front-end work. Sources at bottom.

## Part 1 — The AI tells (what outs a UI as generated)

Compiled from shadcn-sameness and vibe-coded-tells research. A page reading 4+ of
these gets flagged by people instantly:

1. Slate/zinc neutrals + Inter at default sizes + ~8px radius on everything (the
   raw-shadcn fingerprint)
2. Purple/indigo gradients, aurora glows, glassmorphism, bento grids
3. Stat-card banners — a strip of KPI cards each in its own rounded box with a
   green/red delta chip
4. Everything is a card: uniform rounded boxes, each with its own little header,
   all the same visual weight
5. Pill badges everywhere; colored left-borders on cards
6. All-caps letterspaced microlabels on every section
7. Emoji as icons; icon+label sidebar straight from a template
8. Serif-italic accent words; Space Grotesk/Instrument Serif combos
9. Centered hero + badge above H1 (marketing pages)
10. No prose anywhere — only chips, labels, and fragments. Real products write
    sentences.

**Audit of our v2 against this list:** hit #1 (Inter defaults, slate dark, 5–7px
radius), #3 (5-card stat strip with delta chips), #4 (six boxed modules), #5
(WIN/LOSS/OK/PART/COLD pills, evidence chips), #6 (uppercase microlabels), #7
(generic sidebar), #10 (no prose). That's 7 — hence "still has AI elements."

## Part 2 — What the best products actually do

**Linear** — near-achromatic; one accent used rarely (CTAs and active states only);
ultra-thin translucent borders rgba(255,255,255,.05–.08) instead of solid gray lines;
Inter but *tuned* (OpenType cv01/ss03, precise weights ~510/590); dark-by-default as
deliberate dev-tool positioning; keyboard-first.

**Vercel (Geist)** — the strictest grayscale ladder on the web (near-white/near-black
plus a ~200-step gray ramp; every border and disabled state is a deliberate step);
shadow-as-border (`box-shadow: 0 0 0 1px rgba(...)` rather than borders); monospaced
numerals for all data; layout is topbar + tab row + centered document flow with
sections separated by whitespace and hairlines — NOT a sidebar of card modules;
sentence-case labels; tiny text links (Feedback · Changelog · Help · Docs) in chrome.

**Stripe** — 3–4 primary numbers on the default view, not ten; "prioritization first,
explanation second, raw depth only when they ask"; leads with a written sentence about
your account, then data.

**Refactoring UI** — hierarchy via size/weight/color, not boxes; de-emphasize
secondary content instead of emphasizing primary; labels are supporting cast — merge
them into the value ("12 left in stock", not "In stock: 12"); constrained spacing
scale; use whitespace and rules to group, boxes only when functionally necessary.

**Data-table guidelines (enterprise)** — text left-aligned, numbers right-aligned in
mono/tabular figures; quiet headers (smaller, lower contrast, sentence case); compact
rows ~40px; generous horizontal padding; fixed context on scroll; density variance is
what makes tables read as real.

**Rauno Freiberg (Vercel) interface guidelines** — no extraneous animation on frequent
actions; interactions ≤200ms; hover states subtle and instant; details over decoration.

## Part 3 — The binding rules for Sim Lab v3+

1. **Layout:** topbar + tab row + centered content column (~1050px). Document flow.
   Sections divided by hairlines and whitespace. No boxed card modules; the only
   bordered container is a functional table.
2. **Color:** Geist-style grayscale ladder on near-black. Exactly one interactive
   accent (blue) for links/focus only. Green/red/amber appear ONLY as status
   text/dots, never as filled pills or chip backgrounds. No gradients anywhere.
3. **Type:** Inter tuned with cv01/ss03; weights 400/510/590; sizes 13/14 body, 24
   page title, 11.5 quiet labels in sentence case. All numerals in a monospaced face
   with tabular figures.
4. **Primary action:** inverted button (white on black in dark mode) — one per view.
   Everything else is a quiet bordered button or a text link.
5. **Numbers:** max 4 headline figures, set as plain type with hairline column
   dividers — no stat cards, no delta chips; deltas are written into the sentence.
6. **Prose:** every report leads with 1–2 written sentences (the coaching voice).
   Real products write; slop chips.
7. **Badges:** dot + word ("● Won") in status color. Zero pills unless functionally
   required (max one style per view).
8. **Icons:** few, stroke, 14–16px, never emoji. Prefer text links over icon buttons.
9. **Motion:** 120ms ease on hover/focus only. No entrance animations, no staggered
   reveals.
10. **Chrome authenticity:** breadcrumb path with tiny avatar, quiet utility links,
    real pagination ("Prev / 1 of 7 / Next"), timestamps ("Updated 21 min ago"),
    truncation with "+ n more". These small pieces of furniture are what real apps
    have and mockups fake.

## Sources

- https://freedesignmd.com/blog/shadcn-looks-generic
- https://shuffle.dev/blog/2026/01/why-do-most-ai-generated-websites-look-the-same/
- https://www.thefountaininstitute.com/blog/signs-vibe-coded-ui
- https://www.developersdigest.tech/blog/ai-design-slop-and-how-to-spot-it
- https://github.com/JCarterJohnson/vibecoded-design-tells
- https://www.925studios.co/blog/linear-design-breakdown-saas-ui-2026
- https://blog.logrocket.com/ux-design/linear-design/
- https://www.designsystems.one/design-systems/vercel-geist
- https://getdesign.md/vercel/design-md
- https://vercel.com/geist/introduction
- https://mattstromawn.com/projects/stripe-dashboard/
- https://www.sglavoie.com/posts/2023/09/09/book-summary-refactoring-ui/
- https://medium.com/design-bootcamp/top-20-key-points-from-refactoring-ui-by-adam-wathan-steve-schoger-d81042ac9802
- https://www.pencilandpaper.io/articles/ux-pattern-analysis-enterprise-data-tables
- https://www.setproduct.com/blog/data-table-ui-design
- https://rauno.me/craft/interaction-design
- https://sebastiandedeyne.com/rauno-web-interface-guidelines/
- https://evilmartians.com/chronicles/devs-in-mind-how-to-design-interfaces-for-developer-tools
