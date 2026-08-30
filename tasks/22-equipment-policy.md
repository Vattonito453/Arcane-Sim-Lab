# Task 22: equipment — premise retracted, replaced by what measurement found

## Retraction (2026-08-29, same day)

The original version of this task claimed Greaves/Boots were "cast 20 times,
equipped 0 times" across Vincent's run. **That was a detection artifact in my
scan, not a Forge behavior.** Forge logs an equip as
`activated Lightning Greaves targeting [...]` and `Attach to <creature>`; the
scan looked for the word "Equip", which never appears in log text. Measured
correctly on the same run: Greaves cast 3 and activated 6 times, Boots cast 4
and activated 7, 19 attach resolutions overall. **Stock Forge equips.**

A shim mechanism was built against the false premise, validated on 16 games,
and dropped: it attached nothing (Forge's `canPlay()` embeds the stock AI's
own attach-willingness, so the gate inherited the reluctance it was meant to
bypass) except an occasional Skullclamp when stock idled. Not shipped.

## What is actually true, measured

1. **Stock's equip targets are mostly defensible.** Boots went to Saheeli
   (the commander) twice, Greaves to Kappa Cannoneer; of 15 sampled attaches
   3-4 were questionable (Greaves on a Shapeshifter Token, Curator's Ward on
   an Arcane Signet). A target-quality nudge is a MINOR gap, not the crater
   the original task described.
2. **The replay never renders attachments.** The board reconstruction shows
   the equipment card sitting in the artifact row whether or not it is
   attached, so equipped Boots LOOK unused. This is almost certainly what
   Vincent observed and it misleads every replay with equipment in it.

## The real task (UI, needs Vincent's go-ahead: UX-facing)

Show attach state in the replay board: the `Attach to X (id)` /
`activated ... targeting [...]` resolutions carry everything needed to fold
an `attachedTo` field into the board state (web/lib/replay.ts), and the
tabletop can badge the equipment or nest it under its creature. Until then,
equipment play is invisible to the person judging the agent.

## Lesson recorded

Before filing a behavioral gap against the agent, verify the DETECTOR against
one positive example. "Zero occurrences" of something the log spells
differently is the same trap as the em-dash grep and the `"rec": "result"`
spacing bug, and this is the third time it has cost a build.
