# Diagnosis evidence, 2026-09

The scripts and results behind the September 2026 diagnosis of why combos,
tutoring and play logic go wrong in the sim. The readable conclusions are
elsewhere:

- `SYNTHESIS.md` (this folder): ranked root causes RC1 to RC10, measurement and
  product problems, refuted claims, and the verification record.
- `tasks/25-repair-plan.md`: the repair plan built on it, accepted by Vincent
  on 2026-09-26.
- `tasks/26-ux-review.md`: the UX review (the scratchpad's `ux_final.md`, after
  cleaning).

This folder is the evidence those documents cite. It was copied out of a
session scratchpad under `AppData\Local\Temp` on 2026-09-26 (repair plan WS0
task 1), because Windows can clean Temp at any time.

## What is here

| Path | What it is |
|---|---|
| `diag_result.json` | The diagnosis result: `synthesis` (root causes, measurement and product problems, cheap experiments, refuted claims), the 30 adversarially checked findings under `verified`, and the 8 dimension reports. The plan's "Diagnosis" and its RC numbers point here. |
| `syn.txt` | The synthesis block on its own, as JSON; `SYNTHESIS.md` was written from it. |
| `verified_dump.txt` | The verifiers' verdicts and re-checked evidence, one JSON object per finding. |
| `ux_result.json` | The UX review result: final text, draft, critiques, walkthroughs, research. |
| `combo_data/`, `combo_execution/`, `forge_leverage/`, `human_vs_sim_decisions/`, `play_logic_general/`, `product_surface/`, `research_meta/`, `tutoring/` | One folder per diagnosis dimension: the investigator's prototype scripts and the small JSON and text results they wrote. |
| `verify/` | The adversarial verification pass: one subfolder per checked claim, with the scripts that re-measured it. |
| `ux/` | Two measurement notes from the UX walkthroughs. |
| `check_allowlist.py` | The allowlist check (below). |
| `copy_evidence.py` | The copy itself: what was taken, what was left out and why. |

Counts: 276 `.py`, 202 `.json`, 36 `.txt` and 1 `.md` were copied (515 files,
19.1 MB), plus this README, `SYNTHESIS.md`, the two scripts and `.gitignore`.

### The prototypes are evidence, not tools

The scripts were written to answer one question each, fast. Most hard-code
absolute paths: the study folders in the main checkout
(`C:\Users\Vatto\Magic Rules Engine\studies\...`), the session scratchpad, and
the local Forge install. They will not run from a fresh clone without editing,
and several read Forge's own files at run time, which is fine locally and is
why their outputs are not all here.

Nothing in `engine/` may import from this folder. When the repair plan needs
one of these analyses in the product or the QA layer (WS1, `engine/qa/`),
port the logic into a tested, stdlib-only module and check it against the
figure recorded here (the "port test").

## What was left out, and why

The repo's legal posture (CLAUDE.md) forbids committing anything Forge-derived,
and the repair plan (§2.3, §8) forbids committing a playtester's data. So the
copy is an allowlist, not a mirror. From the 1,369 files under the scratchpad's
`diagnosis/` folder, `copy_evidence.py` left out 860:

| Files | Reason |
|---|---|
| 571 | `.class` files: Forge bytecode extracted for reading |
| 62 | Inside `jarx/` (16), `shimcopy/` (22: copies of the shim's GPL Java and a shim jar) or `__pycache__/` (24) |
| 45 | javap disassembly under names the list below does not catch (the content check found the javap header) |
| 16 | Named on the plan's never-commit list: `*.javap.txt`, `ChangeZoneAi.txt`, `scripts_cache.json`, `forge_card_index.json`, `fidx.json`, `allai.txt` |
| 26 | Over 1 MB (adapted result files, card and combo caches, large row dumps) |
| 95 | `combo_data/raw/`: raw Commander Spellbook API responses, about 28 MB. Third-party data, not our results, and regenerable. The 66 small responses under `verify/precon_suffix/raw/` (about 40 KB) were kept, because they are the evidence for the corrected "zero precon variants" claim. |
| 9 | Forge-derived files the content check does not catch, found by reading every flagged candidate: three Forge jar class listings, one headerless bytecode excerpt, Forge's AI profile key names, two card-script extracts and two card-to-AI-flag indexes built from Forge's card scripts |
| 36 | Other types: 28 `.dck` copies of the bundled `engine/decks/` lists, 3 `.log`, 2 `.jsonl`, 1 `.sh`, 1 `.pkl`, 1 empty marker file with no extension |

Also left out: the scratchpad's `richard/` folder (the playtester Richard's
decklists and their 2.4 MB production result), its `gs/` and `gs2/` folders
(extracted Forge classes), the playtester's game payloads in `ux/`, and the
draft copies of the plan and UX review, whose final text is committed under
`tasks/`.

## The off-repo archive

Everything, including what was left out above, is in one zip that never goes
in a repo:

- Path: `C:\Users\Vatto\simlab-archive\diagnosis_2026-09.zip`
- 1,421 files (36,171,051 bytes): the scratchpad's `diagnosis/` (1,369),
  `ux/` (20), `richard/` (15), `gs/` and `gs2/` (4), and the top-level drafts
  and results (13).
- SHA-256: `204aaf13211a590f6a2c86fac52d5afa1a6f4470bee5e3d8f354d1f9a46b779d`

It holds Forge-derived material and a playtester's decklists, so it must never
be published or attached anywhere public. Richard's folder moves to the private
data repo once that exists (repair plan W9, decision 9).

`local/` in this folder is gitignored scratch space for anything that must not
be committed. Decision 9 adds `studies/diagnosis_2026-09/local/` to the
strip-before-public list.

## Checking the allowlist

```
git add studies/diagnosis_2026-09
py studies/diagnosis_2026-09/check_allowlist.py            # what a commit would contain
py studies/diagnosis_2026-09/check_allowlist.py --all      # plus untracked files, before git add
py studies/diagnosis_2026-09/check_allowlist.py --archive  # plus the zip's SHA-256 (dev box only)
```

It reads every tracked file under this folder from the git index and fails
unless each one is `.py`, `.md`, `.json` or `.txt` (the folder's `.gitignore`
excepted), at most 1 MB, and free of the class-file magic bytes, the javap
header and a Java package declaration for Forge or the shim. It also fails if
any tracked path sits under `gs/`, `gs2/`, `jarx/`, `shimcopy/`, `richard/`,
`local/` or `__pycache__/`. Run it before every commit that touches this
folder.
