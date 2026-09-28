#!/usr/bin/env python3
"""Which pilot played a run, as one comparable id.

The prediction model, the rank checks that decide whether it may be shown
(repair plan WS11 task 11, decision 19) and, later, a leaderboard grouped by
pilot all have to ask "was this run piloted the same way as that one?". The
answer is spread over meta fields whose shape changed across shim versions:

  meta.agent             "simlab-forge-shim/0.17.0" on shim runs; the bare
                         "simlab-forge-shim" when a rotated run's rotations
                         disagreed or a run was salvaged; "forge" on a
                         salvaged stock run; absent on a stock stdout run
  meta.agents            per-seat controller, "plan" or "stock" (one run)
  meta.rotations_detail  the same per rotation, with agent, planVersions and
                         fixFlags (run_sim._merged_shim_meta)
  meta.humanized         one bool for the pod, on every shim version
  meta.planVersions      per-seat plan version, shim >= 0.17.0 (carried by
                         shim_log_adapter from R1)
  meta.fixFlags          per-seat hotfix flags, same

planVersions and fixFlags are the ONLY plan-version fields a result carries:
they are what the shim reports it loaded, seat by seat, so a seat that fell
back to stock reads null rather than inheriting the plans file's version. (The
week-3 game-story branch also had run_sim write meta.plan_version and
meta.plan_fix from the plans it built; that was folded into these at the
week-3 integration, and no committed fixture or production result carries it.)

One derivation, two readers. run_pilot() is the identity (the prediction's
rank checks are keyed by its id); disclose() is the run page's wording built
on it (validity.pilot delegates here), and the prediction payload carries
disclose() too, so the run-page line and the prediction label can never
disagree about kind, shim, plan version or fix flags.

Ids, and what they mean:

  "stock"                     Forge's own AI in every seat, through the shim
                              or on the stdout path (the same AI either way:
                              the model's training arm was shim runs with no
                              plans)
  "plan/0.17.0/v2"            Sim Lab's plan pilot, shim 0.17.0, version-2
                              plans with every fix flag (the R1 pilot)
  "plan/0.17.0/v2/fix=none"   version 2 with a flag subset (G0a's per-flag
                              arms); "fix=a+b" names the flags that are on
  "plan/0.16.0/v1"            shims before 0.17.0 read version-1 plans only
  "plan/0.17.0/v-unrecorded"  a 0.17.0 run adapted before plan versions were
                              carried into the result
  "mixed/<shim>/<plans>"      plan seats and stock seats in one run
  "unknown"                   a shim run that records neither per-seat
                              agents nor humanized

Stdlib only; no card knowledge. The text fields are user-facing copy.
"""
from __future__ import annotations

SHIM_AGENT = "simlab-forge-shim"
# The first shim that reads a plan's version. Earlier shims ignore every
# version-2 field, so a run on them was piloted by version-1 plans whatever
# the plans file said (preflight refuses MTG_PLAN_VERSION=2 on them).
PLAN_VERSIONED_SHIM = (0, 17, 0)


def version_tuple(text) -> tuple[int, ...] | None:
    """"0.17.0" -> (0, 17, 0); None for anything that is not dotted ints."""
    try:
        return tuple(int(x) for x in str(text).strip().split("."))
    except (TypeError, ValueError):
        return None


def _rotations(meta: dict) -> list[dict]:
    """Per-rotation metas when the run kept them, else the run meta itself."""
    detail = meta.get("rotations_detail")
    if isinstance(detail, list):
        rots = [d for d in detail if isinstance(d, dict)]
        if rots:
            return rots
    return [meta]


def _shim_version(meta: dict, rots: list[dict]) -> tuple[str | None, bool]:
    """(version, disagreed). A version only when every place that names one
    agrees; rotations on two shims are not one pilot."""
    seen = set()
    for m in [meta, *rots]:
        agent = str(m.get("agent") or "")
        if agent.startswith(SHIM_AGENT + "/"):
            seen.add(agent.split("/", 1)[1])
    if len(seen) == 1:
        return seen.pop(), False
    return None, len(seen) > 1


def _controllers(meta: dict, rots: list[dict]) -> set[str]:
    seats: list[str] = []
    for r in rots:
        agents = r.get("agents")
        if isinstance(agents, list):
            seats.extend(str(a) for a in agents)
    if seats:
        return set(seats)
    by_rot = meta.get("humanized_by_rotation")
    if isinstance(by_rot, list) and by_rot:
        return {"plan" if x else "stock" for x in by_rot}
    if meta.get("humanized") is True:
        return {"plan"}
    if meta.get("humanized") is False:
        return {"stock"}
    return set()


def _plan_seats(rots: list[dict], key: str) -> list:
    """Values of a per-seat list (planVersions, fixFlags) for plan seats only:
    a stock seat's plan version says nothing about how the run was piloted."""
    out = []
    for r in rots:
        vals = r.get(key)
        if not isinstance(vals, list):
            continue
        agents = r.get("agents") if isinstance(r.get("agents"), list) else None
        for i, v in enumerate(vals):
            if agents is not None and i < len(agents) and agents[i] != "plan":
                continue
            out.append(v)
    return out


def _plan_part(rots: list[dict], shim: str | None
               ) -> tuple[str, int | None, object, int | None]:
    """("v2", 2, "all", 4) and the like: the plan version and fix flags of
    the plan seats. Returns the id fragment, the single version (or None),
    the fix description ("all", "none", a sorted list, "mixed" or None) and
    how many fix flags the shim reported (None when it reported none)."""
    versions = set()
    for v in _plan_seats(rots, "planVersions"):
        try:
            versions.add(int(v))
        except (TypeError, ValueError):
            continue
    if not versions:
        vt = version_tuple(shim) if shim else None
        if vt is not None and vt < PLAN_VERSIONED_SHIM:
            versions = {1}
    if not versions:
        return "v-unrecorded", None, None, None
    part = "v" + "+v".join(str(v) for v in sorted(versions))
    single = next(iter(versions)) if len(versions) == 1 else None
    if 2 not in versions:
        return part, single, None, None
    on_sets = set()
    for f in _plan_seats(rots, "fixFlags"):
        if isinstance(f, dict):
            on_sets.add((frozenset(f), frozenset(k for k, on in f.items() if on)))
    if not on_sets:
        return part + "/fix=unrecorded", single, None, None
    if len(on_sets) > 1:
        total = max(len(names) for names, _on in on_sets)
        return part + "/fix=mixed", single, "mixed", total
    names, on = on_sets.pop()
    if on == names:
        return part, single, "all", len(names)
    if not on:
        return part + "/fix=none", single, "none", len(names)
    flags = sorted(on)
    return part + "/fix=" + "+".join(flags), single, flags, len(names)


def run_pilot(meta: dict | None) -> dict:
    """{"id", "kind", "shim", "plan_version", "fix", "fix_total", "text"}
    for one run.

    kind is "stock", "plan", "mixed" or "unknown". fix_total is how many fix
    flags the plan seats' shim reported (so a flag subset can be worded "2 of
    4"). text is written for a player and names Sim Lab's pilot the way the
    product does."""
    meta = meta if isinstance(meta, dict) else {}
    agent = str(meta.get("agent") or "")
    if not agent.startswith(SHIM_AGENT):
        # The stdout path (no agent) and a salvaged stock run ("forge") are
        # Forge's own AI; neither can run a plan.
        return {"id": "stock", "kind": "stock", "shim": None, "plan_version": None,
                "fix": None, "fix_total": None, "text": "stock Forge"}
    rots = _rotations(meta)
    shim, disagreed = _shim_version(meta, rots)
    kinds = _controllers(meta, rots)
    if not kinds:
        return {"id": "unknown", "kind": "unknown", "shim": shim, "plan_version": None,
                "fix": None, "fix_total": None, "text": "a pilot this run did not record"}
    if kinds == {"stock"}:
        return {"id": "stock", "kind": "stock", "shim": shim, "plan_version": None,
                "fix": None, "fix_total": None, "text": "stock Forge"}
    kind = "plan" if kinds == {"plan"} else "mixed"
    part, version, fix, fix_total = _plan_part(rots, shim)
    shim_part = shim or ("mixed-shims" if disagreed else "unrecorded-shim")
    if kind == "mixed":
        text = "Sim Lab's pilot in some seats and stock Forge in the others"
    else:
        bits = []
        if shim:
            bits.append(f"shim {shim}")
        bits.append(f"version-{version} plans" if version else "plan version not recorded")
        text = f"Sim Lab's pilot ({', '.join(bits)})"
    return {"id": f"{kind}/{shim_part}/{part}", "kind": kind, "shim": shim,
            "plan_version": version, "fix": fix, "fix_total": fix_total, "text": text}


# ---- the run page's disclosure (repair plan WS11 task 10) ------------

def _deck_agents(meta: dict) -> dict[str, set]:
    """{deck: {"plan", "stock", ...}} from the per-rotation seat records (or
    the one-rotation meta.agents aligned with meta.players)."""
    out: dict[str, set] = {}
    for rot in meta.get("rotations_detail") or []:
        if not isinstance(rot, dict):
            continue
        seats, agents = rot.get("seats") or [], rot.get("agents") or []
        for deck, agent in zip(seats, agents):
            out.setdefault(str(deck), set()).add(str(agent))
    if not out and isinstance(meta.get("agents"), list):
        players = meta.get("players") or [f"seat {i + 1}" for i in range(len(meta["agents"]))]
        for deck, agent in zip(players, meta["agents"]):
            out.setdefault(str(deck), set()).add(str(agent))
    return out


def _fix_words(fix, total) -> str | None:
    """The tutoring-hotfix flags in words. The UI never shows flag names."""
    if fix == "all":
        return "tutoring fixes on"
    if fix == "none":
        return "tutoring fixes off"
    if fix == "mixed":
        return "tutoring fixes differ by seat"
    if isinstance(fix, list):
        return (f"{len(fix)} of {total} tutoring fixes on" if total
                else f"{len(fix)} tutoring fixes on")
    return None


def disclose(meta: dict | None) -> dict:
    """Who piloted a run, disclosed on every run page.

    run_pilot()'s fields unchanged ({"id", "kind", "shim", "plan_version",
    "fix", "fix_total", "text"}), plus:
      agent        meta.agent verbatim ("simlab-forge-shim/0.15.0")
      plan_decks, stock_decks
                   the decks that ran only that pilot in every rotation (a
                   deck whose seat fell back in one rotation is in neither;
                   None when the run records no per-seat pilot)
      random       True while any random dial remains in the pilot: every
                   plan seat to date skips some blocks at random by design
                   (owner decision 8 retires that at E8). A run that records
                   meta.random_dials is taken at its word.
      label, note  the words the UI shows. "Humanized" is no longer a
                   product claim (owner decision 8); the note says what is
                   true instead: "Some choices are random on purpose."

    kind comes from run_pilot, so the label can never name a category the
    prediction's pilot_honesty did not see. The plan's version and fix flags
    are named only when a seat ran the plan: they describe plan seats, and a
    run whose seats all fell back to stock must not read "a plan piloted
    this". Copy rules apply (these strings reach the UI): no em dash."""
    meta = meta if isinstance(meta, dict) else {}
    p = run_pilot(meta)
    kind, shim = p["kind"], p["shim"]
    agent = meta.get("agent") if isinstance(meta.get("agent"), str) else None
    via_shim = bool(agent and agent.startswith(SHIM_AGENT))
    per_deck = _deck_agents(meta)
    plan_decks = sorted(d for d, a in per_deck.items() if a == {"plan"})
    stock_decks = sorted(d for d, a in per_deck.items() if a and "plan" not in a)
    by_rot = meta.get("humanized_by_rotation")

    random_dials = meta.get("random_dials")
    random = (random_dials if isinstance(random_dials, bool)
              else kind in ("plan", "mixed"))

    shim_words = f"shim {shim}" if shim else ("Sim Lab's shim" if via_shim else None)
    plan_words = []
    if kind in ("plan", "mixed"):
        if p["plan_version"] is not None:
            plan_words.append(f"plan version {p['plan_version']}")
        fix = _fix_words(p["fix"], p["fix_total"])
        if fix:
            plan_words.append(fix)
    detail = ", ".join(w for w in [*plan_words, shim_words] if w)
    tail = f" ({detail})" if detail else ""
    if kind == "plan":
        label = f"Piloted by Sim Lab's plan agent on Forge's AI{tail}."
    elif kind == "stock":
        label = (f"Piloted by Forge's own AI{tail}." if via_shim
                 else "Piloted by Forge's own AI.")
    elif kind == "mixed":
        n_plan = len(plan_decks)
        # A deck that ran the plan in some rotations and stock in others (a
        # rotation whose seats fell back) is in neither count, so "N decks on
        # the plan agent, the rest on Forge's own AI" would be untrue: with one
        # of four rotations fallen back it read "0 decks on Sim Lab's plan
        # agent" for a run the plan piloted three quarters of. Say it by
        # rotation instead.
        split = per_deck and n_plan + len(stock_decks) < len(per_deck)
        if per_deck and not split:
            label = (f"Mixed pilots: {n_plan} {'deck' if n_plan == 1 else 'decks'} on "
                     f"Sim Lab's plan agent, the rest on Forge's own AI{tail}.")
        elif isinstance(by_rot, list) and by_rot:
            ran = sum(1 for x in by_rot if x)
            label = (f"Mixed pilots: {ran} of {len(by_rot)} seat rotations ran Sim Lab's "
                     f"plan agent, the rest Forge's own AI{tail}.")
        else:
            label = (f"Mixed pilots: some seat rotations ran Sim Lab's plan agent "
                     f"and the rest Forge's own AI{tail}.")
    else:
        label = "Pilot not recorded: this run predates it."
    return {
        **p,
        "agent": agent,
        "plan_decks": len(plan_decks) if per_deck else None,
        "stock_decks": len(stock_decks) if per_deck else None,
        "random": bool(random),
        "label": label,
        "note": "Some choices are random on purpose." if random else None,
    }


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    for arg in sys.argv[1:]:
        data = json.loads(Path(arg).read_text(encoding="utf-8"))
        print(arg, json.dumps(run_pilot(data.get("meta"))))
