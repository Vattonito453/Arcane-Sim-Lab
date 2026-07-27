# 03 — AI rules assistant

**Why:** `frontend_handoff/API_SPEC.md` names this a required feature, and it is the
cheapest AI in the product: retrieval is already built, so the only spend is one
small-model synthesis per *distinct* question, cached globally forever
(`frontend_architecture.md` §2: ~$0.003 first ask, $0 after).

**Retrieval already exists. Do not build embeddings or a vector store.**
`Engine.search(query, k=8)` (`engine/mtg_engine.py` line 81) keyword-scores
`rules/kb/chunks.jsonl` and is exposed as `GET /search?q=&k=8`.
`Engine.rule(number)` (line 55) returns an exact rule plus its subrules
(`903.10` also yields `903.10a…`) and is exposed as `GET /rule/{n}`.
`web/lib/api.ts` already has `api.search()` and `api.rule()`, and
`web/lib/types.ts` already has `RuleHit` — all three are currently unused. Those
are your seams.

**Dependencies:** none on other tasks. **Coordinate with 01 Stage 3:** both need one
LLM provider call. Whichever ships first owns `engine/llm.py` (`complete(system,
user, *, model, api_key) -> str`, `MTG_LLM_API_KEY` / `MTG_LLM_MODEL` from env) and
the other imports it. Do not write a second provider shim.

**Size:** medium — a generation step, a cache, two endpoints, one new page.

**Done means:** the shared definition of done in `tasks/README.md` applies in full,
plus the acceptance criteria below.

---

## Non-negotiables

Read the "Rules RAG" section of `frontend_handoff/API_SPEC.md` (lines 50–81) in
full. Its grounding discipline is the whole feature:

- **Answer ONLY from the retrieved excerpts.** Cite rule numbers inline ("per
  903.10a"). If the excerpts do not cover the question, say so.
- **Never answer from model memory.** Rule *numbers* shift between Comprehensive
  Rules editions; the KB is the June 2026 CR. A confidently-cited wrong number is
  worse than "the excerpts don't cover this", because the user cannot tell.
- **Enforce it in code, not only in the prompt.** After generation, extract every
  `\d{3}(\.\d+[a-z]?)?` token from the answer and check it against the rule ids
  present in the retrieved chunk set. A citation that was not retrieved is a
  hallucinated number: drop the answer and retry once, then fail closed with
  `{"ok": false, "reason": "citations not grounded"}`. This check is the only
  reason to trust the output.
- **One call per distinct question, ever.** Cache before you generate.

**Legal** (CLAUDE.md, `frontend_architecture.md` §5): the KB is WotC Comprehensive
Rules text. Display excerpts with attribution; do **not** add a bulk-corpus
endpoint. API_SPEC's "Pattern B" (ship `chunks.jsonl` to the browser and score
locally) directly conflicts with CLAUDE.md's instruction to strip `rules/raw/` and
`rules/kb/` before the repo goes public — **build Pattern A only** and note why in
the code comment. Keep the Fan Content notice in the footer (`Footer` in
`web/components/Chrome.tsx` already does).

---

## Stage 1 — `engine/rules_qa.py`

- `retrieve(question: str, k: int = 8) -> list[dict]` — `Engine.search()`, plus
  `Engine.rule(n)` for every rule number detected in the question itself (API_SPEC
  step 2). Zero tokens. Note the honest scope: `search()` covers **3,887 retrieval
  chunks** built from rules *and* glossary terms; `all_rules.json` holds **3,152**
  numbered rules for exact lookup. They are different corpora — say which you hit.
  Also note `search()` truncates chunk text to 400 characters
  (`mtg_engine.py` line 98); if the prompt needs full text, call `Engine.rule()` for
  the cited numbers rather than raising the truncation limit for everyone.
- `normalize(question: str) -> str` — the cache key input. Document the exact steps
  in the docstring: NFKC, casefold, collapse internal whitespace, strip leading and
  trailing punctuation. Nothing lossier — do not stem or drop stopwords, because
  two questions that differ by one word can have opposite answers.
- `answer(question, *, refresh=False) -> dict` — cache-aware entry point.
  `key = sha256(normalize(question)).hexdigest()`, stored at
  `MTG_DATA_DIR/rules_answers/{key}.json`, matching the layout 01 Stage 3 uses for
  `MTG_DATA_DIR/coaching/{key}.json`. A hit makes **no** network call and returns
  `cached: true`.
- **Name the cache honestly.** §2 calls this a "semantic cache". What is buildable
  stdlib-only is a **normalized-question hash cache**: exact match after
  normalization, no embedding similarity. It delivers the "$0 after" economics for
  repeat askers and nothing more. Say this in the module docstring rather than
  implying paraphrase matching that is not there.
- No `MTG_LLM_API_KEY` → return `{"ok": false, "reason": "no LLM configured",
  "hits": [...]}` with the retrieved chunks still populated, so the UI degrades to
  a plain rules search instead of breaking. Never crash, never commit a key.
- Response schema (validate before caching; reject and retry once on malformed):

```python
{
  "ok": True,
  "question": str, "normalized": str, "key": str,
  "answer": str,                                   # prose, rule numbers inline
  "citations": [{"rule": "903.10a", "text": str}],  # every one present in `hits`
  "hits": [{"id": str, "rule": str, "score": int, "text": str}],
  "covered": bool,        # False when the model says the excerpts don't reach it
  "cached": False,
  "meta": {"model": str, "generated": iso8601, "kb": "June 2026 CR"},
}
```

**Verify:**

```bash
cd engine
# 1. Degrades with no key, makes no network call:
env -u MTG_LLM_API_KEY MTG_DATA_DIR=/tmp/mtgqa python3 -c "
import rules_qa; r = rules_qa.answer('is 19 commander damage lethal')
print(r['ok'], r['reason'], len(r['hits']))"        # False, 'no LLM configured', >0

# 2. Normalization collapses to one key (run with a key configured):
MTG_DATA_DIR=/tmp/mtgqa python3 -c "
import rules_qa
a = rules_qa.answer('Is 19 commander damage lethal?')
b = rules_qa.answer('is  19 commander damage lethal')
print(a['key'] == b['key'], a['cached'], b['cached'])"   # True False True
ls /tmp/mtgqa/rules_answers | wc -l                       # 1

# 3. Every citation is grounded:
MTG_DATA_DIR=/tmp/mtgqa python3 -c "
import rules_qa
r = rules_qa.answer('Is 19 commander damage lethal?')
ids = {h['rule'] for h in r['hits']}
assert all(c['rule'] in ids for c in r['citations']), r['citations']
print('grounded', len(r['citations']))"
```

Add the grounding assertion as a real test in `engine/tests/test_rules_qa.py`
driven by a **stubbed** `llm.complete` that returns a fabricated citation
(`"per 999.99z"`), so the rejection path is tested without spending a token.

## Stage 2 — endpoints

Follow the existing gate pattern in `engine/mtg_engine.py` exactly: `_authed()`
(line 432), `_rate_ok()` (line 223), `_deny()` (line 440), `client_key` (line 391).

- `GET /ask?q=...` — **cache-only.** Returns the stored answer, or
  `{"ok": false, "reason": "not generated", "hits": [...]}`. Public read, subject to
  the existing `READ_PER_MIN` gate. Never generates, so a crawler cannot spend
  money on GETs.
- `POST /ask` `{"q": "..."}` — generates. **Requires an API key** and its own quota:
  add `ASK_PER_HOUR = int(os.environ.get("MTG_ASK_PER_HOUR", "30"))` beside
  `SIM_PER_HOUR` (line 209), bucket `f"ask:{self.client_key}"`, window 3600. Add
  `MTG_ASK_PER_HOUR` to `deploy/.env.example` and `deploy/docker-compose.yml`.
- Extend the auth gate: line 521 reads
  `if route in ("simulate", "decks") and not self._authed()`. Add `"ask"`.
- Cap the question at 500 characters → 413. Reject empty → 400.
- Add `api.ask(q)` (POST) and `api.askCached(q)` (GET) to `web/lib/api.ts`, and
  `RulesAnswer` to `web/lib/types.ts`. `post()` already sends
  `Authorization: Bearer` from `apiKey()` — no client change needed for auth.
- Update the endpoint list in the `mtg_engine.py` module docstring (lines 13–25).
  It is the only route index that exists; leaving it stale is documented drift.

**Verify:**

```bash
MTG_DATA_DIR=/tmp/mtgdata MTG_API_KEYS=k1 MTG_EMBEDDED_WORKER=0 \
  python3 -u engine/mtg_engine.py serve 8484 &
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8484/ask \
  -H 'Content-Type: application/json' -d '{"q":"trample"}'                 # 401
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8484/ask \
  -H 'Authorization: Bearer k1' -H 'Content-Type: application/json' \
  -d '{"q":""}'                                                             # 400
curl -s "localhost:8484/ask?q=never+asked+before" | python3 -m json.tool    # ok:false, not generated
for i in $(seq 1 31); do curl -s -o /dev/null -w '%{http_code} ' -X POST localhost:8484/ask \
  -H 'Authorization: Bearer k1' -H 'Content-Type: application/json' -d '{"q":"q'$i'"}'; done
                                                                            # a 429 appears by #31
```

## Stage 3 — the page

New route `web/app/rules/page.tsx`, client component.

- **Navigation.** There is no route to it today: `web/app/page.tsx` renders bare
  `<Chrome />` with no tabs, and the topbar's `Feedback / Changelog / Docs` links in
  `web/components/Chrome.tsx` are hardcoded placeholders. Add a real tab row —
  `tabs={[{ label: "Runs", href: "/" }, { label: "Rules", href: "/rules" }]}` — on
  the home page and the new page, using the existing `.tabs`/`.tab` classes.
- **Layout: reuse `.stage`.** `globals.css` line 179 defines
  `.stage { display: grid; grid-template-columns: 1fr 330px; gap: 40px }` — the
  replay theater's side-panel grid. That is your answer column plus rule panel. Do
  not invent a drawer.
- Question box: `textarea.paste` or `input.txt` (both exist), a `.btn.pri` "Ask"
  as the view's **single** primary button, and a quiet `.btn` or text link for
  "Search the rules instead" which renders `hits` with no generation.
- Answer rendering: prose paragraphs. Convert each in-text rule number into
  `<a className="bl">` that loads `api.rule(n)` into the right column — API_SPEC
  step 4. Match only numbers that appear in `citations`, so the linkifier cannot
  manufacture a link to an ungrounded number.
- Right column: the selected rule's `entries` from `GET /rule/{n}`, each with its
  number in `.mono`, plus a line attributing the text to the Comprehensive Rules
  (June 2026). Empty state: the retrieved `hits` list, so the panel is never blank.
- `covered: false` → lead with a `.st.warn` "Not covered" line and the honest
  sentence that the retrieved excerpts do not reach the question, then show the
  hits. Do not pad with a guess.
- Prose lede on the page (Part 3 rule 6): computed, e.g. "Grounded in the June 2026
  Comprehensive Rules — 3,152 numbered rules, searched locally. Answers cite only
  retrieved text."
- Handle `RateLimited` and the 401 path (`api.ts` `fail()`, lines 43–60) the way
  the import page does. Note the drift: the 401 message says "set one under Engine"
  but no key-entry UI exists yet — task 06 builds sign-in. Until then the key comes
  from `NEXT_PUBLIC_API_KEY` or `localStorage["simlab.apiKey"]`; do not build a
  bespoke key form here that 06 will delete.

**Verify:**

```bash
cd web && npx tsc --noEmit && npx next build
grep -c "btn pri" app/rules/page.tsx        # exactly 1
git status --porcelain web/ | grep '\.css$'  # only globals.css, if anything
```

Then in the browser: ask a question, confirm each cited number is a blue link that
fills the right panel; confirm an uncovered question renders the warn line and the
hits; confirm asking the same question with different capitalisation returns
instantly and the network tab shows the cached response.

---

## Acceptance criteria

- [ ] Uses the existing `/search` and `/rule/{n}` retrieval — no embeddings, no vector store
- [ ] One LLM call per normalized question, globally cached under `MTG_DATA_DIR/rules_answers/`
- [ ] Normalization documented in a docstring; the cache is described as a
      normalized-question hash cache, not implied to be embedding-based
- [ ] Every citation in the response is verified present in the retrieved chunks;
      an ungrounded citation triggers one retry then fails closed
- [ ] `test_rules_qa.py` proves the rejection path with a stubbed provider, zero tokens
- [ ] No `MTG_LLM_API_KEY` → degraded response with hits, no crash, no network call
- [ ] `POST /ask` authenticated and quota'd (`MTG_ASK_PER_HOUR`); `GET /ask` public and cache-only
- [ ] `MTG_ASK_PER_HOUR` in `.env.example` and `docker-compose.yml`; `mtg_engine.py`
      docstring route list updated
- [ ] `/rules` page reachable from a real tab row; `.stage` grid reused for the side panel
- [ ] Exactly one `.btn.pri`; no new CSS file; prose lede; sentence case; no emoji
- [ ] Uncovered questions say so instead of guessing
- [ ] No bulk-corpus endpoint added (Pattern A only)
- [ ] `test_adapter.py` passes, `tsc` clean, `board.py` accuracy unregressed

## Out of scope

Embedding or paraphrase-similarity caching; streaming tokens; conversation history
or follow-up turns; a turn-structure visualiser (`GET /turn-structure` exists but is
its own feature); card-specific rulings from Scryfall; answering questions about a
specific simulated game — that is coaching, task 01.
