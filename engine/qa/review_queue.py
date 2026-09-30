"""The review queue: flagged moments waiting for a player's judgement.

Repair plan WS2 layer A, task 4 (tasks/25-repair-plan.md). Two writers, one
reader:

  human/<id>.json   "Flag this moment" (POST /flags, mtg_engine.write_flag):
                    a playtester's note on a replay moment. Holds a person's
                    words, so nothing public ever serves it.
  auto/<id>.json    QA layer A (engine/qa/run.py, via enqueue() below): the
                    detector flags of one run at or above a severity
                    threshold, at most CAP_PER_RUN per run, stratified by
                    detector so one noisy detector cannot fill the queue.
  done/<id>.json    triaged items, moved here by whoever judged them (layer B,
                    or Vincent by hand). Never listed; an auto item already
                    here is not queued again, and it still counts toward its
                    run's cap.

All under $MTG_DATA_DIR/simkb/review_queue/.

read_queue() is GET /qa/queue (a reviewer key from MTG_REVIEW_KEYS only; an
API key is refused because the web build inlines one): human flags first, then auto
flags (across pages, not only within one), paged by a cursor holding one
watermark per queue on each file's write time (see read_queue for why a
two-second settle window makes each watermark exact).

Stdlib only, like the rest of engine/.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

REVIEW_SCHEMA = "simlab.review/1"
CAP_PER_RUN = 30
SEVERITIES = ("low", "medium", "high")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}
# What "above a severity threshold" means by default: medium and high are
# queued, low (analyzer limitations such as an undated knockout) is not.
# MTG_QA_QUEUE_MIN_SEVERITY overrides it (low | medium | high).
DEFAULT_MIN_SEVERITY = "medium"
MIN_SEVERITY_ENV = "MTG_QA_QUEUE_MIN_SEVERITY"
# The queue's priority field: human flags rank first (WS2 layer A task 4).
PRIORITY = {"human": 1, "high": 2, "medium": 3, "low": 4}
# A file younger than this is held back from GET /qa/queue until the next
# pull (read_queue explains why). Seconds.
SETTLE_SECONDS = 2.0
DEFAULT_PAGE = 500


def root(data_dir: str | Path) -> Path:
    return Path(data_dir) / "simkb" / "review_queue"


def min_severity(env: dict | None = None) -> str:
    env = os.environ if env is None else env
    v = (env.get(MIN_SEVERITY_ENV) or "").strip().lower()
    return v if v in SEVERITY_RANK else DEFAULT_MIN_SEVERITY


def _rank(flag: dict) -> int:
    return SEVERITY_RANK.get(flag.get("severity") or "low", 0)


def _order(flag: dict) -> tuple:
    a = flag.get("anchor") or {}
    return (-_rank(flag), a.get("game") or 0, a.get("turn") or 0, flag.get("id") or "")


def eligible(flags: list[dict], threshold: str = DEFAULT_MIN_SEVERITY) -> list[dict]:
    floor = SEVERITY_RANK.get(threshold, SEVERITY_RANK[DEFAULT_MIN_SEVERITY])
    return [f for f in flags if _rank(f) >= floor and f.get("id")]


def stratify(flags: list[dict], cap: int) -> list[dict]:
    """At most `cap` flags, taken round-robin across detectors.

    Within a detector, most severe first, then earliest (game, turn). The
    detectors take turns in order of their most severe flag, then by name,
    so a detector with 200 flags and one with 3 yield 3 each before the
    first gets a fourth. Deterministic, so a re-run picks the same flags."""
    if cap <= 0:
        return []
    groups: dict[str, list[dict]] = {}
    for f in flags:
        groups.setdefault(f.get("detector") or "?", []).append(f)
    for g in groups.values():
        g.sort(key=_order)
    order = sorted(groups, key=lambda d: (-_rank(groups[d][0]), d))
    picked: list[dict] = []
    depth = 0
    while len(picked) < cap:
        took = False
        for d in order:
            if depth < len(groups[d]):
                picked.append(groups[d][depth])
                took = True
                if len(picked) >= cap:
                    break
        if not took:
            break
        depth += 1
    return picked


def _atomic_json(path: Path, obj: dict) -> None:
    """Temp file in the same directory, fsync, os.replace: a reader sees no
    file or a whole one, never half of one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=1, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    # Stamp the write time AFTER the rename, so the queue's watermark (the
    # file's time) is never earlier than the moment the file became visible.
    try:
        os.utime(path, None)
    except OSError:
        pass


def _stamp(st: os.stat_result) -> int:
    """When a queue file became visible, in ns. On POSIX a rename updates the
    inode's ctime, so max(mtime, ctime) is at least the rename time even for
    a writer that does not re-stamp after renaming (POST /flags). On Windows
    st_ctime is the creation time, which says nothing about the rename."""
    if os.name == "nt":
        return st.st_mtime_ns
    return max(st.st_mtime_ns, st.st_ctime_ns)


def _queued_ids(qroot: Path, stem: str) -> set[str]:
    """Ids already filed for this run, in auto/ or done/ (by name prefix, not
    glob: a result stem is a plain name, but a glob would read any '[' in it
    as a pattern)."""
    prefix = stem + "#"
    out: set[str] = set()
    for sub in ("auto", "done"):
        d = qroot / sub
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            if n.startswith(prefix) and n.endswith(".json"):
                out.add(n[:-5])
    return out


def item_for(flag: dict, doc: dict, created: str) -> dict:
    """The auto queue record for one qa.json flag."""
    anchor = flag.get("anchor") or {}
    sev = flag.get("severity") or "low"
    return {
        "schema": REVIEW_SCHEMA,
        "id": flag["id"],
        "source": f"detector:{flag.get('detector')}",
        "run": doc.get("run"),
        "anchor": anchor,
        "deck": flag.get("deck"),
        "player": anchor.get("player"),
        "priority": PRIORITY.get(sev, PRIORITY["low"]),
        "severity": sev,
        "detector": flag.get("detector"),
        "kind": flag.get("kind"),
        "trust": flag.get("trust"),
        "card": flag.get("card"),
        "detail": flag.get("detail"),
        "evidence": flag.get("evidence") or [],
        "detector_version": flag.get("detector_version"),
        "analyzer": doc.get("analyzer"),
        "created": created,
    }


def enqueue(doc: dict, data_dir: str | Path, *, cap: int = CAP_PER_RUN,
            threshold: str | None = None) -> dict:
    """File one run's eligible flags in review_queue/auto/. Idempotent: an
    id already in auto/ or done/ is never written again, and what is already
    filed for the run counts toward its cap. Returns what it did."""
    threshold = threshold or min_severity()
    stem = doc.get("run_stem") or ""
    qroot = root(data_dir)
    elig = eligible(doc.get("flags") or [], threshold)
    already = _queued_ids(qroot, stem) if stem else set()
    fresh = [f for f in elig if f["id"] not in already]
    picks = stratify(fresh, cap - len(already))
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for f in picks:
        _atomic_json(qroot / "auto" / f"{f['id']}.json", item_for(f, doc, created))
    by_det: dict[str, int] = {}
    for f in picks:
        by_det[f.get("detector") or "?"] = by_det.get(f.get("detector") or "?", 0) + 1
    return {"threshold": threshold, "cap": cap, "eligible": len(elig),
            "already_queued": len(already), "written": len(picks),
            "written_by_detector": by_det}


# ------------------------------------------------------------ the reader --

def parse_cursor(raw: str | None) -> tuple[int, int]:
    """GET /qa/queue's cursor -> (human watermark, auto watermark), ns.

    "" or absent = from the start. A previous page's cursor is "<human>.<auto>"
    (each a decimal ns watermark); a bare number is both. ValueError
    otherwise."""
    if raw is None or raw == "":
        return (0, 0)
    parts = raw.strip().split(".")
    if len(parts) not in (1, 2) or not all(
            x and len(x) <= 20 and all("0" <= c <= "9" for c in x) for x in parts):
        raise ValueError("since must be a cursor returned by /qa/queue")
    h = int(parts[0])
    return (h, int(parts[1]) if len(parts) == 2 else h)


def _oldest(entries: list, limit: int) -> list:
    """The oldest `limit` entries (sorted by stamp), extended so a page never
    splits entries that share one stamp: the next page starts after the
    cursor, so a split group would lose its second half."""
    if limit <= 0:
        return []
    page = entries[:limit]
    while len(page) < len(entries) and page and entries[len(page)][0] == page[-1][0]:
        page.append(entries[len(page)])
    return page


def read_queue(data_dir: str | Path, since=(0, 0), limit: int = DEFAULT_PAGE,
               now_ns: int | None = None) -> dict:
    """Open review items written after `since`: human flags first, then auto.

    Each queue has its own watermark on the time each file became visible
    (_stamp, ns); `since` is (human, auto) as parse_cursor returns it, or one
    number for both. Every writer builds the file under a temporary name and
    renames it into place, and the stamp is taken at or after the rename;
    items younger than SETTLE_SECONDS are still held for the next pull, so a
    watermark never passes a time at which a file could be on its way in and
    nothing is skipped.

    A page is every pending human flag first (the oldest `limit` of them),
    then, in what room is left, the oldest pending auto items; a group
    sharing one stamp is never split. So human flags come first ACROSS pages,
    not just within one: a human flag written after hundreds of auto items
    is still on the next page pulled. Within the page human flags are in
    write order and auto items by priority. Clients should still
    de-duplicate by id: an item that is rewritten gets a new stamp and is
    served again."""
    since_h, since_a = (since, since) if isinstance(since, int) else since
    qroot = root(data_dir)
    now_ns = time.time_ns() if now_ns is None else now_ns
    settled = now_ns - int(SETTLE_SECONDS * 1e9)
    pending: dict[str, list[tuple[int, str, Path]]] = {"human": [], "auto": []}
    held = 0
    for source, floor in (("human", since_h), ("auto", since_a)):
        d = qroot / source
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            if not n.endswith(".json") or n.startswith("."):
                continue
            p = d / n
            try:
                mt = _stamp(p.stat())
            except OSError:
                continue
            if mt <= floor:
                continue
            if mt > settled:
                held += 1
                continue
            pending[source].append((mt, n, p))
        pending[source].sort()
    limit = max(1, int(limit))
    page_h = _oldest(pending["human"], limit)
    page_a = _oldest(pending["auto"], limit - len(page_h))
    more = len(page_h) < len(pending["human"]) or len(page_a) < len(pending["auto"])
    cursor_h = page_h[-1][0] if page_h else since_h
    cursor_a = page_a[-1][0] if page_a else since_a
    human: list[dict] = []
    auto: list[dict] = []
    unreadable = 0
    for source, page in (("human", page_h), ("auto", page_a)):
        for mt, _n, p in page:
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                unreadable += 1
                continue
            if not isinstance(rec, dict):
                unreadable += 1
                continue
            rec = dict(rec, queue=source,
                       queued_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mt / 1e9)))
            if source == "human":
                rec.setdefault("priority", PRIORITY["human"])
                human.append(rec)
            else:
                auto.append(rec)
    human.sort(key=lambda r: (str(r.get("created") or ""), str(r.get("id") or "")))
    auto.sort(key=lambda r: (r.get("priority") or 9, str(r.get("created") or ""),
                             str(r.get("id") or "")))
    return {"items": human + auto, "cursor": f"{cursor_h}.{cursor_a}", "more": more,
            "counts": {"human": len(human), "auto": len(auto)},
            "held_for_settle": held, "unreadable": unreadable}
