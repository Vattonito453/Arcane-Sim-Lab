"""Is the pod's aggression aimed at the deck that is actually winning?

MEASURED 2026-08-30, and the answer is "not established, on this much data".
Across the four archived runs that carry behaviour records the within-run
Spearman between attackers faced and win rate came out -1.00, +0.32, +0.11 and
-0.32: mean -0.22 with a standard error of about 0.29, which is t = -0.8 and
nowhere near a result. The -1.00 run is real and is the one that prompted this
script (its leader was attacked least and its bottom deck most), but it is one
pod, and three more runs do not reproduce it.

Recording that here because the anecdote is seductive: a perfectly inverted
pod looks exactly like a broken threat model, and acting on it would have
meant retuning kingmakerReaim against noise. Re-run this as runs accumulate.
For reference, kingmaker_reaim fires on roughly 3 to 14% of attack
declarations, so the mechanism is live either way.

For each archived run that carries behaviour records, rank the decks two ways:
by attackers faced, and by win rate. If the agent threat-assesses, the deck
that is ahead should absorb MORE aggression, so the two ranks should move
together (positive correlation). An inverted pod is one where the leader is
left alone.

Spearman is computed within a run, across its decks, so pod composition and
run length cannot leak between runs. Runs with fewer than 3 decks, or where
every deck has the same win rate, carry no rank information and are skipped
rather than scored as zero.
"""
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))

RESULTS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.environ.get("MTG_DATA_DIR", str(
        Path(__file__).resolve().parent.parent / "engine")), "sim_results")
from scorecard import scorecards  # noqa: E402


def rank(xs):
    """Average ranks, so ties do not invent an ordering."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(a, b):
    ra, rb = rank(a), rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = sum((ra[i] - ma) ** 2 for i in range(n)) ** 0.5
    db = sum((rb[i] - mb) ** 2 for i in range(n)) ** 0.5
    if da == 0 or db == 0:
        return None
    return num / (da * db)


rows = []
for path in sorted(glob.glob(os.path.join(RESULTS, "sim_*.json"))):
    if path.endswith(".bak"):
        continue
    try:
        result = json.load(open(path))
    except Exception:
        continue
    try:
        sc = scorecards(result)
    except Exception as e:
        print("skip %s: %s" % (os.path.basename(path), e))
        continue
    if not sc["run"].get("hasBehaviour"):
        continue
    faced, wins, names = [], [], []
    for d in sc["decks"]:
        b = d.get("blocking")
        if b is None or d.get("winRate") is None:
            continue
        faced.append(b["faced"])
        wins.append(d["winRate"])
        names.append(d["deck"])
    if len(faced) < 3:
        continue
    rho = spearman(faced, wins)
    if rho is None:
        continue
    rows.append((os.path.basename(path), sc["run"]["games"], len(faced), rho))

if not rows:
    print("no runs with behaviour records and rankable win rates")
    raise SystemExit(0)

print("%-52s %5s %5s %7s" % ("run", "games", "decks", "rho"))
for name, games, n, rho in rows:
    print("%-52s %5d %5d %+7.2f" % (name[:52], games, n, rho))

rhos = [r[3] for r in rows]
mean = sum(rhos) / len(rhos)
neg = sum(1 for r in rhos if r < 0)
print()
print("runs scored: %d" % len(rhos))
print("mean rho (faced vs win rate): %+.3f" % mean)
print("runs where the leader was attacked LESS than the field: %d of %d"
      % (neg, len(rhos)))
print()
print("rho > 0 means aggression tracked the leader (good threat assessment).")
print("rho < 0 means the pod beat on the losers and left the leader alone.")
