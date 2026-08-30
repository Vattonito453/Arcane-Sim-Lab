# Task 23: attack the table's threat, not your grudge partner

## The finding (Vincent, 2026-08-29, run sim_20260829_220838_0966af5d0640)

Across 8 games, attack declarations received: Living Energy 49, Skrat 34,
Kilo 31, **Ur-Dragon 20** — and Ur-Dragon won 4 of 8. The scariest deck ate
the fewest attacks while pairs of decks ping-ponged each other (e.g. rot3
game 1: Living Energy -> Kilo x3, Kilo -> Living Energy x3, everyone else
also hitting Kilo). Vincent watched it live: "Kilo and Living Energy just
attack each other back and forth leaving Ur-Dragon and Skrat with way more
life than they should have."

Why the current layers cannot fix this:

- **Stock Forge picks attack targets**; the agent only re-aims in one narrow
  case (`kingmakerReaim`: stock aimed at the WEAKEST seat while a leader
  exists at >= 1.6x threat). It fired 4 times in 8 games.
- **Grudge makes it worse**: retaliation pressure (`grudgeWeight`) raises the
  threat score of whoever hit you, which is exactly the feud loop observed.
  Grudge is human-real, but humans break feuds when a third player is
  visibly winning; the agent has no mechanism for that.
- The agent's own documented standard (holdBackBlockers comment: "you attack
  ... when it is the table's real threat") is not met on the attack-target
  axis.

## The fix, respecting the boundary

Extend the existing re-aim from "rescue the weakest seat" to "aim at the
leader when the gap is decisive", still moving only legal attackers Forge
already declared:

- Mechanism: when `threatOf(leader) >= kingmakerRatio * threatOf(currentTarget)`
  (not just vs the weakest), move attackers that `canAttack(leader)` onto the
  leader, keeping any lethal-on-current-target attack intact (the
  attackIsLethal guard added in the QA pass).
- Data: the ratio is already plan data. Consider a `feudBreaker` clamp on
  grudge's share of threatOf (e.g. grudge contributes at most X% of a
  target's score) — also data.

## Measurement before shipping

Same discipline as blocking: mixed pods, neutral observation. New rubric
axis: **attacks-received rank vs threat rank** correlation (a human table's
top threat is its top target), plus win rate at n with power. The
attacks-received table above is the baseline: leader-last is the failure
signature.

## Status (2026-08-29): mechanism shipped, model gap identified

Implemented in simlab-forge-shim PR #10 (0.10.0): the re-aim now fires
whenever the leader out-threatens whoever stock targeted (any seat, not just
the weakest), lethal guard kept, `grudgeCap` wired as data (default off).

Validated, 16 games on the same pod vs a 16-game baseline on main:
- re-aims 14 -> 23 (original run: 0.5/game -> 1.44/game)
- win spread softened: Ur-Dragon 10/16 -> 8/16, Kilo 0 -> 2, Skrat 3 -> 5
- **residual, honestly**: Ur-Dragon is STILL least-attacked (34/216 vs
  40/232). The re-aim faithfully targets what the model calls the leader; the
  remaining defect is that `threatOf` scores board WIDTH (summed power), so a
  20-token swarm out-threats three huge dragons and the deck actually winning
  reads as low-threat.

Next lever is DATA, not mechanism: threat signatures in the deck plans
(deck_plan.py) should carry the quality/evasion story (commander on board,
flying fat, voltron pieces), and `grudgeCap` is available to stop feuds from
propping up threat scores. Tune, then re-measure attacks-received rank vs
final-standing rank on a powered run.
