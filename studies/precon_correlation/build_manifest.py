#!/usr/bin/env python3
"""Resolve each ground-truth precon to the .dck Forge already ships.

Forge bundles 172 Commander precons as native .dck files under
`res/quest/commanderprecons/`. Using those instead of scraped decklists buys us
three things:

  1. No decklist acquisition, and nothing taken from Playgroup's site.
  2. Native .dck, so no conversion step and no parse risk.
  3. A single canonical printing per precon, set-qualified per card.

We do NOT copy the .dck files into this repo. CLAUDE.md forbids vendoring
Forge, and it is unnecessary: the sim runs where Forge is already installed, so
the runner resolves each file under $FORGE_DIR at run time. Only this manifest
(our own mapping + the ground-truth join) is committed.

Usage:
    python3 studies/precon_correlation/build_manifest.py            # write manifest.json
    python3 studies/precon_correlation/build_manifest.py --check    # verify only
"""

import argparse
import json
import re
import unicodedata
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = ("https://api.github.com/repos/Card-Forge/forge/contents/"
       "forge-gui/res/quest/commanderprecons?ref=master")
FORGE_SUBDIR = "res/quest/commanderprecons"

# Forge's filenames differ from the printed precon names for these. Verified by
# hand against the bundle listing; the printed (WotC) name is the key.
ALIASES = {
    "The Hosts of Mordor": "The Host of Mordor",
    "Mind Flayarrgh": "Mind Flayarrrs",
}

# Where two Forge files share a name (reprint precons), pin the set code.
SET_PINS = {}


def norm(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def fetch_listing():
    cache = HERE / ".forge_precon_listing.json"
    if cache.exists():
        return json.loads(cache.read_text())
    req = urllib.request.Request(
        API, headers={"User-Agent": "simlab-precon-study/1.0", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        names = [x["name"] for x in json.load(r)]
    cache.write_text(json.dumps(names, indent=1))
    return names


def index(names):
    out = {}
    for f in names:
        m = re.match(r"^(.*?)\s*\[([A-Z0-9]+)\]\s*\[(\d{4})\]\.dck$", f)
        if not m:
            continue
        out.setdefault(norm(m.group(1)), []).append(
            {"file": f, "forge_name": m.group(1), "set_code": m.group(2),
             "printing_year": int(m.group(3))})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify without writing")
    args = ap.parse_args()

    gt = json.loads((HERE / "ground_truth.json").read_text())
    idx = index(fetch_listing())

    rows, missing, ambiguous = [], [], []
    for d in gt["precons"]:
        lookup = ALIASES.get(d["name"], d["name"])
        cands = idx.get(norm(lookup), [])
        if not cands:
            missing.append(d["name"])
            continue
        if len(cands) > 1:
            pin = SET_PINS.get(d["name"])
            picked = next((c for c in cands if c["set_code"] == pin), None)
            if picked is None:
                ambiguous.append((d["name"], [c["file"] for c in cands]))
                continue
        else:
            picked = cands[0]
        rows.append({
            "name": d["name"],
            "set": d["set"],
            "commander": d["commander"],
            "tier": d["tier"],
            "human_win_rate": d["human_win_rate"],
            "human_games": d["human_games"],
            "forge_file": picked["file"],
            "forge_name": picked["forge_name"],
            "set_code": picked["set_code"],
            "printing_year": picked["printing_year"],
            "aliased": d["name"] in ALIASES,
        })

    print(f"resolved   {len(rows)}/{len(gt['precons'])}")
    if missing:
        print(f"MISSING    {missing}")
    if ambiguous:
        print(f"AMBIGUOUS  {ambiguous}  (add to SET_PINS)")
    aliased = [r["name"] for r in rows if r["aliased"]]
    print(f"aliased    {aliased}")

    if args.check:
        return
    out = {
        "generated_from": "Card-Forge/forge master, " + FORGE_SUBDIR,
        "forge_subdir": FORGE_SUBDIR,
        "note": "forge_file is resolved under $FORGE_DIR at run time; these "
                "files are not vendored into this repo.",
        "ground_truth_source": gt["source"],
        "ground_truth_captured": gt["captured"],
        "resolved": len(rows),
        "precons": sorted(rows, key=lambda r: -r["human_win_rate"]),
    }
    (HERE / "manifest.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote      {HERE / 'manifest.json'}")


if __name__ == "__main__":
    main()
