"""Copy the diagnosis evidence into this folder by allowlist (repair plan WS0
task 1). Kept as the record of exactly what was copied and what was left out;
README.md quotes its output.

    py copy_evidence.py [--src DIR] [--write]

Dry run by default; --write copies. DIR is the folder that holds `diagnosis/`
and the top-level result files: the 2026-09-26 session scratchpad (the
default, which Windows may since have cleaned out of Temp) or an unzip of the
off-repo archive named in README.md. Run check_allowlist.py after any copy.
"""
import os, shutil, sys, collections

SCRATCH = r"C:\Users\Vatto\AppData\Local\Temp\claude\C--Users-Vatto-Magic-Rules-Engine\7a2e31e0-09c8-49d0-ab6f-f767ccb4d74a\scratchpad"
if "--src" in sys.argv:
    SCRATCH = sys.argv[sys.argv.index("--src") + 1]
SRC = os.path.join(SCRATCH, "diagnosis")
DEST = os.path.dirname(os.path.abspath(__file__))

EXT = {".py", ".md", ".json", ".txt"}
MAX = 1024 * 1024
# WS0 task 1 "never commit" list.
EXCL_DIRS = {"jarx", "shimcopy", "gs", "gs2", "__pycache__"}
EXCL_NAMES = {"AiController.javap.txt", "ChangeZoneAi.txt", "scripts_cache.json",
              "forge_card_index.json", "fidx.json", "allai.txt"}
# Content markers, the same four check_allowlist.py enforces. Built by
# concatenation so this file passes that check itself.
MARKERS = [bytes.fromhex("cafebabe"), b"Compiled" + b" from",
           b"package" + b" forge", b"package" + b" simlab"]
# Forge-derived files the markers do not catch, found by reading each flagged
# candidate: jar class listings, a headerless bytecode excerpt, Forge's AI
# profile key names, card-script extracts and card-to-AI-flag indexes built
# from Forge's res/. Kept only in the off-repo archive.
REVIEW_EXCL = {
    "forge_leverage/default_keys.txt": "Forge AI profile key names",
    "verify/removedeck/classes.txt": "Forge jar class listing",
    "verify/removedeck/aiclasses.txt": "Forge jar class listing",
    "verify/combo_loops/aiclasses.txt": "Forge jar class listing",
    "verify/combo_loops/gsatp.txt": "javap bytecode excerpt without header",
    "play_logic_general/forge_ai_flags.json": "card-to-AI-flag index from Forge res/",
    "verify/aiblind/name2flags.json": "card-to-AI-flag index from Forge res/",
    "verify/tutor_restrictions/forge_scripts.json": "Forge card-script extracts",
    "verify/tutor_restrictions/scripts_dump.txt": "Forge card-script extracts",
}
# Third-party API response caches (Commander Spellbook), not our own results;
# about 28 MB and regenerable. The 66 tiny precon_suffix responses (about
# 40 KB) are kept: they are the evidence behind the corrected "zero precon
# variants" claim.
EXCL_PREFIX = {"combo_data/raw/": "Commander Spellbook raw responses (third-party cache)"}

# Top-level results WS0 task 1 names. ux_final.md is not copied: its cleaned
# text is tasks/26-ux-review.md, byte for byte. Of the scratchpad's ux/ folder
# only the two measurement notes come across; the rest is the playtester's
# game payloads (their decks, card by card), which stay in the archive.
EXTRA_TOP = ["diag_result.json", "ux_result.json", "syn.txt", "verified_dump.txt"]
EXTRA_UX = ["ux/first_run_and_decks.md", "ux/cross_cutting_visual_a11y.txt"]


def classify(rel, path):
    fn = os.path.basename(rel)
    parts = set(rel.split("/")[:-1])
    ext = os.path.splitext(fn)[1].lower()
    if parts & EXCL_DIRS:
        return "excluded dir (" + ",".join(sorted(parts & EXCL_DIRS)) + ")"
    if ext not in EXT:
        return "extension " + (ext or "(none)")
    if fn in EXCL_NAMES or fn.endswith(".javap.txt"):
        return "named never-commit file"
    if os.path.getsize(path) > MAX:
        return "over 1 MB"
    for p, why in EXCL_PREFIX.items():
        if rel.startswith(p):
            return why
    if rel in REVIEW_EXCL:
        return "review: " + REVIEW_EXCL[rel]
    b = open(path, "rb").read()
    for m in MARKERS:
        if m in b:
            return "content marker " + repr(m)
    return None


def main():
    write = "--write" in sys.argv
    keep, drop = [], collections.Counter()
    total = 0
    for dp, dns, fns in os.walk(SRC):
        for fn in fns:
            path = os.path.join(dp, fn)
            rel = os.path.relpath(path, SRC).replace("\\", "/")
            total += 1
            why = classify(rel, path)
            if why:
                drop[why] += 1
            else:
                keep.append((rel, path))
    for rel in EXTRA_TOP + EXTRA_UX:
        path = os.path.join(SCRATCH, rel.replace("/", os.sep))
        why = classify(rel, path)
        if why:
            print("EXTRA EXCLUDED", rel, why)
        else:
            keep.append((rel, path))
    size = sum(os.path.getsize(p) for _, p in keep)
    print(f"source files under diagnosis/: {total}")
    print(f"kept: {len(keep)} files, {size/1e6:.1f} MB")
    for k, v in drop.most_common():
        print(f"  dropped {v:4d}  {k}")
    ext = collections.Counter(os.path.splitext(r)[1] for r, _ in keep)
    print("kept by extension:", dict(ext))
    if write:
        for rel, path in keep:
            out = os.path.join(DEST, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copy2(path, out)
        print("copied to", DEST)


if __name__ == "__main__":
    main()
