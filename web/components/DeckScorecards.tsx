"use client";

/** Per-deck scorecards for a finished run.
 *
 *  The results page could only say who won and how often. This says what each
 *  deck DID: how it won, how fast, what killed it, and how it actually played
 *  its combats and its opening hands. Everything here is a read of the result
 *  record or of the shim's neutral per-seat observer, which scores every seat
 *  on identical terms. Nothing is a model prediction.
 *
 *  A behaviour section is null on runs older than shim 0.9.0. Null means NOT
 *  RECORDED and is rendered as such: "did none of it" and "we did not watch"
 *  are different claims. */

import type { DeckScorecard, ScorecardReport } from "@/lib/types";
import { pct } from "@/lib/format";

/** Forge's own loss-line wording, shortened for a chip. */
function methodLabel(m: string): string {
  if (m === "combat damage / life loss") return "combat damage";
  if (m === "not recorded") return "method not recorded";
  return m;
}

function one(n: number, s: string, p: string): string {
  return n === 1 ? s : p;
}

/** The plain-English read: outcome, speed, and the single most notable thing
 *  this deck did. Deliberately short, deliberately never causal. Every clause
 *  carries the number it rests on so a reader can check it against the table
 *  below rather than take our word for it. */
function readOf(d: DeckScorecard, podMedianRound: number | null): string {
  const parts: string[] = [];
  const decided = d.games - d.censored;

  if (d.wins > 0) {
    const top = Object.entries(d.methods).sort((a, b) => b[1] - a[1])[0];
    const how = top ? ` by ${methodLabel(top[0])}` : "";
    const when = d.medianWinRound ? `, closing on round ${d.medianWinRound}` : "";
    parts.push(`Won ${d.wins} of ${decided}${how}${when}.`);
  } else if (decided > 0) {
    parts.push(`Won none of ${decided} decided ${one(decided, "game", "games")}.`);
  } else {
    parts.push("No decided games in this run.");
  }

  if (d.wins === 0 && d.medianDeathRound) {
    const gap =
      podMedianRound && podMedianRound > d.medianDeathRound
        ? ` (the table played to round ${podMedianRound})`
        : "";
    parts.push(`Knocked out on round ${d.medianDeathRound}${gap}.`);
  } else if (d.survivalRate !== null && d.wins > 0) {
    parts.push(`Still standing at the end of ${pct(d.survivalRate)} of them.`);
  }

  // At most ONE behavioural clause: the standout, not an inventory.
  const b = d.blocking;
  if (b && b.declined !== null && b.faced >= 8) {
    if (b.freeCapture !== null && b.freeCapture >= 0.9 && b.declined < 0.45) {
      parts.push(
        `Blocked tightly: took ${pct(b.freeCapture)} of the blocks that were free.`,
      );
    } else if (b.declined >= 0.55) {
      parts.push(
        `Let through ${pct(b.declined)} of the attackers it could have blocked.`,
      );
    }
  }
  return parts.join(" ");
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="scstat" title={hint}>
      <div className="scv">{value}</div>
      <div className="scl">{label}</div>
    </div>
  );
}

function Card({
  d, baseline, podMedianRound,
}: {
  d: DeckScorecard;
  baseline: number | null;
  podMedianRound: number | null;
}) {
  const rate = d.winRate ?? 0;
  const beats = baseline !== null && rate >= baseline;
  const methods = Object.entries(d.methods).sort((a, b) => b[1] - a[1]);
  const b = d.blocking;
  const a = d.attacking;
  const m = d.mulligans;

  return (
    <article className="sccard">
      <header className="schead">
        <h3>{d.deck}</h3>
        <span className={`st ${d.wins === 0 ? "bad" : beats ? "win" : "loss"}`}>
          <i />
          {d.wins} of {d.games - d.censored}
        </span>
        <span className="scrate mono">{d.winRate === null ? "–" : pct(d.winRate)}</span>
      </header>

      <div className="rail">
        <div className="fill" style={{ width: `${Math.max(rate * 100, d.wins > 0 ? 1 : 0)}%` }} />
        {baseline !== null && <div className="base" style={{ left: `${baseline * 100}%` }} />}
      </div>

      <p className="scread">{readOf(d, podMedianRound)}</p>

      <div className="scstats">
        <Stat
          label="median win round"
          value={d.medianWinRound ? String(d.medianWinRound) : "–"}
          hint="Table rounds, counted per player. Blank when the deck never won."
        />
        <Stat
          label="knocked out on"
          value={d.medianDeathRound ? `round ${d.medianDeathRound}` : "–"}
          hint="Median round this deck was eliminated, from Forge's own loss lines."
        />
        <Stat
          label="survived to the end"
          value={d.survivalRate === null ? "–" : pct(d.survivalRate)}
          hint="Share of decided games this deck was still alive in. Surviving is not winning."
        />
        <Stat
          label="how it won"
          value={methods.length ? methodLabel(methods[0][0]) : "–"}
          hint={methods.map(([k, n]) => `${methodLabel(k)}: ${n}`).join("\n")}
        />
      </div>

      {b || a || m ? (
        <div className="scplay">
          {b && (
            <div className="scgrp">
              <span className="scgl">Blocking</span>
              <span>
                blocked <b>{b.engage === null ? "–" : pct(b.engage)}</b> of{" "}
                {b.faced} attackers faced
              </span>
              {b.declined !== null && (
                <span>
                  let through <b>{pct(b.declined)}</b> it could have blocked
                </span>
              )}
              {b.freeCapture !== null && (
                <span>
                  took <b>{pct(b.freeCapture)}</b> of its free blocks
                </span>
              )}
            </div>
          )}
          {a && (
            <div className="scgrp">
              <span className="scgl">Attacking</span>
              {a.commitment !== null && (
                <span>
                  committed <b>{pct(a.commitment)}</b> of creatures that could attack
                </span>
              )}
              {a.defendersPerAttack !== null && (
                <span>
                  hit <b>{a.defendersPerAttack.toFixed(2)}</b> opponents per attack
                </span>
              )}
            </div>
          )}
          {m && (
            <div className="scgrp">
              <span className="scgl">Opening hands</span>
              {m.kept7 !== null && (
                <span>
                  kept seven <b>{pct(m.kept7)}</b> of the time
                </span>
              )}
              {m.landsKept !== null && (
                <span>
                  <b>{m.landsKept.toFixed(1)}</b> lands in the hand it kept
                </span>
              )}
            </div>
          )}
        </div>
      ) : null}
    </article>
  );
}

export function DeckScorecards({ report }: { report: ScorecardReport }) {
  const { decks, run } = report;
  if (!decks.length) return null;
  return (
    <section>
      <div className="sh">
        <h2>What each deck did</h2>
        <span className="meta">
          {run.decided} decided {one(run.decided, "game", "games")}
          {run.censored > 0 && <>, {run.censored} cut off by the clock</>}
        </span>
      </div>
      <div className="scgrid">
        {decks.map((d) => (
          <Card key={d.deck} d={d} baseline={run.baseline} podMedianRound={run.medianGameRound} />
        ))}
      </div>
      <p className="note">
        The marker on each bar sits at{" "}
        {run.baseline === null ? "an even share" : pct(run.baseline, 1)}, an even
        share of a {decks.length}-deck pod. Rounds are table rounds: every player
        gets a turn 1, then a turn 2. Games cut off by the per-game clock count
        as played but never as decided, so they cannot move a win rate.{" "}
        {run.hasBehaviour ? (
          <>
            Blocking, attacking and opening-hand figures are read from the
            simulation itself, scored the same way for every seat.
          </>
        ) : (
          <>
            Play-quality figures were not recorded for this run: it predates the
            observer that measures them. Re-run the gauntlet to collect them.
          </>
        )}
      </p>
    </section>
  );
}
