"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { JobStatus, LiveGame, SimSummary } from "@/lib/types";
import { deckSlug, estimateSeconds, fmtDuration, pct, plural, runTitle, scryfallArt, shortName, stripAi, timeAgo } from "@/lib/format";
import { boardFxAt, buildTimeline, commanderGuess, foldTo, handsAt } from "@/lib/replay";
import { loadCards, type CardFacts, type CardMap } from "@/lib/cards";
import { Tabletop, TabletopNote } from "@/components/Tabletop";
import { Chrome, Footer, PageDetails } from "@/components/Chrome";

const ENGINE_CMD = "python3 engine/mtg_engine.py serve 8484";
const POLL_MS = 4000;
const LIVE_POLL_MS = 1500;
const PLAY_TICK_MS = 50;

/** Actions worth stopping on. 56% of a game log is bookkeeping — 41% phase and
 *  step lines, 15% mana — and playing every event at a rate that finished a game
 *  in 20 s meant ~80 events a second, which is unreadable. Playback steps
 *  between these instead: things a player would actually watch for. Resolves are
 *  left out because the cast already announced the card.
 *
 *  Skipped events are not discarded — foldTo() still folds every step up to the
 *  playhead, so the board stays correct. Only the pauses change. */
const BEATS = new Set([
  "stack_add", "combat", "damage", "life_change", "zone_change", "land_drop",
  "discard", "game_outcome",
]);
/** Beats per second at 1x. A 43-turn game holds ~370 of them, so 1x runs about a
 *  minute — close to the pace Forge produces four-deck games at. */
const BEATS_PER_SEC = 6;
const SPEEDS = [0.5, 1, 2, 4];

function topWin(s: SimSummary): [string, number] | null {
  const entries = Object.entries(s.win_rates);
  if (entries.length === 0) return null;
  entries.sort((a, b) => b[1] - a[1]);
  return entries[0];
}

export default function RunPage() {
  const params = useParams();
  const rawId = params.id;
  const id = Array.isArray(rawId) ? (rawId[0] ?? "") : (rawId ?? "");
  const router = useRouter();

  const [status, setStatus] = useState<JobStatus | null>(null);
  const [fetchErr, setFetchErr] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const terminalRef = useRef(false);

  useEffect(() => {
    if (!id) return;
    terminalRef.current = false;
    let stopped = false;
    const tick = async () => {
      if (stopped || terminalRef.current) return;
      try {
        const s = await api.simStatus(id);
        if (stopped) return;
        setStatus(s);
        setFetchErr(null);
        const st = s.state ?? (s.error ? "error" : undefined);
        if (st === "done" || st === "error") terminalRef.current = true;
      } catch (e) {
        if (!stopped) setFetchErr(e instanceof Error ? e.message : String(e));
      }
    };
    void tick();
    const iv = setInterval(() => void tick(), POLL_MS);
    return () => {
      stopped = true;
      clearInterval(iv);
    };
  }, [id]);

  useEffect(() => {
    const iv = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(iv);
  }, []);

  // ── watching the run ─────────────────────────────────────────────────────
  // Buffer, then play back. Forge does not trickle its log out evenly — it
  // arrives in bursts, most of a game at once, so pinning the view to the last
  // event known showed a frozen table that filled in exactly as the game ended.
  // Instead each game is played out from the buffer at a watchable pace while
  // Forge runs ahead, which is a replay of a finished game rather than a live
  // feed, and is labelled as one.
  const [watchGame, setWatchGame] = useState(1);
  const [liveData, setLiveData] = useState<LiveGame | null>(null);
  useEffect(() => {
    if (!id) return;
    let stopped = false;
    const tick = async () => {
      if (stopped) return;
      try {
        // Asking for a game Forge has not reached is normal; the engine clamps.
        setLiveData(await api.simLive(id, watchGame));
      } catch {
        // 404 until Forge writes its first line. Not worth surfacing.
      }
    };
    void tick();
    const iv = setInterval(() => void tick(), LIVE_POLL_MS);
    return () => {
      stopped = true;
      clearInterval(iv);
    };
  }, [id, watchGame]);

  const liveGame = liveData?.game ?? null;
  const liveTimeline = useMemo(() => (liveGame ? buildTimeline(liveGame) : null), [liveGame]);

  // Playhead. Advances on a clock, not with the buffer.
  const [playIdx, setPlayIdx] = useState(0);
  useEffect(() => {
    setPlayIdx(0); // new game to watch — start it from the top
  }, [liveData?.n]);

  // Indices of the steps playback stops on.
  const beats = useMemo(() => {
    if (!liveTimeline) return [];
    const out: number[] = [];
    liveTimeline.steps.forEach((s, i) => {
      if (BEATS.has(s.kind)) out.push(i);
    });
    return out;
  }, [liveTimeline]);

  const [speed, setSpeed] = useState(1);
  const [paused, setPaused] = useState(false);
  const lastTickRef = useRef(0);
  const beatRef = useRef(0); // fractional position in `beats`, so slow speeds work

  useEffect(() => {
    beatRef.current = 0;
  }, [liveData?.n]);

  useEffect(() => {
    if (beats.length === 0 || paused) return;
    lastTickRef.current = performance.now();
    const iv = setInterval(() => {
      const now = performance.now();
      const dt = now - lastTickRef.current;
      lastTickRef.current = now;
      // Advance by elapsed time, not by one tick's worth: browsers throttle a
      // backgrounded tab to roughly one timer callback a second, and a per-tick
      // rate stretched a one-minute game into many.
      beatRef.current = Math.min(
        beatRef.current + (dt / 1000) * BEATS_PER_SEC * speed,
        beats.length - 1,
      );
      setPlayIdx(beats[Math.floor(beatRef.current)] ?? 0);
    }, PLAY_TICK_MS);
    return () => clearInterval(iv);
  }, [beats, speed, paused]);

  // Once this game is played out and a later one exists, move on to it.
  const gamesSeen = liveData?.games_seen ?? 0;
  // Derived from state, not from beatRef: a ref read during render does not
  // re-render when it changes, so the "waiting for Forge" hint and the
  // advance-to-next-game check would both go stale.
  const atEnd = beats.length > 0 && playIdx >= beats[beats.length - 1];
  const finishedWatching = atEnd && !liveData?.in_progress;
  useEffect(() => {
    if (finishedWatching && gamesSeen > watchGame) {
      const t = setTimeout(() => setWatchGame((g) => g + 1), 1200);
      return () => clearTimeout(t);
    }
  }, [finishedWatching, gamesSeen, watchGame]);

  const liveStep = liveTimeline?.steps[playIdx];
  const liveFx = useMemo(
    () => boardFxAt(liveGame?.boardfx, liveStep?.turn ?? 0, liveStep?.phase ?? ""),
    [liveGame, liveStep?.turn, liveStep?.phase],
  );
  const liveHands = useMemo(
    () => handsAt(liveGame?.zones, liveStep?.turn ?? 0, liveStep?.phase ?? ""),
    [liveGame, liveStep?.turn, liveStep?.phase],
  );
  const liveBoard = useMemo(
    () => (liveTimeline ? foldTo(liveTimeline, playIdx) : null),
    [liveTimeline, playIdx],
  );
  const liveSeats = useMemo(() => {
    if (!liveGame) return [];
    return liveGame.players.map((p) => {
      const commander = commanderGuess(stripAi(p), [liveGame]);
      return {
        player: p,
        label: shortName(p, liveGame.players),
        art: scryfallArt(commander),
        commander,
      };
    });
  }, [liveGame]);

  // Card facts for what is on the table right now. loadCards() memoises across
  // polls, so a growing board only ever fetches the names it has not seen.
  const [cardMap, setCardMap] = useState<CardMap>({});
  useEffect(() => {
    if (!liveBoard) return;
    let alive = true;
    const names = new Set<string>();
    for (const cards of liveBoard.battlefield.values()) {
      for (const c of cards) names.add(c.name);
    }
    // Hands and combat lines too, so hand tiles and blocker ghosts carry
    // faces and tooltips instead of "no card data".
    for (const hand of liveHands.values()) for (const h of hand) names.add(h.name);
    for (const b of liveBoard.blocks) {
      names.add(b.attacker);
      for (const nm of b.blockers) names.add(nm);
    }
    for (const s of liveSeats) if (s.commander) names.add(s.commander);
    if (!names.size) return;
    void loadCards(Array.from(names)).then((m) => alive && setCardMap({ ...m }));
    return () => {
      alive = false;
    };
  }, [liveBoard, liveSeats, liveHands]);
  const facts = useCallback(
    (name: string): CardFacts | undefined => cardMap[name.trim().toLowerCase()],
    [cardMap],
  );

  // The sandbox engine can answer {"error": ...} with no state — treat that as an error.
  const state = status ? (status.state ?? (status.error ? "error" : "idle")) : undefined;

  const decks = status?.decks ?? [];
  const deckNames = decks.map((d) => (d.endsWith(".dck") ? deckSlug(d) : stripAi(d)));
  const games = status?.games;
  const started = status?.started;
  const live = started ? Math.max(0, now / 1000 - started) : (status?.elapsed ?? 0);
  const elapsed = state === "done" || state === "error" ? (status?.elapsed ?? live) : live;
  // The engine now says how many games this will actually play (rounded up to
  // whole seat rotations, so usually more than requested), how long that size
  // typically takes, and how many games are finished across ALL rotations.
  // Prefer all of that over guessing from the browser.
  const prog = status?.progress;
  const plannedGames = prog?.expected_games ?? games ?? 16;
  // Seat-aware fallback for an engine that predates /sim-status.progress: a
  // four-deck game costs ~20x a two-deck one.
  const estimate = prog ? prog.typical_seconds[1] : estimateSeconds(games ?? 16, decks.length || 4);
  const typicalLow = prog?.typical_seconds[0] ?? estimate;
  const gamesDone = prog?.games_done ?? 0;
  // Fill by games finished, not by wall clock. A clock fill is a countdown
  // dressed as progress: it advanced at the same rate whether Forge was
  // playing or had died ten minutes ago (audit A28).
  const progress = prog && plannedGames > 0
    ? Math.min(99, Math.max(2, (gamesDone / plannedGames) * 100))
    : Math.min(95, Math.max(2, (live / estimate) * 100));
  const stalled = prog?.stalled ?? false;
  const overTypical = (prog?.over_typical ?? false) && !stalled;
  const sinceActivity = prog?.seconds_since_activity;
  const short = id.length > 12 ? id.slice(0, 12) : id;
  // A truncated job id is an address, not a title. Name the run by what it is —
  // the matchup — and keep the id in the details disclosure at the foot.
  const podTitle = deckNames.length ? runTitle(deckNames) : "Simulation run";

  const resultBase = status?.result_file ? (status.result_file.split("/").pop() ?? null) : null;
  const resultHref = resultBase ? `/results/${encodeURIComponent(resultBase)}` : null;

  // Don't yank the page away mid-playback. The sim finishing is not a reason to
  // stop showing the game the viewer is in the middle of; wait until playback
  // has run out of buffer and there is no later game queued up.
  const stillWatching = beats.length > 0 && (!atEnd || gamesSeen > watchGame);

  useEffect(() => {
    if (state === "done" && resultHref && !stillWatching) {
      const t = setTimeout(() => router.push(resultHref), 1500);
      return () => clearTimeout(t);
    }
  }, [state, resultHref, router, stillWatching]);

  const res = status?.result;
  const win = res ? topWin(res) : null;

  return (
    <>
      <Chrome />
      <div className="page">
        {!status && !fetchErr && <p className="lede">Checking run status…</p>}

        {!status && fetchErr && (
          <>
            <h1>
              {podTitle}
            </h1>
            <p className="lede">
              Can&apos;t reach the engine yet. This page retries every 4 seconds, so you can
              leave it open.
            </p>
            <p className="note">
              <span className="st bad">
                <i />
                Engine unreachable
              </span>{": "}
              is <span className="mono">{ENGINE_CMD}</span> running?
            </p>
            <p className="note">
              <Link className="q" href="/results">
                ‹ All results
              </Link>
            </p>
          </>
        )}

        {/* One live region holds every state's header, so completion swaps the
            heading in place and is announced (DESIGN_SYSTEM.md §7, WCAG 4.1.3).
            The page never grows a second heading below the tabletop. */}
        <div aria-live="polite">
        {status && (state === "queued" || state === "running") && (
          <>
            <h1>
              {podTitle}
            </h1>
            <p className="lede">
              {state === "queued" ? (
                <>
                  Queued: <b>{plural(plannedGames, "game")}</b> across{" "}
                  <b>{plural(decks.length, "deck")}</b>
                  {(status?.queued_ahead ?? 0) > 0
                    ? `, behind ${plural(status?.queued_ahead ?? 0, "other run")}`
                    : ""}.
                </>
              ) : (
                <>
                  {/* The games that will actually be PLAYED. This said
                      "6 games" while everything below it said 8, which is the
                      surfaces-disagree half of audit A27. */}
                  Simulating <b>{plural(plannedGames, "game")}</b> across{" "}
                  <b>{plural(decks.length, "deck")}</b>
                  {started ? <>, started {timeAgo(started)}</> : null}.
                </>
              )}
            </p>
            <section>
              {/* A queued job draws no progress bar it doesn't have — dashed
                  track, no fill (DESIGN_SYSTEM.md §7). */}
              <div className={state === "queued" ? "prog queued" : "prog"}>
                <div className="fill" style={{ width: `${progress}%` }} />
              </div>
              <p className="note">
                {state === "queued" ? (
                  <>
                    Not started yet. A pod this size usually takes{" "}
                    <b>
                      {fmtDuration(typicalLow)} to {fmtDuration(estimate)}
                    </b>
                    .
                  </>
                ) : (
                  <>
                    <b>
                      {gamesDone} of {plannedGames}
                    </b>{" "}
                    games played
                    {prog && prog.rotations > 1 && (
                      <>
                        {" "}
                        across {prog.rotations} seat rotations
                        {games != null && plannedGames > games && (
                          <>
                            {" "}
                            ({plannedGames} rather than the {games} requested, so
                            every deck sits in every seat the same number of
                            times)
                          </>
                        )}
                      </>
                    )}
                    . Usually {fmtDuration(typicalLow)} to {fmtDuration(estimate)}{" "}
                    for this pod
                    {prog?.eta_seconds != null && gamesDone > 0 && (
                      <>
                        ; at this run&apos;s pace, about{" "}
                        <b>{fmtDuration(prog.eta_seconds)}</b> left
                      </>
                    )}
                    .
                  </>
                )}
              </p>
              {/* The question a waiting user is actually asking is "has this
                  died?", and elapsed time cannot answer it. Liveness comes
                  from whether the run is still WRITING: slower than usual is
                  normal, silent is not. */}
              {state === "running" && overTypical && (
                <p className="note">
                  <b>This run is taking longer than usual, and that is normal.</b>{" "}
                  Games with big boards can run the full clock, and every seat
                  rotation starts a fresh engine.
                  {sinceActivity != null && (
                    <>
                      {" "}
                      It is still working: the last game activity was{" "}
                      {fmtDuration(sinceActivity)} ago.
                    </>
                  )}{" "}
                  Leave it running. Starting the same gauntlet again would make
                  both copies slower.
                </p>
              )}
              {state === "running" && stalled && (
                <p className="note">
                  <b>Nothing has been written for {sinceActivity != null ? fmtDuration(sinceActivity) : "a while"}.</b>{" "}
                  A single game can legitimately run{" "}
                  {prog ? fmtDuration(prog.ceiling_seconds / plannedGames) : "a long time"}{" "}
                  before the clock draws it, so this may still recover. If it
                  does not, the run stops on its own at{" "}
                  {prog ? fmtDuration(prog.ceiling_seconds) : "its time ceiling"}{" "}
                  and keeps whatever games finished.
                </p>
              )}
            </section>
            <div className="figs">
              <div className="fig">
                <div className="n">{state === "queued" ? "–" : fmtDuration(elapsed)}</div>
                <div className="l">{state === "queued" ? "not started" : "elapsed"}</div>
              </div>
              <div className="fig">
                {/* Games to be PLAYED, which is the number that will appear on
                    the result. The requested figure used to sit here alone and
                    disagreed with every other surface (audit A27). */}
                <div className="n">
                  {state === "queued" ? plannedGames : `${gamesDone}/${plannedGames}`}
                </div>
                <div className="l">
                  {state === "queued" ? "games to play" : "games played"}
                </div>
              </div>
              <div className="fig">
                <div className="n">{decks.length}</div>
                <div className="l">decks in the pod</div>
              </div>
              <div className="fig">
                <span className={state === "queued" ? "st queue" : "st run"}>
                  <i />
                  {state === "queued" ? "Queued" : "Running"}
                </span>
                <div className="l">
                  {state === "queued" && (status?.queued_ahead ?? 0) > 0
                    ? `${status?.queued_ahead} ${status?.queued_ahead === 1 ? "run" : "runs"} ahead`
                    : "state"}
                </div>
              </div>
            </div>

            {/* Forge spends ~25 s loading its card database before it plays a
                card, and the log has no turns to parse until then. Say so
                rather than showing an empty space. Mid-run the same gap means
                something different: each seat rotation starts a fresh engine,
                so "loading its card database" next to "4 of 8 games played"
                reads as a restart when it is just the next rotation booting. */}
            {state === "running" && !liveGame && (
              <p className="note">
                {gamesDone > 0
                  ? "Starting the next seat rotation. Each one launches a fresh engine, so there is a short gap before the table reappears."
                  : liveData
                    ? "Forge is loading its card database. The table appears as soon as the first turn is played."
                    : "Waiting for the first turn…"}
              </p>
            )}


            {fetchErr && (
              <p className="note">
                <span className="st warn">
                  <i />
                  Connection hiccup
                </span>{": "}
                still polling every 4 seconds.
              </p>
            )}
          </>
        )}

        {status && state === "done" && (
          <>
            <div className="head">
              <div>
                <h1>{podTitle}</h1>
              </div>
              <div className="btns">
                {resultHref && (
                  <Link className="btn pri" href={resultHref}>
                    View results
                  </Link>
                )}
              </div>
            </div>
            <p className="lede">
              {win ? (
                <>
                  Done. <b>{stripAi(win[0])}</b> won{" "}
                  <b>
                    {res?.wins[win[0]] ?? 0} of {res?.games ?? games ?? 0} games ({pct(win[1])})
                  </b>
                  .
                </>
              ) : (
                <>Done. The run finished.</>
              )}{" "}
              {/* A run that was cut short still lands here as "done". Saying
                  so on the way out beats letting the reader discover it from
                  a game count that does not match what they asked for. */}
              {status.incomplete && (
                <>
                  <b>It did not finish the full gauntlet.</b>{" "}
                  {status.warning ?? ""}{" "}
                </>
              )}
              {resultHref
                ? stillWatching
                  ? "The playback below finishes first; the full report is one click away."
                  : "Taking you to the full report…"
                : "The result file isn't listed yet. Check past runs on the home page."}
            </p>
            <div className="figs">
              <div className="fig">
                <div className="n">{res?.games ?? games ?? "–"}</div>
                <div className="l">games played</div>
              </div>
              <div className="fig">
                <div className="n">{res?.draws ?? 0}</div>
                <div className="l">draws</div>
              </div>
              <div className="fig">
                <div className="n">{win ? pct(win[1]) : "–"}</div>
                <div className="l">{win ? `${stripAi(win[0])} win rate` : "top win rate"}</div>
              </div>
              <div className="fig">
                <div className="n">{fmtDuration(elapsed)}</div>
                <div className="l">wall-clock time</div>
              </div>
            </div>
          </>
        )}

        {status && state === "error" && (
          <>
            <h1>
              {podTitle}
            </h1>
            <p className="lede">
              The engine reported an error for this run. The message below is verbatim.
            </p>
            <p className="note">
              <span className="st bad">
                <i />
                Failed
              </span>{" "}
              {status.error ?? "Unknown engine error."}
            </p>
            <p className="note">
              <Link className="q" href="/results">
                ‹ All results
              </Link>
            </p>
          </>
        )}
        </div>

          {liveBoard && liveGame && liveTimeline && state !== "error" &&
          (state !== "done" || stillWatching) && (
            <section>
              <div className="sh">
                <h2>
                  Game <span className="mono">{liveData?.n ?? 1}</span>
                  {games ? <> of <span className="mono">{games}</span></> : null}
                </h2>
                <span className="meta">
                  {/* Rounds, not Forge's per-player turn counter: at a table
                      every player gets a turn 1, so raw turns read 4x high. */}
                  round <span className="mono">{liveTimeline.steps[playIdx]?.round ?? 0}</span> of{" "}
                  <span className="mono">{liveTimeline.totalRounds}</span>
                  {atEnd && liveData?.in_progress ? " · waiting for Forge" : ""}
                </span>
                <span className="right">
                  <button className="btn" onClick={() => setPaused((p) => !p)}>
                    {paused ? "Play" : "Pause"}
                  </button>
                  <select
                    className="sel"
                    value={String(speed)}
                    aria-label="Playback speed"
                    onChange={(e) => setSpeed(Number(e.target.value))}
                  >
                    {SPEEDS.map((x) => (
                      <option key={x} value={x}>
                        {x}x speed
                      </option>
                    ))}
                  </select>
                </span>
              </div>
              <div className="theater">
                <Tabletop
                  board={liveBoard}
                  seats={liveSeats}
                  activePlayer={liveTimeline.steps[playIdx]?.active ?? ""}
                  facts={facts}
                  fx={liveFx}
                  hands={liveHands}
                />
                <TabletopNote />
              </div>
              <p className="note">
                Played back at a watchable pace, not live. The simulation keeps running.
              </p>
              <div className="loglist tail">
                {/* Follows the playhead, not the buffer. The full log is
                    scrubbable on the replay page once the run finishes. */}
                {liveTimeline.steps.slice(Math.max(0, playIdx - 7), playIdx + 1).map((s, k) => (
                  <div key={`${s.seq}-${k}`} className="ev">
                    <span className="tt">{s.round > 0 ? `R${s.round}` : "–"}</span>
                    <div>{s.text}</div>
                  </div>
                ))}
              </div>
            </section>
          )}

        {status && state === "idle" && (
          <>
            <h1>
              {podTitle}
            </h1>
            <p className="lede">
              The engine has no record of this run. It may have been restarted since the run was
              queued.
            </p>
            <p className="note">
              <Link className="q" href="/results">
                ‹ All results
              </Link>
            </p>
          </>
        )}
        <PageDetails label="Run details">
          <div>job {id}</div>
          {status?.result_file && <div>{status.result_file.split("/").pop()}</div>}
        </PageDetails>
      </div>
      <Footer />
    </>
  );
}
