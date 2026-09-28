"use client";

/** Coaching — /results/[file]/coaching?deck=
 *  Renders the cached coach.report() for one deck of a run, or offers the
 *  single generate action. The verdict's win rate always appears beside its
 *  archetype baseline (enforced server-side), floor decks say so, and every
 *  suggested change carries its evidence tag. Markup reuses the v3 report
 *  wireframe's .telet / .st / .chg classes — no new CSS. */

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Chrome, EngineDown, Footer, PageDetails, useLlmLive, type TabDef } from "@/components/Chrome";
import { api, RateLimited } from "@/lib/api";
import type { CoachingReport, RunSummary } from "@/lib/types";
import { deckLabel, pct, runTitle, stripAi } from "@/lib/format";

const ST_CLASS = { running: "ok", partial: "warn", cold: "bad" } as const;
const ST_WORD = { running: "Running", partial: "Partial", cold: "Never fired" } as const;

function CoachingInner() {
  const params = useParams<{ file: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const file = decodeURIComponent(String(params?.file ?? ""));
  const enc = encodeURIComponent(file);
  const deckParam = searchParams.get("deck") ?? "";

  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [rep, setRep] = useState<CoachingReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [wait, setWait] = useState<number | null>(null);
  // The engine did not answer at all. fetch() rejects with a TypeError only
  // on a network failure ("Failed to fetch" in Chrome, "Load failed" in
  // Safari); an HTTP error from the engine is a plain Error. The raw browser
  // text used to render under a bare "coaching" heading.
  const [down, setDown] = useState(false);
  // Can this deployment generate at all? null while unknown, so a slow
  // /health never flashes a false blocker. Shared with the tab row, which
  // hides this page's tab while generation is off.
  const llmReady = useLlmLive();

  useEffect(() => {
    let live = true;
    api.runSummary(file).then((r) => live && setSummary(r)).catch((e: unknown) => {
      if (!live) return;
      if (e instanceof TypeError) setDown(true);
      else setErr(e instanceof Error ? e.message : String(e));
    });
    return () => {
      live = false;
    };
  }, [file]);

  const decks = (summary?.meta?.decks as string[] | undefined) ?? [];
  const deck = deckParam || decks[0] || "";
  // meta.decks are container paths. The engine sends exact names in
  // summary.deck_labels; deckLabel is the fallback for an older engine so a
  // deck picker can never render "/data/decks/skrat s revenge 239c6293".
  const deckLabels = (summary as { deck_labels?: string[] } | undefined)?.deck_labels ?? [];
  const labelFor = (d: string) => deckLabels[decks.indexOf(d)] ?? deckLabel(d);

  // The free, cache-only read on load and deck change.
  useEffect(() => {
    if (!deck) return;
    let live = true;
    setRep(null);
    setErr(null);
    setWait(null);
    api.coaching(file, deck).then((r) => live && setRep(r)).catch((e: unknown) => {
      if (!live) return;
      if (e instanceof RateLimited) {
        setWait(e.retryAfter);
        setErr(e.message);
      } else if (e instanceof TypeError) {
        setDown(true);
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
    });
    return () => {
      live = false;
    };
  }, [file, deck]);

  const generate = async () => {
    if (busy || !deck) return;
    setBusy(true);
    setErr(null);
    setWait(null);
    try {
      setRep(await api.coach(file, deck));
    } catch (e: unknown) {
      if (e instanceof RateLimited) {
        setWait(e.retryAfter);
        setErr(e.message);
      } else if (e instanceof TypeError) {
        setDown(true);
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  };

  const tabs: TabDef[] = [
    { label: "Overview", href: `/results/${enc}` },
    { label: "Telemetry", href: `/results/${enc}/telemetry${deck ? `?deck=${encodeURIComponent(deck)}` : ""}` },
    {
      label: "Coaching",
      href: `/results/${enc}/coaching${deck ? `?deck=${encodeURIComponent(deck)}` : ""}`,
      on: true,
    },
  ];

  const title = summary
    ? runTitle(((summary.meta?.decks as string[]) ?? []).map(labelFor), summary.commanders)
    : file.replace(/\.json$/, "");
  const deckName = labelFor(deck);

  const selector = (
    <select
      className="sel"
      value={deck}
      aria-label="Deck to coach"
      onChange={(e) =>
        router.replace(`/results/${enc}/coaching?deck=${encodeURIComponent(e.target.value)}`)
      }
    >
      {decks.map((d) => (
        <option key={d} value={d}>
          {labelFor(d)}
        </option>
      ))}
    </select>
  );

  const v = rep?.ok ? rep.verdict : undefined;

  return (
    <>
      <Chrome tabs={tabs} />
      <div className="page">
        <div className="head">
          <div>
            <h1>{deckName ? `${deckName} coaching` : "Coaching"}</h1>
            {/* The .dck filename led this line; it is in the details
                disclosure at the foot with the rest of the addresses. */}
            <div className="sub">
              {rep?.ok && rep.meta ? (
                <>
                  generated by <span className="mono">{rep.meta.model}</span>
                  <span className="sep">·</span>
                  one report per deck and gauntlet, cached
                </>
              ) : (
                <>one report per deck and gauntlet, cached</>
              )}
            </div>
          </div>
        </div>

        {down && <EngineDown onRetry={() => window.location.reload()} />}

        {err && (
          <p className="note">
            {err}
            {wait != null && (
              <>
                {". "}Try again in about <span className="mono">{wait}</span> s.
              </>
            )}
          </p>
        )}

        {rep?.ok && v ? (
          <>
            <p className="lede">
              <b>{v.headline}.</b> {v.prose} Measured here:{" "}
              <b>{pct(v.win_rate)}</b> of {rep.games} seat-rotated games against a{" "}
              <b>{v.baseline != null ? pct(v.baseline) : "not-yet-measured"}</b>{" "}
              {rep.archetype?.class ?? "deck"} archetype baseline
              {v.sim_is_floor && (
                <>
                  {", and "}this archetype&apos;s sim result is <b>a floor, not a verdict</b>
                </>
              )}
              .
            </p>

            <div className="cols">
              <section>
                <div className="sh">
                  <h2>Support chain</h2>
                  <span className="meta">{selector}</span>
                </div>
                <p className="sdesc">
                  Whether each piece of the plan fired in this run, as the coach read it.
                </p>
                <table className="telet">
                  <tbody>
                    {(rep.support_chain ?? []).map((row) => (
                      <tr key={row.link}>
                        <td className="nm">
                          {row.link}
                          <small>{row.reading}</small>
                        </td>
                        <td className="val">{row.measured}</td>
                        <td className="stc">
                          <span className={`st ${ST_CLASS[row.status]}`}>
                            <i />
                            {ST_WORD[row.status]}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div className="sh">
                  <h2>Matchups</h2>
                  <span className="meta">{rep.games} games, this pod</span>
                </div>
                <table className="telet">
                  <tbody>
                    {(rep.matchups ?? []).map((m) => (
                      <tr key={m.pod}>
                        <td className="nm">
                          {stripAi(m.pod)}
                          <small>{m.note}</small>
                        </td>
                        <td className="val">{pct(m.win_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              <section>
                <div className="sh">
                  <h2>Suggested changes</h2>
                  <span className="meta">evidence-tagged</span>
                </div>
                <p className="sdesc">
                  Each suggestion cites its evidence: this run&apos;s numbers, or theory.
                </p>
                <div>
                  {(rep.changes ?? []).map((c) => (
                    <div className="chg" key={`${c.action}-${c.card}`}>
                      <span className={`pm ${c.action === "add" ? "a" : "c"}`}>
                        {c.action === "add" ? "+" : "−"}
                      </span>
                      <div>
                        <div className="t">{c.card}</div>
                        <div className="r">
                          {c.reason} <span className="ev2">[{c.evidence}]</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="sh">
                  <h2>Play guide</h2>
                </div>
                {(rep.play_guide ?? []).map((line, i) => (
                  <p key={i} className="sdesc">
                    {line}
                  </p>
                ))}
              </section>
            </div>

            <p className="note">
              Written by a model from this run&apos;s summary, telemetry, and archetype
              classification only: {rep.archetype?.why ?? ""}. Engine and combo decks
              simulate below their real strength, so read low numbers as a floor when
              the machinery is running.
            </p>
          </>
        ) : rep && !rep.ok && rep.reason === "not generated" && llmReady === false ? (
          // Generation is off (production today). This used to render a
          // glowing primary quoting a price above a note saying the button
          // would fail and naming an env var. A feature that cannot work
          // shows no primary; the tab to this page is hidden too, so this is
          // only reached by a direct link.
          <>
            <p className="lede">
              Coaching isn&apos;t switched on for this server yet. The overview and
              telemetry for this sim work without it.
            </p>
            {/* No report for this deck, but another deck may have one cached
                from when generation was on. Without the picker it was
                reachable only by editing the URL. */}
            {decks.length > 1 && (
              <div className="btns">
                <span className="meta">{selector}</span>
              </div>
            )}
            {process.env.NODE_ENV !== "production" && (
              <p className="note">
                Dev builds only: the engine reports no model key. Set{" "}
                <span className="mono">MTG_LLM_API_KEY</span> in{" "}
                <span className="mono">deploy/.env</span> and redeploy to enable it.
              </p>
            )}
          </>
        ) : rep && !rep.ok && rep.reason === "not generated" && llmReady === null ? (
          // A moment, until /health answers: never flash a primary that the
          // next render may withdraw.
          <p className="note">Checking whether coaching is switched on…</p>
        ) : rep && !rep.ok && rep.reason === "not generated" ? (
          <>
            <p className="lede">
              No coaching report exists yet for <b>{deckName}</b> in this run. Generating
              one reads the run&apos;s telemetry and archetype locally, makes a single
              model call, and caches the result for everyone.
            </p>
            <div className="btns">
              <button className="btn pri" onClick={() => void generate()} disabled={busy}>
                {busy ? "Generating…" : "Generate coaching report (~$0.01, about 20 s)"}
              </button>
              <span className="meta">{selector}</span>
            </div>
          </>
        ) : rep && !rep.ok ? (
          <p className="note">
            The coach declined: {rep.reason}. Telemetry and the overview still work
            without it.
          </p>
        ) : (
          !err && !down && <p className="note">Checking for a cached report…</p>
        )}

        <PageDetails label="Run details">
          <div>{file}</div>
          {deck && <div>{deck}</div>}
        </PageDetails>
      </div>
      <Footer />
    </>
  );
}

export default function CoachingPage() {
  return (
    <Suspense fallback={null}>
      <CoachingInner />
    </Suspense>
  );
}
