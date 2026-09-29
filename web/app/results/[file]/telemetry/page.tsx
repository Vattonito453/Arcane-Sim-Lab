"use client";

/** Win-condition telemetry — /results/[file]/telemetry?deck=
 *  Renders deck_telemetry.compute() for one deck of a run: did the plan
 *  actually fire? Computed server-side (GET /results/{file}/telemetry) so the
 *  browser never downloads the multi-megabyte run file.
 *
 *  Statuses (healthy / partial / cold) come from documented thresholds in
 *  engine/deck_telemetry.py and are mapped to .st classes here — never
 *  recomputed, so this page and the coach always agree. */

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Chrome, Footer, PageDetails, type TabDef } from "@/components/Chrome";
import { api, RateLimited } from "@/lib/api";
import type { RunSummary, TelemetryReport, TelemetryStatus } from "@/lib/types";
import { deckLabel, plural, runTitle, shortName, stripAi } from "@/lib/format";
import { standingsOf } from "@/lib/standings";
import { LoadError } from "@/components/LoadError";

const ST_CLASS = { healthy: "ok", partial: "warn", cold: "bad" } as const;
const ST_WORD = { healthy: "Healthy", partial: "Partial", cold: "Never fired" } as const;

/** Why a row has no verdict: Forge's AI doesn't cast the card on its own. */
const AI_SKIPS_NOTE = "Forge's AI doesn't cast it on its own";

function Status({ s }: { s: TelemetryStatus }) {
  // No verdict, so no status shape either: a card Forge's AI doesn't cast
  // on its own is neither healthy nor cold, and never a cut candidate.
  if (s === "ai_skips") return <span className="st-na">Not judged</span>;
  return (
    <span className={`st ${ST_CLASS[s]}`}>
      <i />
      {ST_WORD[s]}
    </span>
  );
}

function TelemetryInner() {
  const params = useParams<{ file: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const file = decodeURIComponent(String(params?.file ?? ""));
  const enc = encodeURIComponent(file);
  const deckParam = searchParams.get("deck") ?? "";
  const watchStr = searchParams.get("watch") ?? "";

  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [rep, setRep] = useState<TelemetryReport | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [wait, setWait] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    api
      .runSummary(file)
      .then((r) => live && setSummary(r))
      .catch((e: unknown) => {
        if (!live) return;
        if (e instanceof RateLimited) {
          setWait(e.retryAfter);
          setErr(e.message);
        } else {
          setErr(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      live = false;
    };
  }, [file]);

  const decks = (summary?.meta?.decks as string[] | undefined) ?? [];
  const deck = deckParam || decks[0] || "";
  // Telemetry turns are Forge's global counter (every seat's turn counts);
  // players count table turns, so divide by the pod size.
  const tableTurn = (forgeTurn: number) => Math.ceil(forgeTurn / Math.max(1, decks.length));
  // meta.decks are container paths. The engine sends exact names in
  // summary.deck_labels; deckLabel is the fallback for an older engine so a
  // deck picker can never render "/data/decks/skrat s revenge 239c6293".
  const deckLabels = (summary as { deck_labels?: string[] } | undefined)?.deck_labels ?? [];
  const labelFor = (d: string) => deckLabels[decks.indexOf(d)] ?? deckLabel(d);

  useEffect(() => {
    if (!deck) return;
    let live = true;
    setRep(null);
    const watch = watchStr.split("|").map((s) => s.trim()).filter(Boolean);
    api
      .runTelemetry(file, deck, watch)
      .then((r) => live && setRep(r))
      .catch((e: unknown) => {
        if (!live) return;
        if (e instanceof RateLimited) {
          setWait(e.retryAfter);
          setErr(e.message);
        } else {
          setErr(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      live = false;
    };
  }, [file, deck, watchStr]);

  // Both tab hrefs are real destinations; the deck stays in the URL so the
  // view is addressable and survives the round trip through Overview.
  const tabs: TabDef[] = [
    { label: "Overview", href: `/results/${enc}` },
    {
      label: "Telemetry",
      href: `/results/${enc}/telemetry${deck ? `?deck=${encodeURIComponent(deck)}` : ""}`,
      on: true,
    },
    {
      label: "Coaching",
      href: `/results/${enc}/coaching${deck ? `?deck=${encodeURIComponent(deck)}` : ""}`,
    },
  ];

  // The run's one title, in the run page's order (the engine's standings)
  // and never the result filename, which is an address: it sat in the h1
  // while the page loaded.
  const st = summary ? standingsOf(summary, summary.games.flatMap((g) => g.players)) : null;
  const title = summary
    ? runTitle(
        st?.decks.map((d) => d.deck) ?? ((summary.meta?.decks as string[]) ?? []).map(labelFor),
        summary.commanders,
      )
    : "Sim results";

  if (err) {
    return (
      <>
        <Chrome tabs={tabs} />
        <div className="page">
          <div className="head">
            <div>
              <h1>{title}</h1>
              <div className="sub">{wait != null ? "Rate limited" : "Could not load telemetry"}</div>
            </div>
          </div>
          <LoadError err={err} wait={wait} what="run's telemetry" />
        </div>
        <Footer />
      </>
    );
  }
  if (!summary || !rep) {
    return (
      <>
        <Chrome tabs={tabs} />
        <div className="page">
          <div className="head">
            <div>
              <h1>{title}</h1>
              <div className="sub">Loading telemetry…</div>
            </div>
          </div>
        </div>
        <Footer />
      </>
    );
  }

  const games = rep.games;
  const rotated = rep.source === "rotated";
  const gameWord = rotated ? "seat-rotated games" : "games";
  const cmd = rep.commander;
  const castGames = cmd ? Math.round(cmd.cast_rate * games) : 0;
  const coldWatched = rep.watched.filter((w) => w.status === "cold");
  // "ai_skips" replaces "cold" only, so these rows also logged zero events:
  // the lede must not count them as cards that showed up.
  const unseenSkipped = rep.watched.filter((w) => w.status === "ai_skips");
  // Rows on this page about a card Forge's AI doesn't cast on its own.
  const skippedShown = [
    ...(cmd?.ai_wont_play ? [cmd.name] : []),
    ...rep.watched.filter((w) => w.ai_wont_play).map((w) => w.name),
  ];
  const skippedAll = rep.ai_wont_play ?? null;
  // One name per deck (shortName), the name the run title and stories use.
  const allLabels = decks.map(labelFor);
  const oneName = (label: string) => shortName(label, allLabels, summary.commanders);
  const deckName = oneName(stripAi(rep.player_key ?? "") || labelFor(rep.deck));
  // The lede's second sentence, from the damage table below: a sum by source
  // name over the run (same-named tokens add up), so it says "the most damage".
  // The unit is spelled out: a bare "(99)" after a card name reads as Forge's
  // instance-id syntax, the machine text this page no longer prints.
  const topSrc = rep.deaths.by_source[0];
  const deathLine = topSrc
    ? `Across the run, the most damage dealt to it came from ${topSrc.source} (${topSrc.damage} damage).`
    : "";

  return (
    <>
      <Chrome tabs={tabs} />
      <div className="page">
        <div className="head">
          <div>
            <h1>{deckName} telemetry</h1>
            {/* The .dck filename used to lead this line; it is in the details
                disclosure at the foot with the rest of the addresses. */}
            <div className="sub">
              <span className="mono">{games}</span> {games === 1 ? "game" : "games"} in this run
              <span className="sep">·</span>
              {/* The published denominator: decided games (engine/standings.py). */}
              won <span className="mono">{rep.wins}</span> of{" "}
              <span className="mono">{rep.decided ?? games}</span>
              {rep.decided != null ? " decided" : ""}
              <span className="sep">·</span>
              {rotated ? "seat-rotated" : "fixed seats"}
            </div>
          </div>
        </div>

        <p className="lede">
          {cmd ? (
            <>
              <b>{cmd.name}</b> was cast in <b>{castGames} of {games}</b> {gameWord}
              {cmd.median_turn != null && (
                <>
                  , first arriving on median turn <b>{tableTurn(cmd.median_turn)}</b>
                </>
              )}
              {cmd.ai_wont_play && <> ({AI_SKIPS_NOTE})</>}
              .{" "}
            </>
          ) : (
            <>
              No commander could be identified for this deck: its deck file lists none, or the file
              is no longer on the server and the run did not record one.{" "}
            </>
          )}
          {/* The table-wide charge-counter and proliferate figures that used
              to follow here are gone (repair plan WS11 task 8): they were one
              archetype's metrics, counted across every seat, and read the same
              for a reanimator deck as for Atraxa. */}
          {rep.watched.length > 0 && (
            <>
              {coldWatched.length > 0 ? (
                <>
                  <b>{coldWatched.length} of {plural(rep.watched.length, "watched card")}</b> never
                  fired
                  {unseenSkipped.length > 0 && (
                    <>
                      , and {unseenSkipped.length} more never showed up that Forge&apos;s AI
                      doesn&apos;t cast on its own
                    </>
                  )}
                  .
                </>
              ) : unseenSkipped.length > 0 ? (
                <>
                  <b>{unseenSkipped.length} of {plural(rep.watched.length, "watched card")}</b>{" "}
                  never showed up, and Forge&apos;s AI doesn&apos;t cast{" "}
                  {unseenSkipped.length === 1 ? "it" : "them"} on its own.
                </>
              ) : (
                <>All {plural(rep.watched.length, "watched card")} showed up.</>
              )}{" "}
            </>
          )}
          {deathLine}{" "}
          {!rotated && (
            <>This run is <b>not seat-rotated</b>, so its outcomes are not seat-comparable.</>
          )}
        </p>

        <div className="cols">
          <section>
            <div className="sh">
              <h2>Win-condition telemetry</h2>
              <span className="meta">
                <select
                  className="sel"
                  // rep.deck is the engine-resolved filename; the URL may hold
                  // a shorter substring that matches no <option> value.
                  value={rep.deck}
                  aria-label="Deck to inspect"
                  onChange={(e) =>
                    router.replace(
                      `/results/${enc}/telemetry?deck=${encodeURIComponent(e.target.value)}` +
                        (watchStr ? `&watch=${encodeURIComponent(watchStr)}` : ""),
                    )
                  }
                >
                  {decks.map((d) => (
                    <option key={d} value={d}>
                      {oneName(labelFor(d))}
                    </option>
                  ))}
                </select>
              </span>
            </div>
            <p className="sdesc">
              Whether each piece of the deck&apos;s plan actually fired, measured per game across
              the {games} {games === 1 ? "game" : "games"} in this file.
            </p>
            <table className="telet">
              <tbody>
                {cmd && (
                  <tr>
                    <td className="nm">
                      Commander ignition
                      <small>
                        {cmd.name} · cast in {castGames} of {games}
                        {cmd.ai_wont_play && <> · {AI_SKIPS_NOTE}</>}
                      </small>
                    </td>
                    <td className="val">
                      {cmd.median_turn != null ? `turn ${tableTurn(cmd.median_turn)} (median)` : "never"}
                    </td>
                    <td className="stc">
                      <Status s={cmd.status} />
                    </td>
                  </tr>
                )}
                {/* The charge-counter and proliferate rows are gone (WS11
                    task 8): every deck got them, counted across all seats. */}
                {!cmd && rep.watched.length === 0 && (
                  <tr>
                    <td className="nm">
                      Nothing to measure for this deck yet
                      <small>no commander was identified and no cards are being watched</small>
                    </td>
                    <td className="val">–</td>
                  </tr>
                )}
                {rep.watched.map((w) => (
                  <tr key={w.name}>
                    <td className="nm">
                      {w.name}
                      <small>
                        watched card
                        {w.ai_wont_play && <> · {AI_SKIPS_NOTE}</>}
                      </small>
                    </td>
                    <td className="val">{w.events_per_game}/g</td>
                    <td className="stc">
                      <Status s={w.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {coldWatched.length > 0 && (
              <p className="note">
                Zero events can mean the card was never drawn as easily as never cast; the log
                only records what happened, not why it didn&apos;t.
              </p>
            )}
            {/* Repair plan WS6 task 4: a card Forge's AI never casts is not a
                cut candidate, so its rows carry no verdict, and the page says
                why wherever such a row appears. */}
            {skippedShown.length > 0 ? (
              <p className="note">
                Forge&apos;s AI doesn&apos;t cast {skippedShown.join(" or ")} on its own, so
                telemetry never calls {skippedShown.length === 1 ? "it" : "them"} cold: a card the
                AI skips is not a cut candidate, however rarely it shows up. Sim Lab&apos;s pilot can
                cast some such cards while chasing a combo or tutoring.
              </p>
            ) : (
              skippedAll &&
              skippedAll.length > 0 && (
                <p className="note">
                  {plural(skippedAll.length, "card")} in this deck{" "}
                  {skippedAll.length === 1 ? "is one" : "are ones"} Forge&apos;s AI doesn&apos;t cast
                  on its own (listed on the run&apos;s overview); telemetry never calls{" "}
                  {skippedAll.length === 1 ? "it" : "them"} cold.
                </p>
              )
            )}
          </section>

          <section>
            <div className="sh">
              <h2>What killed it</h2>
              <span className="meta">
                {rep.deaths.median_turn != null && (
                  <>median knockout turn <span className="mono">{tableTurn(rep.deaths.median_turn)}</span></>
                )}
              </span>
            </div>
            <p className="sdesc">
              Damage dealt to {deckName} by source, summed across the run.
            </p>
            <table className="telet">
              <tbody>
                {rep.deaths.by_source.map((s) => (
                  <tr key={s.source}>
                    <td className="nm">{s.source}</td>
                    <td className="val">{s.damage} dmg</td>
                  </tr>
                ))}
                {rep.deaths.by_source.length === 0 && (
                  <tr>
                    <td className="nm">
                      No damage was recorded against this deck
                      <small>it may have lost to life loss, poison, or decking instead</small>
                    </td>
                    <td className="val">–</td>
                  </tr>
                )}
              </tbody>
            </table>
          </section>
        </div>

        <p className="note">
          Counts are event-log substring matches, not rules-level reads, and every per-game rate
          divides by the <span className="mono">{games}</span> {games === 1 ? "game" : "games"}{" "}
          actually present in this file. A deck can lose its sims and still show healthy
          telemetry; the machinery firing is a separate question from the pod outcome.
        </p>

        <PageDetails label="Run details">
          <div>{file}</div>
          <div>{rep.deck}</div>
        </PageDetails>
      </div>
      <Footer />
    </>
  );
}

export default function TelemetryPage() {
  return (
    <Suspense fallback={null}>
      <TelemetryInner />
    </Suspense>
  );
}
