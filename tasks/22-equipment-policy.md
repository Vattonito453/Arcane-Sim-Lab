# Task 22: equip what you cast

## The finding (Vincent, 2026-08-29, run sim_20260829_220838_0966af5d0640)

Across all 8 games of a real user pod, Lightning Greaves was cast 9 times and
Swiftfoot Boots 11 times, and the Equip ability was activated **0 times**.
The only "equip" strings in the whole run are one trigger's reminder text.
Boots and Greaves are auto-includes in Commander precisely because attaching
them to your commander is basic play; a table where they sit unattached reads
as a bot instantly.

Equip decisions are stock Forge's (its EquipAi exists but demonstrably did
nothing here), and the plan agent has no equipment layer at all — this
dimension was missing from the 76-criterion rubric research too.

## The fix, respecting the boundary

Mechanism in the shim, knowledge as data:

- **Mechanism**: at second main on the agent's own turn, if an equipment it
  controls is unattached (or attached to a strictly worse body) and the equip
  cost is payable with mana to spare, attach it to the best eligible creature.
  "Best" = commander first, else highest plan weight, else biggest body.
  Legality and cost stay Forge's (`canPlay()` + `canPayCost`), same as every
  other override.
- **Data**: which equipment matters and what "worth equipping" means comes
  from plan weights (`deck_plan.py` already scores utility artifacts); an
  `equipiness` dial is NOT needed — this is play-to-win behavior, not
  personality.

## Acceptance

- On the same pod, Greaves/Boots attach within a turn of resolving in the
  large majority of games; zero illegal attachments (Forge adjudicates).
- Neutral observer or log-based count: equip activations per equipment cast,
  stock vs agent, reported like the blocking axes.
- No regression in the 8-game pod's runtime worth caring about (the scan is
  one pass over own battlefield at second main).
