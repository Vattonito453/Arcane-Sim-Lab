#!/usr/bin/env python3
"""What Forge itself knows about each card, read from its own card scripts.

Why this exists (repair plan WS4, diagnosis RC3 and RC9): the sim and the combo
lookup were silently given different decks than the user pasted, and nothing
could tell. Forge refuses a double-faced card spelled "Front // Back" and says
so only on stderr; Forge's AI never casts any card scripted
`AI:RemoveDeck:All` (Winter, Cynical Opportunist as a commander is simply never
cast). Both facts live in Forge's card scripts, so this module reads them there
instead of guessing from Scryfall: Forge decides what Forge loads.

Output, under $MTG_DATA_DIR/forge_index/<forge_version>/ (engine/ locally):
  cards.json   every card name Forge loads -> its AlternateMode (DoubleFaced,
               Modal, Split, Flip, Adventure, ...), its faces, its front types
  flags.json   cards scripted AI:RemoveDeck:All, and what the filter blocks on
               each: its spell, a non-mana activation, a mana ability, and
               whether it could be a commander (counterspells are listed apart:
               Forge's counterspell pre-pass escapes the filter)
  tutors.json  ChangeType / Origin / Destination per library-search ability
               (QA backfill on old runs only)
  meta.json    schema, Forge version, source, counts; written LAST, so a
               directory without it is not an index

Legal posture (CLAUDE.md): this is derived from Forge's GPL card scripts, so it
is generated at runtime on the machine that has Forge and is NEVER committed
(.gitignore covers engine/forge_index/). The worker builds it at startup when
it is missing; the API container has no Forge and reads it from the shared
volume. Nothing here reimplements rules: it only reads names, layouts and the
AI's own do-not-play flag.

Stdlib only, like the rest of engine/.

CLI:
    py engine/forge_index.py build [--force]     # build for the local Forge
    py engine/forge_index.py status
    py engine/forge_index.py lookup "Winter, Cynical Opportunist"
    py engine/forge_index.py share <deck.dck> [...]   # flagged share of nonland cards
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Iterator

# Bump when the files' shape or the parsing rules change: an index built under
# another schema is rebuilt rather than trusted.
INDEX_SCHEMA = 1

DATA_DIR = Path(os.environ.get("MTG_DATA_DIR", str(Path(__file__).resolve().parent)))
INDEX_ROOT = DATA_DIR / "forge_index"
FILES = ("cards.json", "flags.json", "tutors.json")

# Where a Forge install may live. The worker image unpacks it at /opt/forge and
# points FORGE_JAR at a version-less symlink (/opt/forge/forge.jar), which is
# why the version is read from the symlink's TARGET.
FORGE_HOME_CANDIDATES = ("~/forge", "/opt/forge", "~/Forge")
JAR_RE = re.compile(r"forge-gui-desktop-(.+?)-jar-with-dependencies\.jar$")

# Forge names a split card "A // B"; every other multi-face layout by its
# first face (CardRules.getName). Only this mode keeps the joined name.
SPLIT_MODE = "Split"

# Lines that start a new face inside one script file.
_FACE_SEP = re.compile(r"^(?:ALTERNATE|SPECIALIZE:\w+)\s*$")
_MANA_APIS = {"Mana", "ManaReflected"}


# ---------------------------------------------------------------- discovery --

def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p))


def find_forge_home() -> Path | None:
    """The Forge install directory (the one holding res/), or None."""
    cands: list[Path] = []
    if os.environ.get("FORGE_HOME"):
        cands.append(_expand(os.environ["FORGE_HOME"]))
    if os.environ.get("FORGE_JAR"):
        jar = _expand(os.environ["FORGE_JAR"])
        cands += [jar.parent, Path(os.path.realpath(jar)).parent]
    cands += [_expand(c) for c in FORGE_HOME_CANDIDATES]
    for c in cands:
        if (c / "res" / "cardsfolder").is_dir():
            return c
    return None


def find_cardsfolder(forge_home: Path | None = None) -> Path | None:
    """cardsfolder.zip when it exists, else the unzipped folder of scripts."""
    home = forge_home or find_forge_home()
    if home is None:
        return None
    folder = home / "res" / "cardsfolder"
    z = folder / "cardsfolder.zip"
    if z.is_file():
        return z
    if folder.is_dir() and any(folder.rglob("*.txt")):
        return folder
    return None


def _safe_version(v: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", v)[:64] or "unknown"


def forge_version(forge_home: Path | None = None, source: Path | None = None) -> str:
    """Forge's release, read from the desktop jar's file name.

    FORGE_JAR first (resolving a symlink to its target), then any desktop jar
    in the install. With no jar at all, a stable tag derived from the card
    scripts' size and mtime, so a changed cardsfolder still gets its own index.
    """
    names: list[str] = []
    if os.environ.get("FORGE_JAR"):
        jar = _expand(os.environ["FORGE_JAR"])
        names += [os.path.realpath(jar), str(jar)]
    home = forge_home or find_forge_home()
    if home is not None:
        names += sorted(glob.glob(str(home / "forge-gui-desktop-*-jar-with-dependencies.jar")),
                        reverse=True)
    for n in names:
        m = JAR_RE.search(os.path.basename(n))
        if m:
            return _safe_version(m.group(1))
    src = source or find_cardsfolder(home)
    if src is not None and src.exists():
        st = src.stat()
        tag = hashlib.sha1(f"{st.st_size}:{int(st.st_mtime)}".encode()).hexdigest()[:10]
        return f"unknown-{tag}"
    return "unknown"


# ------------------------------------------------------------------ parsing --

def iter_scripts(source: Path) -> Iterator[tuple[str, str]]:
    """(relative file name, script text) for every card script in the source."""
    if source.is_file():
        with zipfile.ZipFile(source) as z:
            for info in z.infolist():
                if info.filename.endswith(".txt"):
                    yield info.filename, z.read(info).decode("utf-8", "replace")
        return
    for p in sorted(source.rglob("*.txt")):
        yield p.relative_to(source).as_posix(), p.read_text(encoding="utf-8", errors="replace")


def _params(ability: str) -> tuple[str, str, dict[str, str]]:
    """("SP"|"AB"|"DB"|"", api, {param: value}) for one ability string such as
    "SP$ ChangeZone | Origin$ Library | Destination$ Hand | ChangeType$ Card"."""
    parts = [p.strip() for p in ability.split("|")]
    via, api = "", ""
    params: dict[str, str] = {}
    for i, p in enumerate(parts):
        if "$" not in p:
            continue
        k, v = p.split("$", 1)
        k, v = k.strip(), v.strip()
        if i == 0 and k in ("SP", "AB", "DB"):
            via, api = k, v
        else:
            params[k] = v
    return via, api, params


def parse_script(text: str) -> list[dict]:
    """The faces of one card script, in order. Each face:
    {"name", "types", "abilities": [raw A: strings], "svars": {name: raw},
     "keywords": [raw K: strings], "commander_text": bool}.
    Whole-card keys (AlternateMode, AI hints) are read by build(), not here."""
    faces: list[dict] = []
    cur: dict | None = None

    def start() -> dict:
        f = {"name": None, "types": "", "abilities": [], "svars": {}, "keywords": [],
             "commander_text": False}
        faces.append(f)
        return f

    for raw in text.splitlines():
        line = raw.rstrip()
        if _FACE_SEP.match(line.strip()):
            cur = start()
            continue
        if cur is None:
            cur = start()
        if ":" not in line or line.startswith("#"):
            continue
        key, val = line.split(":", 1)
        if key == "Name":
            cur["name"] = val.strip()
        elif key == "CopyFaceFrom" and cur["name"] is None:
            # A few split cards borrow a face from another script
            # ("Start // Fire"); the borrowed face keeps its name.
            cur["name"] = val.strip()
        elif key == "Types":
            cur["types"] = val.strip()
        elif key == "A":
            cur["abilities"].append(val.strip())
        elif key == "SVar":
            if ":" in val:
                sname, body = val.split(":", 1)
                cur["svars"][sname.strip()] = body.strip()
        elif key == "K":
            cur["keywords"].append(val.strip())
            if "can be your commander" in val:
                cur["commander_text"] = True
        elif key == "Text" and "can be your commander" in val:
            cur["commander_text"] = True
    return [f for f in faces if f["name"]]


def _alternate_mode(text: str) -> str | None:
    m = re.search(r"^AlternateMode:(.*)$", text, re.M)
    return m.group(1).strip() if m else None


def canonical_name(faces: list[dict], mode: str | None) -> str:
    """The name Forge loads this card by."""
    if mode == SPLIT_MODE and len(faces) >= 2:
        return " // ".join(f["name"] for f in faces[:2])
    return faces[0]["name"]


def _is_land(types: str) -> bool:
    return bool(re.search(r"\bLand\b", types or ""))


def _commander_eligible(face: dict) -> bool:
    t = face.get("types") or ""
    if face.get("commander_text"):
        return True
    return "Legendary" in t.split() and ("Creature" in t.split() or "Background" in t.split())


def _flag_kinds(faces: list[dict]) -> list[str]:
    """What AiController's RemoveDeck filter takes away from this card.

    spell         casting it (a nonland face whose spell is not a counterspell)
    counterspell  its spell is a Counter, which Forge's counterspell pre-pass
                  still casts (175 of 178 flagged stock casts were these)
    activation    a non-mana activated ability (loyalty abilities included)
    mana          a mana ability
    commander     it could be a commander, so a deck led by it loses its general
    """
    kinds: set[str] = set()
    for f in faces:
        if not _is_land(f["types"]):
            first_sp = next((a for a in f["abilities"] if a.startswith("SP$")), None)
            if first_sp and _params(first_sp)[1] == "Counter":
                kinds.add("counterspell")
            else:
                kinds.add("spell")
        for a in f["abilities"]:
            via, api, _ = _params(a)
            if via != "AB":
                continue
            kinds.add("mana" if api in _MANA_APIS else "activation")
    if faces and _commander_eligible(faces[0]):
        kinds.add("commander")
    order = ("spell", "counterspell", "activation", "mana", "commander")
    return [k for k in order if k in kinds]


def _searches(faces: list[dict]) -> list[dict]:
    """Library-search abilities: ChangeZone with a library origin that picks by
    type (ChangeType) or hidden choice, not a Defined card; plus the keyword
    searches (Transmute, TypeCycling) that have no ChangeZone line."""
    out: list[dict] = []
    for f in faces:
        sources = [(a, None) for a in f["abilities"]] + list(
            (body, name) for name, body in f["svars"].items())
        for body, svar in sources:
            via, api, p = _params(body)
            if api not in ("ChangeZone", "ChangeZoneAll"):
                continue
            origin = p.get("Origin", "")
            if "Library" not in [o.strip() for o in origin.split(",")]:
                continue
            if "Defined" in p or not ("ChangeType" in p or p.get("Hidden") == "True"):
                continue
            rec = {"face": f["name"], "via": via or "?", "api": api, "origin": origin,
                   "destination": p.get("Destination", ""),
                   "change_type": p.get("ChangeType", ""),
                   "change_num": p.get("ChangeNum", "1")}
            if svar:
                rec["svar"] = svar
            if "LibraryPosition" in p:
                rec["library_position"] = p["LibraryPosition"]
            if via == "AB" and "Cost" in p:
                rec["cost"] = p["Cost"]
            out.append(rec)
        for k in f["keywords"]:
            parts = k.split(":")
            if parts[0] == "Transmute":
                out.append({"face": f["name"], "via": "K", "keyword": "Transmute",
                            "origin": "Library", "destination": "Hand",
                            "change_type": "Card.sameCMC", "cost": ":".join(parts[1:])})
            elif parts[0] == "TypeCycling" and len(parts) >= 2:
                out.append({"face": f["name"], "via": "K", "keyword": "TypeCycling",
                            "origin": "Library", "destination": "Hand",
                            "change_type": parts[1], "cost": ":".join(parts[2:])})
    return out


def build_data(source: Path) -> tuple[dict, dict, dict, dict]:
    """(cards, flags, tutors, counts) from every script in the source."""
    cards: dict[str, dict] = {}
    flags: dict[str, dict] = {}
    tutors: dict[str, list] = {}
    counts = {"scripts": 0, "cards": 0, "duplicates": 0, "flagged_all": 0,
              "flagged_random": 0, "tutors": 0, "unparsed": 0}
    for _fname, text in iter_scripts(source):
        counts["scripts"] += 1
        faces = parse_script(text)
        if not faces:
            counts["unparsed"] += 1
            continue
        mode = _alternate_mode(text)
        name = canonical_name(faces, mode)
        if name in cards:
            counts["duplicates"] += 1
            continue
        entry = {"mode": mode, "types": faces[0]["types"]}
        if len(faces) > 1:
            entry["faces"] = [f["name"] for f in faces]
        cards[name] = entry
        # AI hints belong to the whole card (CardRules), wherever the line sits.
        remove = set(re.findall(r"^AI:RemoveDeck:(\w+)", text, re.M))
        if "Random" in remove:
            counts["flagged_random"] += 1
        if "All" in remove:
            flags[name] = {"remove": "All", "kinds": _flag_kinds(faces),
                           "land": _is_land(faces[0]["types"])}
        s = _searches(faces)
        if s:
            tutors[name] = s
    counts["cards"] = len(cards)
    counts["flagged_all"] = len(flags)
    counts["tutors"] = len(tutors)
    return cards, flags, tutors, counts


# ------------------------------------------------------------------ writing --

def index_dir(version: str) -> Path:
    return INDEX_ROOT / _safe_version(version)


def _read_meta(d: Path) -> dict | None:
    try:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if meta.get("schema") != INDEX_SCHEMA:
        return None
    if not all((d / f).is_file() for f in FILES):
        return None
    return meta


def is_built(version: str) -> bool:
    return _read_meta(index_dir(version)) is not None


def build(source: Path, version: str, force: bool = False) -> Path:
    """Write the index for one Forge version. Atomic: files go to a temp
    directory that is renamed into place, meta.json last, so a reader never
    sees half an index."""
    final = index_dir(version)
    if not force and is_built(version):
        return final
    t0 = time.time()
    cards, flags, tutors, counts = build_data(source)
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{final.name}-", dir=INDEX_ROOT))
    try:
        head = {"schema": INDEX_SCHEMA, "forge_version": version}
        for fname, key, data in (("cards.json", "cards", cards),
                                 ("flags.json", "flags", flags),
                                 ("tutors.json", "tutors", tutors)):
            (tmp / fname).write_text(json.dumps({**head, key: data}, ensure_ascii=False),
                                     encoding="utf-8")
        meta = {**head, "source": str(source), "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "build_seconds": round(time.time() - t0, 2), "counts": counts}
        (tmp / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        if final.exists():
            shutil.rmtree(final, ignore_errors=True)
        try:
            os.replace(tmp, final)
        except OSError:
            if not is_built(version):   # lost a race to another builder: theirs stands
                raise
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    return final


def ensure_index(force: bool = False) -> dict:
    """Build the index for the local Forge if it is missing. Never raises:
    returns {"status": "ok"|"built"|"no_forge"|"error", ...}."""
    try:
        home = find_forge_home()
        source = find_cardsfolder(home)
        if source is None:
            return {"status": "no_forge", "message": "no Forge cardsfolder found"}
        version = forge_version(home, source)
        if not force and is_built(version):
            return {"status": "ok", "version": version, "path": str(index_dir(version))}
        path = build(source, version, force=force)
        meta = _read_meta(path) or {}
        return {"status": "built", "version": version, "path": str(path),
                "counts": meta.get("counts"), "seconds": meta.get("build_seconds")}
    except Exception as e:  # noqa: BLE001 — a broken index must never take a worker down
        return {"status": "error", "message": f"{type(e).__name__}: {e}"}


def ensure_index_async(log=print) -> threading.Thread:
    """ensure_index() on a daemon thread, so worker startup never waits on it."""
    def run() -> None:
        res = ensure_index()
        if res["status"] == "built":
            log(f"forge_index: built {res['version']} in {res.get('seconds')} s "
                f"({(res.get('counts') or {}).get('cards')} cards) at {res['path']}")
        elif res["status"] != "ok":
            log(f"forge_index: {res['status']}: {res.get('message', '')}")
    t = threading.Thread(target=run, name="forge-index", daemon=True)
    t.start()
    return t


# ------------------------------------------------------------------ reading --

def fold(name: str) -> str:
    """Case, accent and punctuation-insensitive key: "Lim-Dûl's Vault" and
    "lim-dul's vault" meet; "Æther" meets "Aether"."""
    s = (name or "").replace("Æ", "Ae").replace("æ", "ae")
    s = s.replace("’", "'").replace("‘", "'")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.casefold().split())


class ForgeIndex:
    """A loaded index. `resolve()` answers "what does Forge call this card?"."""

    def __init__(self, path: Path, meta: dict, cards: dict, flags: dict) -> None:
        self.path = path
        self.meta = meta
        self.version = meta.get("forge_version")
        self.cards = cards
        self.flags = flags
        self._tutors: dict | None = None
        self._fold: dict[str, str] = {}
        self._joined: dict[str, str] = {}
        self._face: dict[str, str] = {}
        ambiguous: set[str] = set()
        for name, e in cards.items():
            self._fold.setdefault(fold(name), name)
            faces = e.get("faces") or []
            if len(faces) > 1:
                self._joined.setdefault(fold(" // ".join(faces[:2])), name)
                for f in faces:
                    k = fold(f)
                    if self._face.setdefault(k, name) != name:
                        ambiguous.add(k)
        # "Fire" is a face of both Fire // Ice and Start // Fire: a lone face
        # that belongs to two cards names neither, so it resolves to nothing.
        for k in ambiguous:
            self._face.pop(k, None)

    def resolve(self, name: str) -> str | None:
        """Forge's own name for a pasted card name, or None when Forge does not
        know it. "Front // Back" of a transform/modal/battle/adventure card is
        its front face; a split card keeps "A // B"; a lone face resolves to the
        card it belongs to. A real card always beats a face of the same name."""
        n = (name or "").strip()
        if not n:
            return None
        if n in self.cards:
            return n
        k = fold(n)
        if k in self._fold:
            return self._fold[k]
        if k in self._joined:
            return self._joined[k]
        if " // " in n:
            front = fold(n.split(" // ", 1)[0])
            hit = self._fold.get(front) or self._face.get(front)
            if hit and len(self.cards[hit].get("faces") or []) > 1:
                return hit
            return None
        return self._face.get(k)

    def mode(self, forge_name: str) -> str | None:
        return (self.cards.get(forge_name) or {}).get("mode")

    def types(self, forge_name: str) -> str:
        return (self.cards.get(forge_name) or {}).get("types") or ""

    def flag(self, forge_name: str) -> dict | None:
        return self.flags.get(forge_name)

    def tutors(self) -> dict:
        if self._tutors is None:
            try:
                self._tutors = json.loads((self.path / "tutors.json").read_text(
                    encoding="utf-8")).get("tutors") or {}
            except (OSError, ValueError):
                self._tutors = {}
        return self._tutors


_loaded: dict[str, tuple[float, ForgeIndex]] = {}


def _candidate_dirs(version: str | None) -> list[Path]:
    if version:
        return [index_dir(version)]
    out: list[Path] = []
    home = find_forge_home()
    if home is not None:
        out.append(index_dir(forge_version(home)))
    # No local Forge (the API container): the newest complete index on the
    # shared volume, which the worker built for the Forge it runs.
    if INDEX_ROOT.is_dir():
        rest = [d for d in INDEX_ROOT.iterdir() if d.is_dir() and not d.name.startswith(".")]
        rest.sort(key=lambda d: (d / "meta.json").stat().st_mtime
                  if (d / "meta.json").is_file() else 0, reverse=True)
        out += [d for d in rest if d not in out]
    return out


def load_index(version: str | None = None) -> ForgeIndex | None:
    """The index for this machine's Forge (or the newest on the data volume),
    or None when none is built. Cheap to call repeatedly: a loaded index is
    reused until its meta.json changes."""
    for d in _candidate_dirs(version):
        meta = _read_meta(d)
        if meta is None:
            continue
        try:
            mtime = (d / "meta.json").stat().st_mtime
        except OSError:
            continue
        hit = _loaded.get(str(d))
        if hit and hit[0] == mtime:
            return hit[1]
        try:
            cards = json.loads((d / "cards.json").read_text(encoding="utf-8"))["cards"]
            flags = json.loads((d / "flags.json").read_text(encoding="utf-8"))["flags"]
        except (OSError, ValueError, KeyError):
            continue
        idx = ForgeIndex(d, meta, cards, flags)
        _loaded[str(d)] = (mtime, idx)
        return idx
    return None


# ------------------------------------------------------------ deck metrics --

def dck_entries(text: str) -> list[tuple[int, str, str]]:
    """(qty, name, section) for [Commander] and [Main] lines of a .dck body,
    with Forge's "|SET|art" suffix dropped."""
    out: list[tuple[int, str, str]] = []
    section = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.strip("[]").lower()
            continue
        if section not in ("main", "commander"):
            continue
        m = re.match(r"^(\d+)\s+(.+?)\s*$", line)
        if m:
            out.append((int(m.group(1)), m.group(2).split("|", 1)[0].strip(), section))
    return out


def flagged_share(idx: ForgeIndex, deck_texts: list[str]) -> dict:
    """Share of nonland card slots scripted AI:RemoveDeck:All, over decks.

    Counting rule (ported from the 2026-09 diagnosis, removedeck.py): every
    [Main] and [Commander] slot, weighted by quantity; a slot is a land when
    its front face is a Land (an MDFC with a spell front counts as nonland);
    names Forge does not know cannot be typed, so they are counted apart and
    left out of both numbers. On the 32 human_ceiling cEDH decks this gives
    285/2362 (12.1%), the diagnosis figure, with 2 unknown slots."""
    nonland = flagged = unknown = 0
    per_card: dict[str, int] = {}
    for text in deck_texts:
        for qty, name, _sec in dck_entries(text):
            forge = idx.resolve(name)
            if forge is None:
                unknown += qty
                continue
            if _is_land(idx.types(forge)):
                continue
            nonland += qty
            if idx.flag(forge):
                flagged += qty
                per_card[forge] = per_card.get(forge, 0) + qty
    return {"nonland": nonland, "flagged": flagged, "unknown": unknown,
            "share": round(flagged / nonland, 4) if nonland else 0.0,
            "top": sorted(per_card.items(), key=lambda kv: (-kv[1], kv[0]))[:25]}


# ---------------------------------------------------------------------- CLI --

def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "build":
        res = ensure_index(force="--force" in rest)
        print(json.dumps(res, indent=1))
        return 0 if res["status"] in ("ok", "built") else 1
    if cmd == "status":
        idx = load_index()
        if idx is None:
            print(json.dumps({"built": False, "root": str(INDEX_ROOT),
                              "forge_home": str(find_forge_home())}, indent=1))
            return 1
        print(json.dumps({"built": True, "path": str(idx.path), **idx.meta}, indent=1))
        return 0
    idx = load_index()
    if idx is None:
        print("no index built; run: py engine/forge_index.py build", file=sys.stderr)
        return 1
    if cmd == "lookup":
        name = " ".join(rest)
        forge = idx.resolve(name)
        print(json.dumps({"query": name, "forge_name": forge,
                          "card": idx.cards.get(forge) if forge else None,
                          "flag": idx.flag(forge) if forge else None,
                          "searches": idx.tutors().get(forge) if forge else None},
                         indent=1, ensure_ascii=False))
        return 0 if forge else 2
    if cmd == "share":
        paths = [p for a in rest for p in (glob.glob(a) or [a])]
        texts = [Path(p).read_text(encoding="utf-8", errors="replace") for p in paths]
        res = flagged_share(idx, texts)
        print(f"{len(paths)} decks: {res['flagged']}/{res['nonland']} nonland slots "
              f"flagged AI:RemoveDeck:All ({res['share']:.1%}); unknown to Forge: "
              f"{res['unknown']}")
        print("most common:", res["top"][:15])
        return 0
    print(f"unknown command: {cmd}\n{__doc__}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
