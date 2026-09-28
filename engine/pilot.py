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


def _plan_part(rots: list[dict], shim: str | None) -> tuple[str, int | None, object]:
    """("v2", 2, "all") and the like: the plan version and fix flags of the
    plan seats. Returns the id fragment, the single version (or None) and the
    fix description ("all", "none", a sorted list, "mixed" or None)."""
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
        return "v-unrecorded", None, None
    part = "v" + "+v".join(str(v) for v in sorted(versions))
    single = next(iter(versions)) if len(versions) == 1 else None
    if 2 not in versions:
        return part, single, None
    on_sets = set()
    for f in _plan_seats(rots, "fixFlags"):
        if isinstance(f, dict):
            on_sets.add((frozenset(f), frozenset(k for k, on in f.items() if on)))
    if not on_sets:
        return part + "/fix=unrecorded", single, None
    if len(on_sets) > 1:
        return part + "/fix=mixed", single, "mixed"
    names, on = on_sets.pop()
    if on == names:
        return part, single, "all"
    if not on:
        return part + "/fix=none", single, "none"
    flags = sorted(on)
    return part + "/fix=" + "+".join(flags), single, flags


def run_pilot(meta: dict | None) -> dict:
    """{"id", "kind", "shim", "plan_version", "fix", "text"} for one run.

    kind is "stock", "plan", "mixed" or "unknown". text is written for a
    player and names Sim Lab's pilot the way the product does."""
    meta = meta if isinstance(meta, dict) else {}
    agent = str(meta.get("agent") or "")
    if not agent.startswith(SHIM_AGENT):
        # The stdout path (no agent) and a salvaged stock run ("forge") are
        # Forge's own AI; neither can run a plan.
        return {"id": "stock", "kind": "stock", "shim": None, "plan_version": None,
                "fix": None, "text": "stock Forge"}
    rots = _rotations(meta)
    shim, disagreed = _shim_version(meta, rots)
    kinds = _controllers(meta, rots)
    if not kinds:
        return {"id": "unknown", "kind": "unknown", "shim": shim, "plan_version": None,
                "fix": None, "text": "a pilot this run did not record"}
    if kinds == {"stock"}:
        return {"id": "stock", "kind": "stock", "shim": shim, "plan_version": None,
                "fix": None, "text": "stock Forge"}
    kind = "plan" if kinds == {"plan"} else "mixed"
    part, version, fix = _plan_part(rots, shim)
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
            "plan_version": version, "fix": fix, "text": text}


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    for arg in sys.argv[1:]:
        data = json.loads(Path(arg).read_text(encoding="utf-8"))
        print(arg, json.dumps(run_pilot(data.get("meta"))))
