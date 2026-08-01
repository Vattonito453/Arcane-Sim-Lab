# 11 — Card art coverage audit and fix

Some cards render without art (name-only tiles) in the replay and anywhere
else faces show. Reported from live use 2026-08-01. The fix is an audit
first — there are at least four distinct ways art goes missing, and they need
different fixes. Do not "switch to a different API"; the Scryfall path and
its etiquette (batched, cached, hotlinked) are correct and stay.

## Known ways art can be missing (check each, measure before fixing)

1. **Stale cache entries.** `engine/cards.py` `_slim()` keeps `art_crop` /
   `normal`, but entries written before those fields existed sit in the disk
   cache forever with no image URLs — `fetch_missing()` skips any cached key.
   Fix: on load (or via a one-shot `python3 engine/cards.py refresh`),
   re-queue cache entries lacking `normal` for refetch. Add a cache format
   version so this class of staleness can't recur silently.
2. **The `_offline` latch.** One Scryfall failure sets `_offline = True` for
   the process lifetime, so a transient blip at startup makes every later
   lookup cache-only until restart. Fix: let it retry after a cooldown, and
   surface offline state in `/health` so the UI can say so instead of
   silently degrading.
3. **DFC / faces edge cases.** `_slim()` reads the front face's
   `image_uris`; verify meld cards, adventures, and split cards actually
   yield a `normal` URL, and add the fallback if any class doesn't.
4. **Normalization misses.** Names that fail `normalizeName` round-tripping
   (client and server MUST agree) land in `missing` and never retry. Compare
   `web/lib/cards.ts normalizeName` against `engine/cards.py normalize_name`
   on the full cache key set; any divergence is a bug.

Also: `web/lib/cards.ts loadCards()` swallows fetch errors (`catch { break }`)
by design, but nothing tells the user art degraded. Add a quiet honesty note
when a load returned no faces for cards we expected to resolve.

## What "live Scryfall" means here

Not a new integration — verification that the existing one is reachable and
warm in every environment we run:

- Local dev, and the worker/API containers (egress + User-Agent intact).
- `/health` (or a small `/cards/status`) reports cache size, entries missing
  `normal`, and offline state, so "is art working" is checkable without
  clicking through a replay.

## Acceptance criteria

- [ ] A measured before/after: N cache entries lacked `normal` before,
      0 after refresh (record N in this file).
- [ ] `_offline` recovers without a process restart; offline state visible
      in `/health`.
- [ ] normalizeName parity test between `web/lib/cards.ts` and
      `engine/cards.py` (same inputs, same keys) added to the test suite.
- [ ] Scryfall etiquette unchanged: batched ≤75, ~8 req/s, real User-Agent,
      disk cache, zero network when warm. Images stay hotlinked, never
      rehosted.
- [ ] Replay of the fixture with a warm cache shows art for every
      non-token, non-Unidentified permanent.
- [ ] `python3 engine/tests/test_adapter.py` and smoke test still pass.

## Verification

```bash
python3 engine/tests/test_adapter.py
python3 engine/tests/smoke_test.py            # API up
python3 - <<'EOF'
# count cache entries with no image URL — the before/after number
import json, importlib.util, pathlib, sys
sys.path.insert(0, "engine"); import cards
cache = cards._load()
bad = [k for k, v in cache.items() if not v.get("normal")]
print(f"{len(bad)}/{len(cache)} entries lack a 'normal' image URL")
EOF
cd web && npm run verify
```
