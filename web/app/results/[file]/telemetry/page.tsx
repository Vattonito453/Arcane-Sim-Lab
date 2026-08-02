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
import type { RunSummary, TelemetryReport } from "@/lib/types";
import { plural, runTitle, stripAi } from "@/lib/format";

const ST_CLASS = { healthy: "ok", partial: "warn", cold: "bad" } as const;
const ST_WORD = { healthy: "Healthy", partial: "Partial", cold: "Never fired" } as const;

function Status({ s }: { s: keyof typeof ST_CLASS }) {
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

  const title = summary
    ? runTitle(((summary.meta?.decks as string[]) ?? []).map((d) => d.replace(/\.dck$/, "")))
    : file.replace(/\.json$/, "");

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
          {wait != null ? (
            <p className="note">
              {err} — the engine is throttling reads. Try again in about{" "}
              <span className="mono">{wait}</span> s.
            </p>
          ) : (
            <p className="note">{err} — check that the engine API is running, then reload.</p>
          )}
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
  const deckName = stripAi(rep.player_key ?? "") || rep.deck.replace(/\.dck$/, "");

  return (
    <>
      <Chrome tabs={tabs} />
      <div className="page">
        <div className="head">
          <div>
            <h1>{deckName} — telemetry</h1>
            {/* The .dck filename used to lead this line; it is in the details
                disclosure at the foot with the rest of the addresses. */}
            <div className="sub">
              <span className="mono">{games}</span> {games === 1 ? "game" : "games"} in this run
              <span className="sep">·</span>
              won <span className="mono">{rep.wins}</span> of <span className="mono">{games}</span>
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
                  , first arriving on median turn <b>{cmd.median_turn}</b>
                </>
              )}
              .{" "}
            </>
          ) : (
            <>
              No commander could be identified for this deck, so telemetry covers its engine
              and watched cards only.{" "}
            </>
          )}
          The table logged charge counters <b>{rep.engine.charge_events_per_game}</b> times a
          game and proliferate <b>{rep.engine.proliferate_per_game}</b>
          {rep.watched.length > 0 && (
            <>
              ; {coldWatched.length > 0 ? (
                <>
                  <b>{coldWatched.length} of {plural(rep.watched.length, "watched card")}</b> never
                  fired
                </>
              ) : (
                <>all {plural(rep.watched.length, "watched card")} showed up</>
              )}
            </>
          )}
          .{" "}
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
                      {d.replace(/\.dck$/, "")}
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
                      </small>
                    </td>
                    <td className="val">
                      {cmd.median_turn != null ? `T${cmd.median_turn} med` : "never"}
                    </td>
                    <td className="stc">
                      <Status s={cmd.status} />
                    </td>
                  </tr>
                )}
                <tr>
                  <td className="nm">
                    Charge counters
                    <small>station, triggers, additions · all seats</small>
                  </td>
                  <td className="val">{rep.engine.charge_events_per_game}/g</td>
                  <td className="stc">
                    <Status s={rep.engine.charge_status} />
                  </td>
                </tr>
                <tr>
                  <td className="nm">
                    Proliferate
                    <small>resolutions and mentions · all seats</small>
                  </td>
                  <td className="val">{rep.engine.proliferate_per_game}/g</td>
                  <td className="stc">
                    <Status s={rep.engine.proliferate_status} />
                  </td>
                </tr>
                {rep.watched.map((w) => (
                  <tr key={w.name}>
                    <td className="nm">
                      {w.name}
                      <small>watched card</small>
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
                Zero events can mean the card was never drawn as easily as never cast — the log
                only records what happened, not why it didn&apos;t.
              </p>
            )}
          </section>

          <section>
            <div className="sh">
              <h2>What killed it</h2>
              <span className="meta">
                {rep.deaths.median_turn != null && (
                  <>median death turn <span className="mono">T{rep.deaths.median_turn}</span></>
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
                    <td className="val">—</td>
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
          telemetry — the machinery firing is a separate question from the pod outcome.
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
