# Reader instructions: knockout and turning-point audit

*Part of the pre-registration (`PREREG.md` in this folder). Each reader gets
this text, a batch manifest and the evidence files the manifest lists, and
nothing else.*

You are reading replays of simulated four-player Commander games played by
Forge, an open-source Magic: The Gathering rules engine. Forge adjudicated
every game, so the log is the record of what happened. Your readings will be
compared with other readings; work independently and read carefully.

## What you may use

- Only the evidence files named in your batch manifest.
- Do not open any other file, the repository, the web, any API or any other
  tool output. Do not look for, or ask for, anyone else's reading of these
  games. If an evidence file seems to contain an answer (a stated cause,
  killer or turning point from some tool), stop and report it instead of using
  it.

## What an evidence file holds

1. A header: the game key, the seats as Forge prints them, and notes on what
   the log records.
2. Forge's log in order. Each turn starts with a header giving Forge's turn
   number and the active player. Each event line shows the step it happened in
   and Forge's text for it. Card names carry Forge's instance number in
   parentheses, for example `Goblin Token (412)`.
3. A per-turn digest computed mechanically from the log: spells cast, damage
   dealt to players, life and poison totals as logged, creatures entering and
   leaving the battlefield, and Forge's elimination lines. It is a reading aid;
   the log is authoritative. The header says how complete the creature lists
   are.

Forge prints its end-of-game outcome lines ("X has lost because ...") for every
player at the very end of the game, so their position does not date a
knockout. The outcome block also starts with a "Turn N" line of its own that
does not use the turn numbering of the headers; always use the header numbers.

## Task 1: every elimination

For every player Forge records as having lost (every "has lost" line), give:

- **player**: exactly as printed, for example `Ai(3)-Stella Lee, Wild Card`.
- **turn**: the header turn number of the event that put the player out of the
  game: for a life loss, the damage or loss that took their life from above 0
  to 0 or below; for poison, the counters that took them to 10 or more; for
  commander damage, the hit that took one commander's total to 21 or more;
  for an alternate win, the winning spell or ability resolving; for a
  deck-out, the draw from an empty library. Check it: a player who is out
  takes no later turns.
- **cause**: one of the classes below. Start from Forge's reason in the
  "has lost" line, then read the log for the event that crossed the threshold:

  | cause | when |
  |---|---|
  | `combat_damage` | Forge: "life total reached 0", and combat damage took their life to 0 or below |
  | `noncombat_damage` | Forge: "life total reached 0", and damage from a spell or ability outside combat (burn, fight, a damage trigger) took it there |
  | `life_loss` | Forge: "life total reached 0", and life loss that is not damage took it there (a drain such as "each opponent loses 1 life", paying life) |
  | `life_total` | Forge: "life total reached 0", but the log shows no event that took it there |
  | `poison` | Forge: "obtaining 10 poison counters" |
  | `commander_damage` | Forge: "accumulation of 21 damage from generals" (21 combat damage from one commander) |
  | `alt_win` | Forge: "an opponent has won by spell '...'" (a card's "you win the game") |
  | `lose_effect` | a card's own "you lose the game" effect, for example an unpaid Pact |
  | `deckout` | Forge: "trying to draw cards from empty library" |
  | `concession` | the player conceded |
  | `unknown` | none of the above fits |

- **killer**: the seat, as printed, that controlled the card or ability whose
  damage, life loss, poison or winning effect put the player out. For combat
  damage, the attacking player. For a player's own card (life they paid, their
  own Pact), the player themselves. `null` for a deck-out or a concession, or
  when the log cannot tell.
- **card**: the card most responsible, named as printed without the instance
  number. Combat or poison: the source that dealt that player the most in the
  lethal damage step (on a tie, the first one listed). Commander damage: the
  commander. Alternate win: the winning card. Burn or drain: the source of the
  lethal damage or loss. `null` for a deck-out or concession.
- **confidence**: `high`, `medium` or `low`, and a one-line **note** if
  anything was unclear.

## Task 2: the turning point (only where the manifest says "turning point requested")

Read the whole game first. Then name the turning point: the one turn on which
the game swung decisively toward the player who eventually won it. It can be
any player's turn, and it can be the final turn if nothing earlier decided the
game. Give:

- **turn**: the header turn number;
- **card**: the card most responsible for the swing, named as printed without
  the instance number, or the word `combat` when an attack as a whole did it;
- **reason**: one sentence;
- **confidence**: `high`, `medium` or `low`.

## Output

Write one JSON file (the manifest names its path), shaped like this:

```json
{
  "reader": "A1",
  "games": [
    {
      "game": "X-g01",
      "eliminations": [
        {"player": "Ai(1)-...", "turn": 31, "cause": "combat_damage",
         "killer": "Ai(3)-...", "card": "...", "confidence": "high", "note": ""}
      ],
      "turning_point": {"turn": 22, "card": "...", "reason": "...", "confidence": "medium"}
    }
  ]
}
```

Use `"turning_point": null` for games where it is not requested. Report every
game in your manifest, and every "has lost" line in each game.
