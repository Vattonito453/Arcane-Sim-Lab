# cEDH holdout: the draw

*Drawn 2026-09-26, before any template, tier, band or override work, as the
repair plan requires (`tasks/25-repair-plan.md` §2.2, §3.0, WS0 task 2,
Appendix B task 4). This file is committed on its own so that its parent
commit, which seeds the lot, was fixed before the result was known.*

## The draw

**Holdout pods: `Bq-nFi0f1jA` and `CxKMqO36DdM`.**

| Pod | Decks (`studies/human_ceiling/decks/<pod>/`) |
|---|---|
| `Bq-nFi0f1jA` | cabbage_merchant, kinnan, rog_thrasios, yidris |
| `CxKMqO36DdM` | alan_tnt, dallas_bluefarm, joseph_ral, sterling_bluefarm |

The two eligible pods not drawn, `B421mac67IE` and `sZA0KqXCGrY`, join
cEDH-dev with `5A6o18Bra0Y` and `OuY6mdiXbHU`.

## The rule

1. **Candidates.** `studies/human_ceiling` has 8 pods. A holdout pod must
   share no deck with cEDH-A and must not be used by the scenario suite:
   - `n7WpsqsZtdQ` and `2iA_Jt0d6sM` are cEDH-A;
   - `5A6o18Bra0Y` shares rog_ishai with `n7WpsqsZtdQ`;
   - `OuY6mdiXbHU` is scenario S1 (Kiki-Jiki + Zealous Conscripts).

   That leaves 4 eligible pods: `B421mac67IE`, `Bq-nFi0f1jA`, `CxKMqO36DdM`,
   `sZA0KqXCGrY`.
2. **The lot.** Draw 2 of the 4 with Python's `random.Random`, seeded with the
   40-hex commit hash of this file's parent commit read as one integer, and
   `sample(sorted(pods), 2)`.
3. **Discipline until G3 (Mon 2027-01-11).**
   - No template, tier, band, override, threshold or target is tuned on these
     two pods, and no AI experiment runs on them. WS8 targets are computed on
     dev decks only.
   - Nobody reads their per-deck sim results before G3.
   - At G-lines (Thu 2026-11-19) their lines are scored blind, once, with the
     classification frozen for G3. That is a static check; no games.
   - Allowed before G3, because it changes what the decks are rather than how
     the pilot is tuned: input-fidelity fixes applied to every study deck (the
     week-2 DFC regeneration, Appendix B task 17), and E7's fidelity read on
     the Ral decks, which records only whether the commander was cast
     (critique item 10).
4. **At G3.** The holdout runs beside cEDH-dev, all plan seats, 16 games per
   pod, and is reported side by side with dev. It must yield at least 30
   assembled drivable lines. If it does not, play 16 more games per pod, up to
   64. If it is still short, Vincent's 8 fresh cEDH lists become a second
   holdout (decision 14).

## Reproduce it

Seed (this file's parent commit):
`d4597a05db72223090b8751304a1d71edc5d00b7`

```
py -c "import random; pods=['B421mac67IE','Bq-nFi0f1jA','CxKMqO36DdM','sZA0KqXCGrY']; print(random.Random(int('d4597a05db72223090b8751304a1d71edc5d00b7',16)).sample(sorted(pods),2))"
```

Output on the dev box (Python 3.8.2): `['Bq-nFi0f1jA', 'CxKMqO36DdM']`.
Integer seeding and list sampling have been stable across Python 3 releases;
if a later version ever prints something else, this recorded 3.8.2 result is
the draw.

To confirm the seed is this file's parent, run
`git log --diff-filter=A --format="%H %P" -- studies/holdout/HOLDOUT.md`: it
prints the commit that added this file, then its parent, and the parent must
equal the seed above.

**SHA-256 of the pods list:**
`15487daf4862b55cd3a3ef0b42f67d9c3dcc0a0b2a59c1e7c42724fcfb93161f`, the hash
of the four eligible pod ids, sorted, joined by a single newline with no
trailing newline, as UTF-8:

```
py -c "import hashlib; pods=['B421mac67IE','Bq-nFi0f1jA','CxKMqO36DdM','sZA0KqXCGrY']; print(hashlib.sha256(chr(10).join(sorted(pods)).encode('utf-8')).hexdigest())"
```

## Caveats found while drawing

The eligibility rule checks overlap with cEDH-A and the scenario suite, not
with cEDH-dev. Both drawn pods share one byte-identical decklist with a dev
pod:

- `Bq-nFi0f1jA/cabbage_merchant` is the same list as
  `5A6o18Bra0Y/cabbage_merchant` (dev).
- `CxKMqO36DdM/joseph_ral` is the same list as `sZA0KqXCGrY/joseph_ral`
  (dev), and the same deck E7 reads in week 2.

So 2 of the 8 holdout seats are decks the dev bed will see. The draw stands
as drawn; redrawing after seeing the result would defeat the lot. The
proposal for G3 is to report holdout figures per deck, and the pooled holdout
figures both with and without those two seats. That choice belongs to Vincent
and is listed as an open question in the week-1 report.

Two fidelity notes from `studies/human_ceiling/RESULTS.md` and its manifest
also apply: the kinnan seat in `Bq-nFi0f1jA` is a different build from the one
the human played, and dallas_bluefarm's list has drifted from the streamed one
(Jeska's Will and Harnfel are missing). Neither matters for a sim-only holdout,
but neither list is a faithful copy of the human game.
