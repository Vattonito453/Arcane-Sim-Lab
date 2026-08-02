"use client";

/** Rules assistant — /rules
 *  Ask a question, get an answer grounded ONLY in retrieved Comprehensive
 *  Rules excerpts (engine/rules_qa.py enforces citation grounding in code).
 *  Every cited number is a link that loads the full rule into the side panel
 *  via GET /rule/{n}. "Search the rules instead" is the zero-token path.
 *
 *  Layout reuses the replay theater's `.stage` grid: answer column plus a
 *  330px rule panel. One `.btn.pri` on the view — Ask. */

import { useEffect, useMemo, useState } from "react";
import { Chrome, Footer } from "@/components/Chrome";
import { api, RateLimited } from "@/lib/api";
import type { RuleHit, RuleLookup, RulesAnswer } from "@/lib/types";

const RULE_TOKEN = /\b\d{3}(?:\.\d+[a-z]?)?\b/g;

/** Turn cited rule numbers (and only those — the grounding set) into links. */
function linkify(
  text: string,
  cited: Set<string>,
  onRule: (n: string) => void,
): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const m of text.matchAll(RULE_TOKEN)) {
    const tok = m[0];
    if (!cited.has(tok) || m.index === undefined) continue;
    parts.push(text.slice(last, m.index));
    parts.push(
      <a
        key={key++}
        className="bl mono"
        href="#"
        onClick={(e) => {
          e.preventDefault();
          onRule(tok);
        }}
      >
        {tok}
      </a>,
    );
    last = m.index + tok.length;
  }
  parts.push(text.slice(last));
  return parts;
}

function HitList({ hits, onRule }: { hits: RuleHit[]; onRule: (n: string) => void }) {
  if (hits.length === 0) return <p className="note">No rules matched this search.</p>;
  return (
    <>
      {hits.map((h, i) => {
        const num = h.rule ? String(h.rule) : null;
        // Chunk text usually opens with its own rule number — the link
        // already shows it, so drop the duplicate.
        let text = String(h.text ?? "");
        if (num && text.startsWith(num)) text = text.slice(num.length).trimStart();
        return (
          <p key={num ?? i} className="sdesc">
            {num && (
              <>
                <a
                  className="bl mono"
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    onRule(num);
                  }}
                >
                  {num}
                </a>{" "}
              </>
            )}
            {text}
          </p>
        );
      })}
    </>
  );
}

export default function RulesPage() {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [resp, setResp] = useState<RulesAnswer | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [wait, setWait] = useState<number | null>(null);
  const [ruleN, setRuleN] = useState<string | null>(null);
  const [rule, setRule] = useState<RuleLookup | null>(null);
  const [rulesCount, setRulesCount] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    api.health().then((h) => live && setRulesCount(h.rules)).catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (!ruleN) return;
    let live = true;
    setRule(null);
    api.rule(ruleN).then((r) => live && setRule(r)).catch(() => live && setRule(null));
    return () => {
      live = false;
    };
  }, [ruleN]);

  const fail = (e: unknown) => {
    if (e instanceof RateLimited) {
      setWait(e.retryAfter);
      setErr(e.message);
    } else {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  /** Ask = cached read first (free), then the authed, quota'd generate. */
  const ask = async () => {
    const question = q.trim();
    if (!question || busy) return;
    setBusy(true);
    setErr(null);
    setWait(null);
    setResp(null);
    try {
      const cached = await api.askCached(question);
      if (cached.ok || cached.reason !== "not generated") {
        setResp(cached);
      } else {
        setResp(await api.ask(question));
      }
    } catch (e: unknown) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  /** The zero-token path: retrieval only, no generation. */
  const searchOnly = async () => {
    const question = q.trim();
    if (!question || busy) return;
    setBusy(true);
    setErr(null);
    setWait(null);
    try {
      const cached = await api.askCached(question);
      // Force the hits-only rendering even if an answer exists.
      setResp({ ...cached, ok: false, reason: "search only" });
    } catch (e: unknown) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const cited = useMemo(
    () => new Set((resp?.citations ?? []).map((c) => c.rule)),
    [resp],
  );

  return (
    <>
      <Chrome />
      <div className="page">
        <div className="head">
          <div>
            <h1>Rules assistant</h1>
            <div className="sub">
              Comprehensive Rules · <span className="mono">June 2026</span>
            </div>
          </div>
        </div>

        <p className="lede">
          Grounded in the June 2026 Comprehensive Rules:{" "}
          <b>{rulesCount != null ? rulesCount.toLocaleString("en-US") : "3,152"} numbered rules</b>,
          searched locally. Answers cite only retrieved rule text; a question the
          excerpts don&apos;t reach says so instead of guessing.
        </p>

        {/* One column until there is a rule to put in the second. The right
            rail used to render an empty 330px panel holding two paragraphs of
            apology for being empty — on mobile it stacked below the fold and
            said the same nothing. */}
        <div className={ruleN == null ? "stage stage--one" : "stage"}>
          <div>
            <section>
              <div className="sh">
                <h2>Ask a rules question</h2>
                              </div>
              <input
                className="txt"
                value={q}
                maxLength={500}
                placeholder="Is 19 commander damage lethal?"
                aria-label="Rules question"
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void ask();
                }}
              />
              <div className="btns">
                <button className="btn pri" onClick={() => void ask()} disabled={busy || !q.trim()}>
                  {busy ? "Working…" : "Ask"}
                </button>
                <button className="btn" onClick={() => void searchOnly()} disabled={busy || !q.trim()}>
                  Search the rules instead
                </button>
              </div>

              {wait != null && (
                <p className="note">
                  {err}. Try again in about <span className="mono">{wait}</span> s.
                </p>
              )}
              {err && wait == null && (
                <p className="note">
                  {err}
                  {err.includes("API key") &&
                    ". Asking generates a paid answer, so it needs the shared key; searching is free."}
                </p>
              )}
            </section>

            {resp && resp.ok && resp.answer && (
              <section>
                <div className="sh">
                  <h2>Answer</h2>
                  <span className="meta">
                    {resp.cached ? "from the cache" : `generated by ${resp.meta?.model ?? "the model"}`}
                  </span>
                </div>
                {resp.covered === false && (
                  <p className="sdesc">
                    <span className="st warn">
                      <i />
                      Not covered
                    </span>{": "}
                    the retrieved excerpts don&apos;t reach this question, so no answer is
                    offered. The closest rules are listed below.
                  </p>
                )}
                {resp.covered !== false && (
                  <p className="lede">{linkify(resp.answer, cited, setRuleN)}</p>
                )}
                <p className="note">
                  Answered only from the retrieved excerpts; every cited number was verified
                  against them before this was shown. Click a citation to read the full rule.
                </p>
              </section>
            )}

            {resp && !resp.ok && (
              <section>
                <div className="sh">
                  <h2>Matching rules</h2>
                  <span className="meta">
                    {resp.reason === "search only"
                      ? "retrieval only; no tokens spent"
                      : resp.reason === "no LLM configured"
                        ? "the engine has no model configured, so this is plain search"
                        : resp.reason}
                  </span>
                </div>
                {resp.reason === "citations not grounded" && (
                  <p className="sdesc">
                    <span className="st warn">
                      <i />
                      Answer withheld
                    </span>{": "}
                    the model cited rule numbers that were not in the retrieved text, twice.
                    Showing the retrieved rules instead of a possibly-wrong answer.
                  </p>
                )}
                <HitList hits={resp.hits ?? []} onRule={setRuleN} />
              </section>
            )}
          </div>

          {ruleN != null && (
            <div>
              <section>
                <div className="sh">
                  <h2>Rule text</h2>
                  <span className="meta mono">{ruleN}</span>
                  <span className="right">
                    <button className="rail-x" onClick={() => setRuleN(null)}>
                      Close
                    </button>
                  </span>
                </div>
                {rule == null && <p className="note">Loading rule {ruleN}…</p>}
                {rule?.error && <p className="note">{rule.error}</p>}
                {rule?.entries?.map((e) => (
                  <p key={e.rule} className="sdesc">
                    <span className="mono">{e.rule}</span> {e.text}
                  </p>
                ))}
              </section>
            </div>
          )}
        </div>

        {/* Attribution stays on the page whether or not a rule panel is open —
            the search hits quote rule text too. */}
        {/* Attribution is a legal obligation and stays. The two clauses that
            followed it just restated the lede. */}
        <p className="note">
          Rule text from the Magic: The Gathering Comprehensive Rules (June 2026),
          © Wizards of the Coast, quoted for reference.
        </p>
      </div>
      <Footer />
    </>
  );
}
