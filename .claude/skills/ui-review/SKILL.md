---
name: ui-review
description: Self-review gate for any UI change in this repo (web/app/**, web/components/**, globals.css). Use BEFORE claiming a UI change is done and before opening a PR that touches the front end — it catches undiscoverable affordances, competing click targets, hover-only actions, and unverified interaction paths. Trigger on any task that adds or changes a page, a control, an overlay/popover/menu, or a click/hover/focus behavior.
---

# UI review gate

This exists because real failures shipped: an "open the deck" action hidden as
bare text inside a tile that otherwise selected the deck (Vincent: "nobody is
going to see that there"), a popover that flicker-looped on the leftmost
column, and a popover that pinned to the top of the document instead of the
viewport. All three were avoidable by asking the questions below.

`Design System/DESIGN_SYSTEM.md` is the visual contract and still binds. This
skill is about **interaction**: whether a real person can find and use the
thing.

---

## 1. The discoverability test (the one that matters most)

> **If explaining how to find an action requires a sentence, the affordance
> does not exist.**

For every action you added, answer in writing:

- **Where does a first-time user look for it?** If your answer is "they'd
  hover the tile" or "the name is clickable", stop — that's a fail.
- **Is there a visible, labeled control?** Text label beats icon-only. Icon
  alone is acceptable only for a universally-known glyph AND with an
  `aria-label`. Bare text styled like content is never a control.
- **Would it survive a screenshot?** If someone looked at a still image of
  the screen, could they point at the control? Hover-only reveals fail this,
  and they are dead on touch devices.

Concrete anti-patterns, all of which have shipped here at least once:

| Anti-pattern | Why it fails | Do instead |
|---|---|---|
| Text inside a clickable region is a different link | Two click targets, one invisible; users click the region and get the wrong action | Give the secondary action its own visible button, positioned away from the primary target |
| Action only appears on `:hover` | Undiscoverable; nonexistent on touch; invisible in screenshots | Render it always (dim it if it must recede) |
| Icon-only control for a non-obvious action | Users don't guess your metaphor | Icon **plus** a short text label |
| Relying on the user reading a `.note` to learn an interaction | Instructions are not affordances | Make the control self-evident; keep the note as reinforcement only |

## 2. Competing click targets

If a region has more than one action, write down the split explicitly:

- What does clicking the **body** of the region do?
- What is the **other** action, and what is its own control?
- Are they visually distinct and non-overlapping?
- Are they siblings in the DOM? **Never nest an interactive inside an
  interactive** (a `<Link>` inside a `<button>` is invalid HTML and produces
  unpredictable event behavior).

## 3. Overlays: popovers, menus, tooltips, dialogs

- **Portal to `document.body`.** Our glass panels use `backdrop-filter`, and a
  filtered ancestor captures `position: fixed` in some browsers — the overlay
  then anchors to the *document*, not the viewport, and scrolls out of view.
- **Anchor beside the trigger, never in a fixed slot** that can land under the
  cursor: opening under the pointer makes the container fire `mouseleave`,
  which unmounts the overlay, which re-fires `mouseenter` — an infinite
  flicker loop.
- **Flip and clamp at edges.** Test first/last column and row; clamp so the
  panel's real max-height fits the viewport.
- **Moving into the overlay must not dismiss it** (guard the container's
  `mouseleave` against `relatedTarget` inside the overlay).
- **Keyboard**: reachable on focus, dismissable with Escape.

## 4. Verification protocol (do this, don't assume)

Synthetic `dispatchEvent` calls are not verification — they bypass the real
hit-testing that produces these bugs.

1. Start this session's own preview (`preview_start`), never assume another
   session's server.
2. Use **real pointer actions** (`computer` hover/click). Screenshot
   coordinates are **scaled** from CSS pixels — compute `800 / innerWidth` and
   multiply; passing raw `getBoundingClientRect` values silently clicks the
   wrong element.
3. Confirm you hit the intended element: `document.elementFromPoint(x, y)`.
4. **Test the boundaries, not the happy path**: first and last column, first
   and last row, scrolled deep down the page, narrow viewport.
5. For overlays, sample presence over ~1.5 s to catch mount/unmount flicker:
   a stable string of `1`s, no `10` transitions.
6. Verify against **real data**, including the ugly cases: missing art,
   unresolved card facts, empty lists, long names.

## 5. Before you say "done"

- [ ] Walked the user's actual path start to finish with a real pointer
- [ ] Every action has a visible, labeled control (§1)
- [ ] Click-target split written down and non-overlapping (§2)
- [ ] Overlays portaled, anchored, flipped, clamped, Escape-dismissable (§3)
- [ ] Boundary cases tested (§4.4)
- [ ] Keyboard-only run-through of the primary flow
- [ ] One `.btn.pri` per view; tokens only, no hex; no new CSS file; inline
      styles only for computed values (DESIGN_SYSTEM.md)
- [ ] Screenshot attached to the report, showing the control the user must find

## 6. Reporting

Say what you verified and how ("real-pointer hover on the last-row tile while
scrolled 5000px down; 12/12 stability samples"), not that it "should work".
If you could not verify something, say which part and why — never imply
coverage you don't have.
