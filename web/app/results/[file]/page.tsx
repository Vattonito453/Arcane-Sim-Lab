"use client";

/** Run results report — /results/[file]
 *  Reads the run *summary* from the engine (GET /results/{file}/summary) and
 *  reports it: prose lede, four headline figures, win-rate rails against the
 *  even-seats baseline, and a games table that links into the replay theater.
 *
 *  The summary carries no event logs — a run that is ~2.4 MB whole arrives here
 *  as a few KB. Anything that needs the event-by-event record (the "decided by"
 *  reason, the folded board) lives in the replay, which fetches one game. */

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Chrome, Footer, PageDetails, type TabDef } from "@/components/Chrome";
import { api, RateLimited } from "@/lib/api";
import type {
  AnalysisReport,
  PredictionReport,
  RunGameSummary,
  RunSummary,
  ScorecardReport,
} from "@/lib/types";
import { ComboLines } from "@/components/ComboLines";
import { DeckScorecards } from "@/components/DeckScorecards";
import { PredictionPanel } from "@/components/PredictionPanel";
import { fmtDay, pct, plural, runDate, runTitle, stripAi } from "@/lib/format";

/** "12:05". A missing duration is an en dash: a draw logged without one
 *  printed "NaN:NaN" here (tasks/26-ux-review.md, problem 6). */
function fmtClock(ms: number | null | undefined): string {
  if (typeof ms !== "number" || !Number.isFinite(ms) || ms < 0) return "–";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function median(xs: number[]): number {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2);
}

/** Winner key out of a result raw, for the rare run whose result.winner is null
 *  but whose raw still names a winner ("… Ai(2)-Drana Vampires has won!"). */
const RE_WON_RAW = /([^.]+?) has won/;

/** Game length out of a result raw, for a line the adapter did not time:
 *  "Game 3 ended in a Draw! Took 17619 ms." carries no duration_ms. */
const RE_TOOK_MS = /(?:Took|ended in) (\d+) ms/;

/** How a game that nobody won ended, stamped by the adapters on top of
 *  SimGame["result"]. The shim marks the per-game clock and the turn cap;
 *  stock-Forge results carry neither, so every field is optional. */
type ResultMarks = {
  timedOut?: boolean;
  turnCapped?: boolean;
  error?: unknown;
  missingResult?: boolean;
};

/** One table row, built entirely from the summary payload. */
interface GameRow {
  n: number;
  winnerName: string | null;
  draw: boolean;
  /** Forge's per-player turn counter. Kept for the median only; never shown,
   *  because it reads about 4x high to a player ("T36" for a turn-9 game). */
  endedTurn: number;
  /** The table turn: a player's Nth turn is turn N. */
  endedRound: number | null;
  durationMs: number;
  decidedBy: string;
}

function toRow(g: RunGameSummary, clockSeconds: number | null): GameRow {
  const r = g.result as RunGameSummary["result"] & ResultMarks;
  // A game the clock cut off is a draw whatever winner the record carries:
  // the engine's summary counts it that way (audit A16), so the table must too.
  const timedOut = r.timedOut === true;
  const draw = r.draw || timedOut;
  // `raw` is optional-chained: every adapter path sets it today, but a result
  // with neither a winner nor a raw line should render as "–" rather than take
  // the whole page down with it.
  const key = draw ? null : (r.winner ?? r.raw?.match(RE_WON_RAW)?.[1]?.trim() ?? null);
  const winnerName = key ? stripAi(key) : null;
  const endedTurn = g.ended_turn ?? g.turns;
  const endedRound = g.ended_round ?? null;
  const durationMs =
    typeof r.duration_ms === "number" ? r.duration_ms : Number(r.raw?.match(RE_TOOK_MS)?.[1] ?? NaN);
  const onTurn = endedRound ? ` on turn ${endedRound}` : "";
  // A draw says why when the data knows ("Draw (draw)" said nothing). Older
  // stock-Forge files carry no clock mark, but a draw that ran the full clock
  // was cut by it.
  const hitClock =
    timedOut || (clockSeconds != null && Number.isFinite(durationMs) && durationMs >= clockSeconds * 1000);
  const clockWords = clockSeconds ? `the ${Math.round(clockSeconds / 60)}-minute clock` : "the per-game clock";
  // Without the event log there is no honest way to name the killing swing, so
  // this column states only what the result line proves: who won, and when.
  const decidedBy = draw
    ? hitClock
      ? `Draw: hit ${clockWords}${onTurn}`
      : r.turnCapped
        ? `Draw: reached the turn limit${onTurn}`
        : `Draw${onTurn}`
    : winnerName
      ? `${winnerName} won${onTurn}`
      : r.error
        ? "No result: this game crashed"
        : r.missingResult
          ? "No result: none was recorded"
          : "–";
  return {
    n: g.n,
    winnerName,
    draw,
    endedTurn,
    endedRound,
    durationMs,
    decidedBy,
  };
}

export default function ResultsPage() {
  const params = useParams<{ file: string }>();
  const router = useRouter();
  const file = decodeURIComponent(String(params?.file ?? ""));

  const [data, setData] = useState<RunSummary | null>(null);
  const [an, setAn] = useState<AnalysisReport | null>(null);
  const [sc, setSc] = useState<ScorecardReport | null>(null);
  const [pred, setPred] = useState<PredictionReport | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [wait, setWait] = useState<number | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    let live = true;
    api
      .runSummary(file)
      .then((r) => live && setData(r))
      .catch((e: unknown) => {
        if (!live) return;
        if (e instanceof RateLimited) {
          setWait(e.retryAfter);
          setErr(e.message);
        } else {
          setErr(e instanceof Error ? e.message : String(e));
        }
      });
    // The analysis (win methods, combo lines) loads separately and the page
    // works without it: the first request for an old run computes it
    // server-side, which can take a few seconds, and a failure just means no
    // "How games ended" or combo-lines section.
    api.analysis(file).then((r) => live && setAn(r)).catch(() => {});
    // Per-deck scorecards: a few KB, and the only route the shim's neutral
    // per-seat records take to the browser. The page works without them (an
    // old run has no behaviour records), so a failure is silent.
    api.runScorecards(file)
      .then((r) => {
        // Shape-check before trusting it. An engine older than this build
        // has no /scorecards route and falls through to the whole result
        // file, which is a 200 with a completely different body; reading
        // .run off that white-screened the page during verification. A
        // version-skewed deploy must degrade to the old table instead.
        if (live && r && Array.isArray(r.decks) && r.run) setSc(r);
      })
      .catch(() => {});

    // Corrected win rates. Same contract as scorecards: optional, silent on
    // failure, and shape-checked, because an engine without the fitted model
    // answers {available:false} rather than erroring.
    api.runPrediction(file)
      .then((r) => {
        if (live && r && typeof r.available === "boolean") setPred(r);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [file]);

  const view = useMemo(() => {
    if (!data) return null;
    const games = data.games.length;

    // The pod roster comes from the games, not from summary.win_rates, for two
    // reasons. A winless deck is missing from the summary of any run adapted
    // before that was fixed, and reading the roster off the summary sizes a
    // 4-deck pod as a 1-deck pod — which sets the even-seats baseline to 100%.
    // Rotated runs also key the summary by bare deck name while games[].players
    // keep the Ai(n)- seat prefix; folding both through stripAi() puts the two
    // in one namespace, so every row below is already a display label.
    const wins = new Map<string, number>();
    for (const g of data.games) for (const p of g.players) wins.set(stripAi(p), 0);
    for (const [key, w] of Object.entries(data.summary.wins)) {
      const label = stripAi(key);
      wins.set(label, (wins.get(label) ?? 0) + w);
    }
    const baseline = wins.size > 0 ? 1 / wins.size : 0.25;
    const rows = [...wins.entries()]
      // Recomputed rather than read from win_rates: that map is keyed the same
      // way and would reintroduce the raw-vs-stripped mismatch.
      .map(([name, w]) => ({ name, wins: w, rate: games > 0 ? w / games : 0 }))
      .sort((a, b) => b.rate - a.rate || a.name.localeCompare(b.name));
    const maxWins = rows.length ? rows[0].wins : 0;
    const tops = rows.filter((r) => r.wins === maxWins);
    const topNames = new Set(tops.map((t) => t.name));
    // run_sim stamps the per-game clock it ran under (seconds).
    const clock = data.meta?.clock;
    const clockSeconds = typeof clock === "number" && clock > 0 ? clock : null;
    const gameRows: GameRow[] = data.games.map((g) => toRow(g, clockSeconds));
    const medTurns = median(gameRows.map((g) => g.endedTurn));
    const rotated = data.meta?.source === "rotated";

    // First game the leading deck actually won — target for the primary action.
    let watchGame = 1;
    for (const g of gameRows) {
      if (g.winnerName && topNames.has(g.winnerName)) {
        watchGame = g.n;
        break;
      }
    }
    return { games, baseline, rows, tops, topNames, gameRows, medTurns, rotated, watchGame };
  }, [data, file]);

  // The matchup, not the filename: "sim_20260724_094940_rotated.json" tells a
  // reader nothing. The address lives in the details disclosure at the foot.
  const title = view ? runTitle(view.rows.map((r) => r.name)) : file.replace(/\.json$/, "");
  const enc = encodeURIComponent(file);
  const when = runDate(file);

  // Real destinations now that telemetry and coaching exist — the row is
  // present on the loading and error states too, so it does not vanish mid-load.
  const tabs: TabDef[] = [
    { label: "Overview", href: `/results/${enc}`, on: true },
    { label: "Telemetry", href: `/results/${enc}/telemetry` },
    { label: "Coaching", href: `/results/${enc}/coaching` },
  ];

  if (err) {
    return (
      <>
        <Chrome tabs={tabs} />
        <div className="page">
          <div className="head">
            <div>
              <h1>{title}</h1>
              <div className="sub">{wait != null ? "Rate limited" : "Could not load this result"}</div>
            </div>
          </div>
          {wait != null ? (
            <p className="note">
              {err}. The engine is throttling reads. Try again in about{" "}
              <span className="mono">{wait}</span> s.
            </p>
          ) : (
            <p className="note">{err}. Check that the engine API is running, then reload.</p>
          )}
        </div>
        <Footer />
      </>
    );
  }
  if (!data || !view) {
    return (
      <>
        <Chrome tabs={tabs} />
        <div className="page">
          <div className="head">
            <div>
              <h1>{title}</h1>
              <div className="sub">Loading result…</div>
            </div>
          </div>
        </div>
        <Footer />
      </>
    );
  }

  const { rows, tops, topNames, gameRows, games, baseline, medTurns, rotated } = view;
  // Table rounds when the scorecards have loaded; Forge player-turns only as
  // the fallback for a run whose scorecards could not be computed. The two
  // are different units and the label says which one is on screen.
  const medRounds = sc?.run?.medianGameRound ?? null;
  const top = rows[0];
  const second = rows.find((r) => !topNames.has(r.name));
  const draws = data.summary.draws;
  // Clock-cut games. They are draws too, so this qualifies the draw count
  // rather than adding to it: a pod that mostly times out reads as four decks
  // all "below an even share" at once, which is a property of the clock and
  // not of any deck.
  const timeouts = data.summary.timeouts ?? 0;
  const validity = data.validity;
  const gameWord = rotated ? "seat-rotated games" : "games";

  const filtered = gameRows.filter((g) => {
    if (!q.trim()) return true;
    const needle = q.trim().toLowerCase();
    return (
      (g.winnerName ?? "draw").toLowerCase().includes(needle) ||
      g.decidedBy.toLowerCase().includes(needle) ||
      (g.endedRound != null && `turn ${g.endedRound}`.includes(needle))
    );
  });

  const tieText =
    tops.length > 1
      ? `, tied with ${tops.slice(1).map((t) => t.name).join(" and ")}`
      : second
        ? `, ${top.wins - second.wins} ${top.wins - second.wins === 1 ? "win" : "wins"} clear of ${second.name} (${pct(second.rate)})`
        : "";

  return (
    <>
      <Chrome tabs={tabs} />
      <div className="page">
        <div className="head">
          <div>
            <h1>{title}</h1>
            {/* What sizes the result: format, pod, sample, date. The result
                filename used to be the third item here — an address, and the
                only one of the five that told a reader nothing. The date
                replaces it and earns its place: four runs of this matchup are
                otherwise indistinguishable. */}
            <div className="sub">
              {String(data.meta?.format ?? "Commander")}
              <span className="sep">·</span>
              {plural(rows.length, "deck")}
              <span className="sep">·</span>
              <span className="mono">{games}</span> {rotated ? "seat-rotated " : ""}
              {games === 1 ? "game" : "games"}
              {when && (
                <>
                  <span className="sep">·</span>
                  {fmtDay(when)}
                </>
              )}
            </div>
          </div>
          <div className="btns">
            <Link className="btn pri" href={`/results/${enc}/replay/${view.watchGame}`}>
              Watch a winning game
            </Link>
          </div>
        </div>

        <p className="lede">
          <b>{top.name}</b> won <b>{top.wins} of {games}</b> {gameWord} ({pct(top.rate)})
          {tieText}.{" "}
          {draws > 0 ? (
            <>
              {draws} {draws === 1 ? "game" : "games"} ended drawn
              {timeouts > 0 &&
                (timeouts >= draws ? (
                  <>
                    , {draws === 1 ? "and it hit" : "all of them hitting"} the
                    per-game clock rather than finishing
                  </>
                ) : (
                  <>
                    , <b>{timeouts}</b> of those because{" "}
                    {timeouts === 1 ? "it hit" : "they hit"} the per-game clock
                    rather than finishing
                  </>
                ))}
              ; the median game ran <b>{medRounds ?? medTurns} {medRounds ? "rounds" : "turns"}</b>.
            </>
          ) : (
            <>No draws; the median game ran{" "}
              <b>{medRounds ?? medTurns} {medRounds ? "rounds" : "turns"}</b>.</>
          )}
        </p>

        {validity && validity.quality !== "clean" && (
          <p className="note">
            <b>
              {validity.quality === "polluted"
                ? "These numbers are not trustworthy."
                : "Read these numbers with care."}
            </b>{" "}
            {validity.reasons.join(" ")}
          </p>
        )}

        <div className="figs">
          <div className="fig">
            <div className="n">{games}</div>
            <div className="l">games in this run</div>
          </div>
          <div className="fig">
            <div className="n">{medRounds ?? medTurns}</div>
            <div className="l">
              median {medRounds ? "rounds" : "turns"} per game
            </div>
          </div>
          <div className="fig">
            <div className="n">
              {(top.rate * 100).toFixed(0)}
              <small>%</small>
            </div>
            <div className="l">top win rate ({top.name})</div>
          </div>
          <div className="fig">
            <div className="n">{draws}</div>
            <div className="l">{draws === 1 ? "draw" : "draws"}</div>
          </div>
        </div>

        {sc ? (
          <DeckScorecards report={sc} />
        ) : (
          <section>
            <div className="sh">
              <h2>Win rates</h2>
              <span className="meta">
                {plural(games, "game")}, {plural(rows.length, "deck")}
              </span>
            </div>
            <table className="podt">
              <tbody>
                {rows.map((r) => (
                  <tr key={r.name}>
                    <td className="nm">{r.name}</td>
                    <td>
                      <div className="rail">
                        <div className="fill" style={{ width: `${Math.max(r.rate * 100, r.wins > 0 ? 1 : 0)}%` }} />
                        <div className="base" style={{ left: `${baseline * 100}%` }} />
                      </div>
                    </td>
                    <td className="pct">{pct(r.rate)}</td>
                    <td className="res">
                      <span className={`st ${r.wins === 0 ? "bad" : r.rate >= baseline ? "win" : "loss"}`}>
                        <i />
                        {r.wins} of {games}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="note">
              The marker sits at {pct(baseline, 1)}, an even share of a {rows.length}-player pod.
            </p>
          </section>
        )}

        {/* Measured first, modelled second: the corrected rates only read
            correctly once the reader has seen the raw ones they correct. */}
        <PredictionPanel report={pred} />

        {an && Object.keys(an.summary?.methods ?? {}).length > 0 && (
          <section>
            <div className="sh">
              <h2>How games ended</h2>
              <span className="meta">{plural(an.summary.games, "game")}</span>
            </div>
            <div className="scgrp mth">
              {Object.entries(an.summary.methods)
                .sort((a, b) => b[1] - a[1])
                .map(([method, n]) => (
                  <span key={method}>
                    <b>{n}</b>{" "}
                    {/* Forge writes one loss line for combat damage and for
                        life loss alike, so this cannot say "combat" alone
                        until the knockouts analyzer reads the lethal event
                        (repair plan WS1, WS11 task 3). */}
                    {method === "combat damage / life loss"
                      ? "ended as life reached 0 (combat or life loss)"
                      : method === "not recorded"
                        ? "with no method recorded"
                        : method === "draw"
                          ? "drawn"
                          : `by ${method}`}
                  </span>
                ))}
            </div>
            <p className="note">
              Read from the loss line Forge wrote at the end of each game. Forge
              writes the same line for combat damage and for life loss, so the
              two are not told apart here.
            </p>
          </section>
        )}

        {/* Combo lines from Commander Spellbook, folded into families. Most
            cannot win on their own and Forge's AI doesn't run combo loops, so
            the section shows chances, not results (repair plan WS11 task 2). */}
        <ComboLines report={an} />

        <section>
          <div className="sh">
            <h2>Games</h2>
            <span className="meta">{games} total</span>
          </div>
          <div className="tblwrap">
            <div className="toolrow">
              <div className="inp">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="7" />
                  <path d="m21 21-4.3-4.3" />
                </svg>
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Filter by winner or finish…"
                  aria-label="Filter games"
                />
              </div>
              <span className="upd">
                {filtered.length} of {plural(games, "game")}
              </span>
            </div>
            {/* `stackable` + the c- cell classes are the narrow-screen contract
                (globals.css): below 720px the head hides and each row reflows to
                two lines rather than hiding four of its six columns behind a
                horizontal scroll nobody discovers. */}
            <table className="games stackable">
              <thead>
                <tr>
                  <th style={{ width: 64 }}>Game</th>
                  <th style={{ width: 220 }}>Winner</th>
                  <th style={{ width: 70 }}>Ended</th>
                  <th style={{ width: 80 }}>Duration</th>
                  <th>Decided by</th>
                  <th className="r" style={{ width: 90 }}>
                    Replay
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((g) => (
                  <tr
                    key={g.n}
                    className="click"
                    onClick={() => router.push(`/results/${enc}/replay/${g.n}`)}
                  >
                    {/* Wide: its own column. Narrow: it belongs on the title
                        line, not orphaned above it — a block-level title after
                        an inline cell starts a new line box. */}
                    <td className="id c-drop">#{g.n}</td>
                    <td className="c-title">
                      <span className="only-narrow-inline gnum">#{g.n} </span>
                      {g.draw ? (
                        <span className="st out">
                          <i />
                          Draw
                        </span>
                      ) : g.winnerName && topNames.has(g.winnerName) ? (
                        <span className="st win">
                          <i />
                          {g.winnerName}
                        </span>
                      ) : (
                        (g.winnerName ?? "–")
                      )}
                    </td>
                    {/* The table turn, never Forge's per-player counter ("T36"
                        for a game that ended on everyone's ninth turn). */}
                    <td className="mono c-meta">{g.endedRound ? `turn ${g.endedRound}` : "–"}</td>
                    <td className="dur c-meta">{fmtClock(g.durationMs)}</td>
                    <td className="c-meta">
                    {g.decidedBy}
                    {(() => {
                      // The summary can only say who won and when; the analysis
                      // knows HOW. Only annotate the non-default methods. A draw
                      // already says why above, so it never gets "(draw)", and
                      // "other" names nothing a player can use.
                      const m = an?.games.find((x) => x.n === g.n);
                      if (!m || g.draw || m.method === "draw" || m.method === "other"
                          || m.method === "combat damage / life loss" || m.method === "not recorded")
                        return null;
                      return (
                        <span className="ctanote">
                          {" ("}{m.method === "spell" ? `won by ${m.detail}` : m.method}{")"}
                        </span>
                      );
                    })()}
                  </td>
                    <td className="r c-act">
                      <Link
                        className="bl"
                        href={`/results/${enc}/replay/${g.n}`}
                        onClick={(e) => e.stopPropagation()}
                      >
                        Watch
                      </Link>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td className="c-empty" colSpan={6}>No games match “{q}”.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="note">
            Open a replay to see what actually did the killing.
          </p>
        </section>

        <PageDetails label="Run details">
          <div>{file}</div>
          {when && <div>{when.toLocaleString()}</div>}
          <div>
            {plural(games, "game")} · {data.games.reduce((a, g) => a + g.events, 0).toLocaleString("en-US")} events
            {data.meta?.source ? ` · ${String(data.meta.source)}` : ""}
          </div>
        </PageDetails>
      </div>
      <Footer />
    </>
  );
}
