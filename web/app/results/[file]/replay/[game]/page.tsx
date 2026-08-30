"use client";

/** Replay theater — /results/[file]/replay/[game] ([game] is 1-based).
 *  Fetches exactly one game (GET /results/{file}/game/{n}) rather than the whole
 *  run, so a 48-turn replay costs ~15 KB on the wire instead of ~235 KB.
 *  All replay state comes from lib/replay.ts: buildTimeline() folds the raw
 *  event log into steps; foldTo() derives a best-effort board at any step.
 *  The event feed on the right is the authoritative record. */

import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Chrome, Footer, PageDetails } from "@/components/Chrome";
import { api, RateLimited } from "@/lib/api";
import type { RunGame } from "@/lib/types";
import { runTitle, scryfallArt, shortName, stripAi } from "@/lib/format";
import { buildTimeline, commanderGuess, foldTo, summarizeGame, type Step } from "@/lib/replay";
import { loadCards, type CardFacts, type CardMap } from "@/lib/cards";
import { Tabletop, TabletopNote } from "@/components/Tabletop";

const SPEED_MS: Record<number, number> = { 1: 300, 2: 150, 4: 75 };

function fmtClock(ms: number): string {
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function clamp(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x));
}

/** Render step text with its key names bolded. */
function Hi({ text, hi }: { text: string; hi?: string[] }) {
  const ranges: [number, number][] = [];
  if (hi) {
    for (const h of Array.from(new Set(hi))) {
      if (!h) continue;
      const at = text.indexOf(h);
      if (at < 0) continue;
      if (ranges.some(([a, b]) => at < b && at + h.length > a)) continue; // overlap
      ranges.push([at, at + h.length]);
    }
  }
  if (!ranges.length) return <>{text}</>;
  ranges.sort((a, b) => a[0] - b[0]);
  const out: React.ReactNode[] = [];
  let pos = 0;
  ranges.forEach(([a, b], k) => {
    if (a > pos) out.push(text.slice(pos, a));
    out.push(<b key={k}>{text.slice(a, b)}</b>);
    pos = b;
  });
  if (pos < text.length) out.push(text.slice(pos));
  return <>{out}</>;
}

export default function ReplayPage() {
  const params = useParams<{ file: string; game: string }>();
  const file = decodeURIComponent(String(params?.file ?? ""));
  const gameNum = Math.max(1, Number(params?.game ?? 1) || 1);
  const enc = encodeURIComponent(file);

  const [data, setData] = useState<RunGame | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [wait, setWait] = useState<number | null>(null);
  const [absent, setAbsent] = useState(false);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [copied, setCopied] = useState(false);
  const seeded = useRef(false);
  const listRef = useRef<HTMLDivElement | null>(null);
  const curRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let live = true;
    // One fetch per game, so switching games has to clear the previous one.
    setData(null);
    setErr(null);
    setWait(null);
    setAbsent(false);
    setIdx(0);
    setPlaying(false);
    api
      .runGame(file, gameNum)
      .then((r) => live && setData(r))
      .catch((e: unknown) => {
        if (!live) return;
        if (e instanceof RateLimited) {
          setWait(e.retryAfter);
          setErr(e.message);
          return;
        }
        const msg = e instanceof Error ? e.message : String(e);
        // fail() formats unhandled statuses as "GET /path → 404: <engine error>".
        if (/→ 404\b/.test(msg)) setAbsent(true);
        setErr(msg);
      });
    return () => {
      live = false;
    };
  }, [file, gameNum]);

  const game = data?.game ?? null;
  const timeline = useMemo(() => (game ? buildTimeline(game) : null), [game]);
  const summary = useMemo(() => (game ? summarizeGame(game) : null), [game]);
  const n = timeline?.steps.length ?? 0;

  const seats = useMemo(() => {
    if (!game) return [];
    return game.players.map((p) => {
      const commander = commanderGuess(stripAi(p), [game]);
      return {
        player: p,
        label: shortName(p, game.players),
        art: scryfallArt(commander),
        commander,
      };
    });
  }, [game]);

  // Back-link reads as the matchup; the filename stays in the footer.
  const backLabel = seats.length ? runTitle(seats.map((s) => s.label)) : file;

  const board = useMemo(() => (timeline ? foldTo(timeline, idx) : null), [timeline, idx]);
  const cur: Step | null = timeline && n > 0 ? timeline.steps[clamp(idx, 0, n - 1)] : null;

  // Static card facts (type line, P/T, oracle text) for every name this game
  // touches. Fetched once per game; the board groups itself by type line, so a
  // cold cache degrades to a single "Unidentified" row rather than breaking.
  const [cardMap, setCardMap] = useState<CardMap>({});
  useEffect(() => {
    if (!timeline || !game) return;
    let live = true;
    const names = new Set<string>();
    for (const p of game.players) {
      for (const c of foldTo(timeline, timeline.steps.length - 1).battlefield.get(p) ?? []) {
        names.add(c.name);
      }
    }
    for (const s of timeline.steps) {
      for (const h of s.hi ?? []) names.add(h);
    }
    for (const s of seats) if (s.commander) names.add(s.commander);
    loadCards(Array.from(names)).then((m) => live && setCardMap({ ...m }));
    return () => {
      live = false;
    };
  }, [timeline, game, seats]);

  const facts = useCallback(
    (name: string): CardFacts | undefined => cardMap[name.trim().toLowerCase()],
    [cardMap],
  );

  const seek = useCallback(
    (i: number) => {
      setPlaying(false);
      setIdx(clamp(i, 0, Math.max(0, n - 1)));
    },
    [n],
  );

  const jumpTurn = useCallback(
    (d: number) => {
      if (!timeline || !cur) return;
      const at = timeline.turns.findIndex((t) => t.turn === cur.turn);
      const j = clamp((at < 0 ? (d > 0 ? -1 : 0) : at) + d, 0, timeline.turns.length - 1);
      seek(timeline.turns[j]?.start ?? 0);
    },
    [timeline, cur, seek],
  );

  const playPause = useCallback(() => {
    setPlaying((p) => {
      if (!p && idx >= n - 1) setIdx(0); // replay from the top
      return !p;
    });
  }, [idx, n]);

  // playback clock
  useEffect(() => {
    if (!playing || n === 0) return;
    const id = setInterval(() => setIdx((p) => Math.min(p + 1, n - 1)), SPEED_MS[speed] ?? 300);
    return () => clearInterval(id);
  }, [playing, speed, n]);
  useEffect(() => {
    if (playing && idx >= n - 1) setPlaying(false);
  }, [playing, idx, n]);

  // ?t= deep link, once the timeline exists
  useEffect(() => {
    if (seeded.current || !timeline) return;
    seeded.current = true;
    const t = new URLSearchParams(window.location.search).get("t");
    if (t != null && Number.isFinite(Number(t))) {
      setIdx(clamp(Math.round(Number(t)), 0, timeline.steps.length - 1));
    }
  }, [timeline]);

  // keyboard: space play/pause, arrows step, shift+arrows jump turns
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.code === "Space") {
        e.preventDefault();
        playPause();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        if (e.shiftKey) jumpTurn(1);
        else seek(idx + 1);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        if (e.shiftKey) jumpTurn(-1);
        else seek(idx - 1);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [idx, seek, jumpTurn, playPause]);

  // keep the feed pinned to the playhead (scroll the list only, not the page)
  useEffect(() => {
    const list = listRef.current;
    const row = curRef.current;
    if (!list || !row) return;
    const lr = list.getBoundingClientRect();
    const rr = row.getBoundingClientRect();
    list.scrollTop += rr.top - lr.top - lr.height / 2 + rr.height / 2;
  }, [idx]);

  const copyLink = useCallback(() => {
    const url = `${window.location.origin}${window.location.pathname}?t=${idx}`;
    navigator.clipboard
      ?.writeText(url)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      })
      .catch(() => {});
  }, [idx]);

  const tabs = [
    { label: "Overview", href: `/results/${enc}` },
    { label: "Replay", href: "#", on: true },
  ];

  if (err) {
    return (
      <>
        <Chrome tabs={tabs} />
        <div className="page">
          <Link className="back q" href={`/results/${enc}`}>‹ {backLabel}</Link>
          <div className="head">
            <div>
              <h1>Game {gameNum}</h1>
              <div className="sub">
                {absent
                  ? "No such game in this run"
                  : wait != null
                    ? "Rate limited"
                    : "Could not load this replay"}
              </div>
            </div>
          </div>
          {absent ? (
            <p className="note">
              This run has no game <span className="mono">{gameNum}</span>. Pick one from the{" "}
              <Link className="bl" href={`/results/${enc}`}>
                run overview
              </Link>
              .
            </p>
          ) : wait != null ? (
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
  if (!data || !timeline || !game || !board || !summary || !cur) {
    return (
      <>
        <Chrome tabs={tabs} />
        <div className="page">
          <Link className="back q" href={`/results/${enc}`}>‹ {backLabel}</Link>
          <div className="head">
            <div>
              <h1>Game {gameNum}</h1>
              <div className="sub">Loading replay…</div>
            </div>
          </div>
        </div>
        <Footer />
      </>
    );
  }

  // Rounds, not Forge's per-player turn counter: at a table every player
  // gets a turn 1, so the raw counter reads 4x too high to a Magic player.
  const R = timeline.totalRounds;
  const frac = n > 1 ? (idx / (n - 1)) * 100 : 0;
  const tickEvery = Math.max(1, Math.ceil(R / 8));
  const ticks = timeline.turns.filter(
    (t, i) => t.round % tickEvery === 0 && (i === 0 || timeline.turns[i - 1].round !== t.round),
  );
  const decidingIdx = timeline.turns.length ? timeline.turns[timeline.turns.length - 1].start : 0;
  const lo = Math.max(0, idx - 40);
  const hi = Math.min(n, idx + 41);
  const phaseLabel = cur.round > 0 ? `Round ${cur.round} · ${cur.phase.replace(/ step$/i, "").toLowerCase()}` : "Pregame";
  return (
    <>
      <Chrome tabs={tabs} />
      <div className="page">
        <Link className="back q" href={`/results/${enc}`}>‹ {backLabel}</Link>
        <div className="head">
          <div>
            <h1>Game {gameNum}</h1>
            <div className="sub">
              {seats.map((s) => s.label).join(" · ")}
              <span className="sep">·</span>
              <span className="mono">{R}</span> rounds
              <span className="sep">·</span>
              <span className="mono">{fmtClock(summary.durationMs)}</span>
            </div>
          </div>
          <div className="btns">
            <button className="btn" onClick={copyLink}>
              {copied ? "Copied" : "Copy link at this event"}
            </button>
          </div>
        </div>

        <p className="lede">
          {summary.draw ? (
            <>This game ended in a <b>draw</b> after {R} rounds.</>
          ) : (
            <>
              <b>{summary.winnerName}</b> won on <b>round {summary.endedRound}</b> via {summary.decidedBy}.
            </>
          )}{" "}
          <span className="only-fine-pointer">Use space to play; arrows step events. </span>
          <a
            className="bl"
            href={`?t=${decidingIdx}`}
            onClick={(e) => {
              e.preventDefault();
              seek(decidingIdx);
            }}
          >
            Jump to the deciding turn
          </a>
        </p>

        <div className="stage">
          <div>
            <div className="theater">
              <div className="ttool">
                <span className="now">{phaseLabel}</span>
                <span className="right">
                  <select
                    className="sel"
                    value={String(speed)}
                    onChange={(e) => setSpeed(Number(e.target.value))}
                    aria-label="Playback speed"
                  >
                    <option value="1">1× speed</option>
                    <option value="2">2×</option>
                    <option value="4">4×</option>
                  </select>
                  <span>
                    event <span className="mono">{idx + 1}</span> of <span className="mono">{n}</span>
                  </span>
                </span>
              </div>

              <Tabletop
                board={board}
                seats={seats}
                activePlayer={cur.active}
                facts={facts}
              />
              <TabletopNote />


              <div className="vcr">
                <button className="vbtn" title="Previous turn" onClick={() => jumpTurn(-1)}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M19 20 9 12l10-8v16Z" />
                    <path d="M5 19V5" />
                  </svg>
                </button>
                <button className="vbtn" title="Step back" onClick={() => seek(idx - 1)}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m15 18-6-6 6-6" />
                  </svg>
                </button>
                <button className="vbtn play" title={playing ? "Pause" : "Play"} onClick={playPause}>
                  {playing ? (
                    <svg viewBox="0 0 24 24">
                      <path d="M8 5h3.2v14H8zM12.8 5H16v14h-3.2z" fill="currentColor" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24">
                      <path d="M8 5v14l11-7L8 5Z" fill="currentColor" />
                    </svg>
                  )}
                </button>
                <button className="vbtn" title="Step forward" onClick={() => seek(idx + 1)}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m9 18 6-6-6-6" />
                  </svg>
                </button>
                <button className="vbtn" title="Next turn" onClick={() => jumpTurn(1)}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m5 4 10 8-10 8V4Z" />
                    <path d="M19 5v14" />
                  </svg>
                </button>
                <div
                  className="scrub"
                  onClick={(e) => {
                    const r = e.currentTarget.getBoundingClientRect();
                    seek(Math.round(((e.clientX - r.left) / r.width) * (n - 1)));
                  }}
                >
                  <div className="rail2" />
                  <div className="done" style={{ width: `${frac}%` }} />
                  <div className="headk" style={{ left: `${frac}%` }} />
                  {ticks.map((t) => {
                    const left = `${n > 1 ? (t.start / (n - 1)) * 100 : 0}%`;
                    return (
                      <Fragment key={t.turn}>
                        <div className="tick" style={{ left }} />
                        <div className="ticklab" style={{ left }}>
                          R{t.round}
                        </div>
                      </Fragment>
                    );
                  })}
                </div>
                <div className="clock">
                  round {cur.round > 0 ? cur.round : "–"} of {R}
                </div>
              </div>
            </div>

            <p className="note only-fine-pointer">
              Keyboard: <span className="mono">space</span> play or pause ·{" "}
              <span className="mono">← →</span> step one event ·{" "}
              <span className="mono">shift ← →</span> jump a turn.
            </p>
            {/* Stays at every width and on every input: it is the honesty note,
                not a keyboard hint. "on the right" was also wrong on a phone,
                where the log stacks below the table. */}
            <p className="note">
              Replays fold the event log into board state locally. The event log is the
              authoritative record.
            </p>
          </div>

          <div>
            <div className="sh">
              <h2>Event log</h2>
              <span className="meta">follows the playhead</span>
            </div>
            <div className="loglist" ref={listRef}>
              {timeline.steps.slice(lo, hi).map((s, k) => {
                const i = lo + k;
                const isCur = i === idx;
                return (
                  <div
                    key={`${s.seq}-${i}`}
                    className={`ev${isCur ? " cur" : ""}`}
                    ref={isCur ? curRef : undefined}
                  >
                    <span className="tt">{s.round > 0 ? `R${s.round}` : "–"}</span>
                    <div>
                      <Hi text={s.text} hi={s.hi} />
                    </div>
                    {isCur && <span className="nowtag">now</span>}
                  </div>
                );
              })}
            </div>
            <div className="logfoot">
              <a
                className="bl"
                href={`?t=${decidingIdx}`}
                onClick={(e) => {
                  e.preventDefault();
                  seek(decidingIdx);
                }}
              >
                Skip to the deciding turn
              </a>
              <span className="mono">{n.toLocaleString()} events</span>
            </div>
          </div>
        </div>

        <PageDetails label="Game details">
          <div>{file}</div>
          <div>game {gameNum} of {data.games_total} · {n.toLocaleString()} events</div>
        </PageDetails>
      </div>
      <Footer />
    </>
  );
}
