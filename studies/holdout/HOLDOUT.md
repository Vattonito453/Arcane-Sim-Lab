# cEDH holdout: the draw

*Drawn 2026-09-26, before any template, tier, band or override work, as the
repair plan requires (`tasks/25-repair-plan.md` §2.2, §3.0, WS0 task 2,
Appendix B task 4). This file was first committed on its own, in the draw
commit `1f8e52d` on `repair/week1`, so that the parent of that commit, which
seeds the lot, was fixed before the result was known. See "Reproduce it" for
how to check that on main, where the file arrived through a squash merge.*

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
   `sample(sorted(pods), 2)`. "This file's parent commit" means the parent
   of the commit that first added this file, the draw commit `1f8e52d`; on
   main the file arrived later through a squash merge (see "Reproduce it").
3. **Discipline until G3 (Mon 2027-01-11).**
   - No template, tier, band, override, threshold or target is tuned on these
     two pods, and no AI experiment runs on them. WS8 targets are computed on
     dev decks only.
   - Nobody reads their per-deck sim results before G3. This is
     forward-looking: evidence produced before the draw already covers these
     pods (the August 2026 stock runs in `studies/human_ceiling/RESULTS.md`,
     the behavior_rubric shipping runs, and the diagnosis's corpus-wide
     counts over all 32 decks). None of it may be used to tune anything
     either.
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
5. **How G3 reports it** (Vincent's decision, 2026-09-27). Every holdout
   figure is reported three ways, and all three appear in the G3 write-up:
   - **per deck**, for each of the 8 holdout seats;
   - **pooled over all 8 seats**;
   - **pooled over the 6 seats that are not dev duplicates**, leaving out
     the two seats whose decklists are byte-identical to cEDH-dev decks:

     | Holdout seat | Byte-identical dev deck |
     |---|---|
     | `Bq-nFi0f1jA/cabbage_merchant` | `5A6o18Bra0Y/cabbage_merchant` |
     | `CxKMqO36DdM/joseph_ral` | `sZA0KqXCGrY/joseph_ral` |

   Both the decklist text (`<pod>/<deck>.txt`) and the converted
   `<pod>/dck/<deck>.dck` compare byte-identical (`cmp`, 2026-09-27).

   This is a reporting rule, not a new draw and not a new gate. The holdout
   is still `Bq-nFi0f1jA` and `CxKMqO36DdM`, all 8 seats play, and the three
   views are cut from the same games. Rule 4 is unchanged by this decision,
   which covered reporting only: its 30-line floor is read on the holdout
   as drawn (all 8 seats), and the write-up gives the 6-seat count beside
   it. Whether the floor should count only the 6 is an open question for
   Vincent, not settled here. Where the two pools would read differently
   against a target, the write-up shows both and says so rather than
   picking one.

## Reproduce it

Seed (the parent of the draw commit `1f8e52d`):
`d4597a05db72223090b8751304a1d71edc5d00b7`

```
py -c "import random; pods=['B421mac67IE','Bq-nFi0f1jA','CxKMqO36DdM','sZA0KqXCGrY']; print(random.Random(int('d4597a05db72223090b8751304a1d71edc5d00b7',16)).sample(sorted(pods),2))"
```

Output on the dev box (Python 3.8.2): `['Bq-nFi0f1jA', 'CxKMqO36DdM']`.
Integer seeding and list sampling have been stable across Python 3 releases;
if a later version ever prints something else, this recorded 3.8.2 result is
the draw.

**Confirming the seed was fixed before the draw.** The lot was drawn in
commit `1f8e52dac9f618f2d7999aa1d24cda5f23643119` ("Holdout drawn by lot",
2026-09-26 12:48 -0400) on the `repair/week1` branch. That commit adds this
file and touches nothing else, and its parent is the seed above. main does
not contain it: week 1 reached main as the squash merge `ef80299` (#63), so
on main the commit that adds this file is `ef80299`, whose parent `39e2a41`
has nothing to do with the lot. A check limited to main's history therefore
finds the wrong commit. Look across every ref instead:

```
git log --all --diff-filter=A --format="%H %P" -- studies/holdout/HOLDOUT.md
```

It lists two commits that add this file:

- `1f8e52dac9f618f2d7999aa1d24cda5f23643119 d4597a05db72223090b8751304a1d71edc5d00b7`:
  the draw; its parent must equal the seed above;
- `ef802994e20d2cf0f40a5f0926cf13178d741c69 39e2a419a2ab5a5d7e32e36f2fee23331b595010`:
  the squash merge that carried the file to main; ignore it.

`git show --stat 1f8e52d` confirms the draw commit changed only this file,
and `git show 1f8e52d:studies/holdout/HOLDOUT.md` shows the draw as it was
recorded at the time.

**The proof lasts only while `1f8e52d` is reachable from a ref.** Today that
is the `repair/week1` branch, locally and on GitHub (`origin/repair/week1`).
If that branch is deleted, git can garbage-collect the commit, and nothing on
main would then show that the seed predates the draw. Keep `repair/week1`,
or tag `1f8e52d` (for example `holdout-draw-2026-09-26`) and push the tag
before the branch goes. Which one is Vincent's call; no tag has been made.

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
week-1 report proposed reporting holdout figures per deck, and the pooled
holdout figures both with and without those two seats. Vincent accepted that
on 2026-09-27, and it is now rule 5 above.

Two fidelity notes from `studies/human_ceiling/RESULTS.md` and its manifest
also apply: the kinnan seat in `Bq-nFi0f1jA` is a different build from the one
the human played, and dallas_bluefarm's list has drifted from the streamed one
(Jeska's Will and Harnfel are missing). Neither matters for a sim-only holdout,
but neither list is a faithful copy of the human game.
