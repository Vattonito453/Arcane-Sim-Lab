"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { JobStatus, SimSummary } from "@/lib/types";
import { deckSlug, fmtDuration, pct, stripAi, timeAgo } from "@/lib/format";
import { Chrome, Footer } from "@/components/Chrome";

const ENGINE_CMD = "python3 engine/mtg_engine.py serve 8484";
const POLL_MS = 4000;
const SECONDS_PER_GAME = 45; // rough estimate for the indeterminate bar

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

  // The sandbox engine can answer {"error": ...} with no state — treat that as an error.
  const state = status ? (status.state ?? (status.error ? "error" : "idle")) : undefined;

  const decks = status?.decks ?? [];
  const deckNames = decks.map((d) => (d.endsWith(".dck") ? deckSlug(d) : stripAi(d)));
  const games = status?.games;
  const started = status?.started;
  const live = started ? Math.max(0, now / 1000 - started) : (status?.elapsed ?? 0);
  const elapsed = state === "done" || state === "error" ? (status?.elapsed ?? live) : live;
  const estimate = (games ?? 16) * SECONDS_PER_GAME;
  const progress = Math.min(95, Math.max(2, (live / estimate) * 100));
  const short = id.length > 12 ? id.slice(0, 12) : id;

  const resultBase = status?.result_file ? (status.result_file.split("/").pop() ?? null) : null;
  const resultHref = resultBase ? `/results/${encodeURIComponent(resultBase)}` : null;

  useEffect(() => {
    if (state === "done" && resultHref) {
      const t = setTimeout(() => router.push(resultHref), 1500);
      return () => clearTimeout(t);
    }
  }, [state, resultHref, router]);

  const res = status?.result;
  const win = res ? topWin(res) : null;

  return (
    <>
      <Chrome context={`run ${short}`} />
      <div className="page">
        {!status && !fetchErr && <p className="lede">Checking run status…</p>}

        {!status && fetchErr && (
          <>
            <h1>
              Run <span className="mono">{short}</span>
            </h1>
            <p className="lede">
              Can&apos;t reach the engine yet — this page retries every 4 seconds, so you can
              leave it open.
            </p>
            <p className="note">
              <span className="st bad">
                <i />
                Engine unreachable
              </span>{" "}
              — is <span className="mono">{ENGINE_CMD}</span> running?
            </p>
            <p className="note">
              <Link className="q" href="/">
                ‹ Back to Sim Lab
              </Link>
            </p>
          </>
        )}

        {status && (state === "queued" || state === "running") && (
          <>
            <h1>
              Run <span className="mono">{short}</span>
            </h1>
            <p className="lede">
              Simulating <b>{games ?? "—"} games</b> across <b>{decks.length} decks</b>
              {started ? <> — started {timeAgo(started)}</> : null}. You can leave; this page
              keeps polling.
            </p>
            <section>
              <div className="prog">
                <div className="fill" style={{ width: `${progress}%` }} />
              </div>
              <p className="note">
                Rough progress — a {games ?? 16}-game run usually takes about{" "}
                {fmtDuration(estimate)}.
              </p>
            </section>
            <div className="figs">
              <div className="fig">
                <div className="n">{fmtDuration(elapsed)}</div>
                <div className="l">elapsed</div>
              </div>
              <div className="fig">
                <div className="n">{games ?? "—"}</div>
                <div className="l">games requested</div>
              </div>
              <div className="fig">
                <div className="n">{decks.length}</div>
                <div className="l">decks in the pod</div>
              </div>
              <div className="fig">
                <span className="st run">
                  <i />
                  {state === "queued" ? "Queued" : "Running"}
                </span>
                <div className="l">state</div>
              </div>
            </div>
            {deckNames.length > 0 && <p className="note">Decks: {deckNames.join(" · ")}</p>}
            {fetchErr && (
              <p className="note">
                <span className="st warn">
                  <i />
                  Connection hiccup
                </span>{" "}
                — still polling every 4 seconds.
              </p>
            )}
          </>
        )}

        {status && state === "done" && (
          <>
            <div className="head">
              <div>
                <h1>
                  Run <span className="mono">{short}</span>
                </h1>
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
                  Done — <b>{stripAi(win[0])}</b> won{" "}
                  <b>
                    {res?.wins[win[0]] ?? 0} of {res?.games ?? games ?? 0} games ({pct(win[1])})
                  </b>
                  .
                </>
              ) : (
                <>Done — the run finished.</>
              )}{" "}
              {resultHref
                ? "Taking you to the full report…"
                : "The result file isn't listed yet — check past runs on the home page."}
            </p>
            <div className="figs">
              <div className="fig">
                <div className="n">{res?.games ?? games ?? "—"}</div>
                <div className="l">games played</div>
              </div>
              <div className="fig">
                <div className="n">{res?.draws ?? 0}</div>
                <div className="l">draws</div>
              </div>
              <div className="fig">
                <div className="n">{win ? pct(win[1]) : "—"}</div>
                <div className="l">{win ? `${stripAi(win[0])} win rate` : "top win rate"}</div>
              </div>
              <div className="fig">
                <div className="n">{fmtDuration(elapsed)}</div>
                <div className="l">wall-clock time</div>
              </div>
            </div>
            {deckNames.length > 0 && <p className="note">Decks: {deckNames.join(" · ")}</p>}
          </>
        )}

        {status && state === "error" && (
          <>
            <h1>
              Run <span className="mono">{short}</span>
            </h1>
            <p className="lede">
              The engine reported an error for this run — the message below is verbatim.
            </p>
            <p className="note">
              <span className="st bad">
                <i />
                Failed
              </span>{" "}
              {status.error ?? "Unknown engine error."}
            </p>
            <p className="note">
              <Link className="q" href="/">
                ‹ Back to Sim Lab
              </Link>
            </p>
          </>
        )}

        {status && state === "idle" && (
          <>
            <h1>
              Run <span className="mono">{short}</span>
            </h1>
            <p className="lede">
              The engine has no record of this run — it may have been restarted since the run was
              queued.
            </p>
            <p className="note">
              <Link className="q" href="/">
                ‹ Back to Sim Lab
              </Link>
            </p>
          </>
        )}
      </div>
      <Footer right={`job ${id}`} />
    </>
  );
}
