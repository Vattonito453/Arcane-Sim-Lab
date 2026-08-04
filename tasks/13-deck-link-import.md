# 13 — Import a deck from a Moxfield or Archidekt link

Today `POST /decks` only accepts pasted decklist text
(`engine/convert_decklist.py`) — a Moxfield/Arena/MTGO export a user copies by
hand. Most players don't copy-paste; they have a deck at a URL. Let the import
page accept `https://moxfield.com/decks/<id>` or
`https://archidekt.com/decks/<id>` directly and do the fetch+convert for them.

## What to build

1. **`engine/deck_import.py`** (new, stdlib-only per CLAUDE.md gotcha 6 — use
   `urllib.request`, not `requests`): given a URL, detect the host, hit that
   host's own public JSON API (Moxfield: `api.moxfield.com/v2/decks/all/{id}`;
   Archidekt: `www.archidekt.com/api/decks/{id}/`) and return `(card_lines,
   commander_name)` in the same shape `convert_decklist.parse()` already
   produces, so `_import_deck()` can hand off to the existing
   `convert_decklist.convert()` pipeline unchanged. **Confirm both response
   shapes empirically against a real public deck before coding the parser** —
   these are undocumented APIs and may not match what you remember; do not
   guess the schema.
2. **`mtg_engine.py` `_import_deck()`**: accept `payload["url"]` as an
   alternative to `payload["text"]`. When a URL is present, call
   `deck_import.fetch()` first, then feed the result through the same
   `convert()` call `text` already uses — one code path downstream of the
   fetch, not a parallel importer.
3. **Scryfall-etiquette parity for the new outbound call**: real `User-Agent`,
   one request per import (no pagination loops), and treat a non-200 or
   malformed response as a normal `{"ok": false, "error": ...}` — never a
   500, matching the existing tolerant-by-contract rule for pasted text.
4. **Web**: the import page's paste box gains a URL field (or auto-detects a
   pasted URL and switches modes) that calls the same `/decks` endpoint with
   `{url: ...}` instead of `{text: ...}`. No new primary button — importing
   by URL and importing by paste are the same action, one `.btn.pri`.
5. **Commander art still comes from Scryfall only.** Moxfield/Archidekt each
   have their own card-image CDNs; do not fetch or hotlink from them. The
   commander name returned by the importer flows into the existing `/cards`
   art-crop path like any other imported deck — this task adds a card *list*,
   not card art.

## What NOT to build

- No OAuth or authenticated access to either site's API — public deck links
  only, same trust level as a pasted list.
- No periodic re-sync of an imported deck if the source list changes later —
  import is a one-time snapshot, same as paste-to-import today.
- No scraping the HTML deck page. If a site has no public JSON endpoint,
  don't reverse-engineer one from the DOM — treat that host as unsupported
  and say so in the error.

## Acceptance criteria

- [ ] Pasting a real public Moxfield deck URL into the import page produces
      the same validated `.dck` + report shape as pasting that deck's text
      export would.
- [ ] Same for a real public Archidekt deck URL.
- [ ] An unrecognized host, a private/deleted deck, or a malformed response
      returns `{"ok": false, "error": ...}` — never a 500, never a partial
      `.dck` written to disk.
- [ ] `engine/deck_import.py` has no third-party dependency — `urllib.request`
      and stdlib `json` only.
- [ ] `test_adapter.py` still passes; a new fixture-based unit test covers the
      Moxfield and Archidekt response-parsing paths without a live network
      call (record a real response once as a fixture, don't hit the network
      in CI).
- [ ] `cd web && npm run verify` clean; still exactly one `.btn.pri` on the
      import page.

## Verification

```bash
python3 engine/tests/test_adapter.py
python3 -c "
import deck_import, sys
sys.path.insert(0, 'engine')
" 2>/dev/null  # replace with the real fixture-based unit test once written
cd web && npm run verify
# manual: paste a real Moxfield deck URL and a real Archidekt deck URL into
# /import, confirm both convert and the resulting deck appears in /new with
# commander art resolved
```
