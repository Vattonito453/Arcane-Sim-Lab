"use client";

/** New run — /new
 *  The deck picker. Used to be the home page; home is now the splash hub, and
 *  "Run new simulation" / "Explore decklists" both land here. The ?deck= param
 *  preselects a deck (the import page links here after a save). */

import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { DeckEntry } from "@/lib/types";
import { estimateSeconds, fmtDuration, plural } from "@/lib/format";
import { Chrome, Footer } from "@/components/Chrome";
import ApiBaseSetting from "@/components/ApiBaseSetting";

const ENGINE_CMD = "python3 engine/mtg_engine.py serve 8484";

interface Health {
  rules: number;
  keywords: number;
  glossary_terms: number;
}

function NewRunInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselect = searchParams.get("deck");

  const [decks, setDecks] = useState<DeckEntry[] | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);
  const [healthErr, setHealthErr] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [selected, setSelected] = useState<string[]>([]);
  const [games, setGames] = useState(16);
  const [starting, setStarting] = useState(false);
  const [startErr, setStartErr] = useState<string | null>(null);
  const appliedPreselect = useRef(false);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    let stop = false;
    setDown(false);
    setHealthErr(false);
    api
      .health()
      .then((h) => {
        if (!stop) setHealth(h);
      })
      .catch(() => {
        if (!stop) {
          setHealth(null);
          setHealthErr(true);
        }
      });
    api
      .decks()
      .then((d) => {
        if (!stop) setDecks(d);
      })
      .catch(() => {
        if (!stop) {
          setDecks(null);
          setDown(true);
        }
      });
    return () => {
      stop = true;
    };
  }, [reloadKey]);

  useEffect(() => {
    if (appliedPreselect.current || !preselect || !decks) return;
    if (decks.some((d) => d.file === preselect)) {
      appliedPreselect.current = true;
      setSelected((prev) =>
        prev.includes(preselect) || prev.length >= 4 ? prev : [...prev, preselect]
      );
    }
  }, [preselect, decks]);

  const toggle = (file: string) => {
    setStartErr(null);
    setSelected((prev) => {
      if (prev.includes(file)) return prev.filter((f) => f !== file);
      if (prev.length >= 4) return prev;
      return [...prev, file];
    });
  };

  const canRun = selected.length >= 2 && selected.length <= 4;

  const start = async () => {
    if (!canRun || starting) return;
    setStarting(true);
    setStartErr(null);
    try {
      const r = await api.simulate(selected, games);
      if (!r.ok || !r.job_id) throw new Error("The engine refused the run — is another simulation in progress?");
      router.push(`/runs/${encodeURIComponent(r.job_id)}`);
    } catch (e) {
      setStartErr(e instanceof Error ? e.message : String(e));
      setStarting(false);
    }
  };

  const downNote = (
    <p className="note">
      <span className="st bad">
        <i />
        Engine unreachable
      </span>{" "}
      — is <span className="mono">{ENGINE_CMD}</span> running?{" "}
      <a
        className="q"
        href="#"
        onClick={(e) => {
          e.preventDefault();
          reload();
        }}
      >
        Retry
      </a>
    </p>
  );

  return (
    <>
      <Chrome context="New run" />
      <div className="page">
        <h1>New run</h1>

        {down ? (
          <p className="lede">
            The engine at the configured address isn&apos;t answering. Start it with{" "}
            <span className="mono">{ENGINE_CMD}</span> and retry — nothing here is lost.
          </p>
        ) : !decks ? (
          <p className="lede">Loading decks…</p>
        ) : (
          <p className="lede">
            <b>{decks.length} decks</b> on this engine. Pick two to four and run a gauntlet —
            results land under <Link className="bl" href="/results">Results</Link>.
          </p>
        )}

        <section>
          <div className="sh">
            <h2>Pick decks</h2>
            <span className="meta">two to four</span>
            <span className="right">
              <ApiBaseSetting onChanged={reload} />
              <span className="meta"> · </span>
              {health ? (
                <span className="meta">
                  <span className="mono">{health.rules.toLocaleString("en-US")}</span> rules loaded
                </span>
              ) : healthErr ? (
                <span className="st bad">
                  <i />
                  Engine unreachable
                </span>
              ) : (
                <span className="meta">checking engine…</span>
              )}
              <span className="meta"> · </span>
              <Link className="bl" href="/import">
                Import a deck →
              </Link>
            </span>
          </div>

          {down ? (
            downNote
          ) : !decks ? (
            <p className="note">Loading decks…</p>
          ) : decks.length === 0 ? (
            <p className="note">
              No decks on this engine yet —{" "}
              <Link className="bl" href="/import">
                import one
              </Link>{" "}
              to get started.
            </p>
          ) : (
            <>
              <div className="tblwrap">
                <div className="toolrow">
                  {selected.length === 0
                    ? "Select decks by clicking rows"
                    : `${selected.length} of 2–4 selected`}
                  <span className="upd">{decks.length} decks</span>
                </div>
                <table className="games">
                  <tbody>
                    {decks.map((d) => {
                      const on = selected.includes(d.file);
                      return (
                        <tr key={d.file} className="click" onClick={() => toggle(d.file)}>
                          <td>
                            <input
                              type="checkbox"
                              checked={on}
                              aria-label={`Select ${d.name}`}
                              onClick={(e) => e.stopPropagation()}
                              onChange={() => toggle(d.file)}
                            />
                          </td>
                          <td>
                            <div className="by">{d.name}</div>
                          </td>
                          <td className="mono">{d.file}</td>
                          <td className="r">
                            <Link
                              className="bl"
                              href={`/playtest/${encodeURIComponent(d.file)}`}
                              onClick={(e) => e.stopPropagation()}
                            >
                              Playtest
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="ctarow">
                <select
                  className="sel"
                  value={games}
                  aria-label="Games to simulate"
                  onChange={(e) => setGames(Number(e.target.value))}
                >
                  <option value={1}>1 game</option>
                  <option value={2}>2 games</option>
                  <option value={8}>8 games</option>
                  <option value={16}>16 games</option>
                  <option value={32}>32 games</option>
                </select>
                {/* The primary stays live (DESIGN_SYSTEM.md §6): when the run
                    can't start, the blocker is stated beside it instead. */}
                <button
                  className="btn pri"
                  aria-disabled={!canRun || starting}
                  aria-describedby={!canRun ? "run-blocker" : undefined}
                  onClick={() => void start()}
                >
                  {starting ? "Starting run…" : `Run ${plural(games, "game")}`}
                </button>
                {!canRun && (
                  <span className="ctanote" id="run-blocker">
                    Pick at least 2 decks — you have {selected.length}.
                  </span>
                )}
                {canRun && (
                  // Shown before you commit, because the cost is driven by pod
                  // size far more than by game count: four decks is ~20x the
                  // per-game time of two.
                  <span className="ctanote">
                    about <span className="mono">{fmtDuration(estimateSeconds(games, selected.length))}</span>
                    {games === 1 ? " — you can watch this one play out" : ""}
                  </span>
                )}
              </div>
              {startErr && (
                <p className="note">
                  <span className="st bad">
                    <i />
                    Couldn&apos;t start
                  </span>{" "}
                  {startErr}
                </p>
              )}
            </>
          )}
        </section>

      </div>
      <Footer
        right={
          health
            ? `${health.rules.toLocaleString("en-US")} rules · ${health.keywords} keywords`
            : undefined
        }
      />
    </>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <NewRunInner />
    </Suspense>
  );
}
