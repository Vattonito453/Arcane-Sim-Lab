"use client";

/** Predicted real-playgroup win rates, beside the raw simulation.
 *
 *  WHY THIS EXISTS. /results/{file}/prediction has worked for a while and had
 *  no web consumer at all, so the single most important claim the product
 *  makes -- that a raw sim win rate is NOT what a deck does against people,
 *  and that we can say by how much -- was reachable only by curling the API.
 *
 *  HONESTY CONTRACT (engine/SIM_CALIBRATION.md). This panel shows a MODEL
 *  OUTPUT, not a measurement, and must never be mistaken for one:
 *   - the raw sim number stays visible next to the corrected one, so the
 *     correction is legible as a correction rather than a replacement;
 *   - the interval is always shown, never the point estimate alone;
 *   - the basis (decks trained on, human games, out-of-sample error) is on
 *     the panel, not buried in a tooltip;
 *   - when the fitted model is absent the panel says so plainly instead of
 *     rendering zeros, which is exactly how this failed silently before.
 *
 *  All styling comes from globals.css; this file adds none.
 */

import type { PredictionReport } from "@/lib/types";

function pp(x: number): string {
  return `${x >= 0 ? "+" : ""}${x.toFixed(1)}`;
}

export function PredictionPanel({ report }: { report: PredictionReport | null }) {
  if (!report) return null;

  // Absent model: say it, do not draw an empty table. The reason string is
  // written by the engine and names the actual fix.
  if (!report.available || !report.decks || report.decks.length === 0) {
    return (
      <section>
        <div className="sh">
          <h2>Against real playgroups</h2>
        </div>
        <p className="note">
          No corrected win rates for this run. {report.reason ?? "The fitted model is not available."}
        </p>
      </section>
    );
  }

  const decks = [...report.decks].sort(
    (a, b) => b.expected_win_rate - a.expected_win_rate,
  );
  const basis = decks[0].basis;

  return (
    <section>
      <div className="sh">
        <h2>Against real playgroups</h2>
        <span className="meta">
          modelled, not simulated; {"±"}
          {decks[0].typical_error_pp.toFixed(1)} points typical error
        </span>
      </div>

      <p className="sdesc">
        A simulated win rate is not what a deck does against people. These are the
        raw figures corrected by a model fitted on {basis.trained_on_decks} decks and{" "}
        {basis.human_games.toLocaleString()} recorded human games, with the range each
        deck plausibly lands in.
      </p>

      <table className="telet">
        <thead>
          <tr>
            <th>Deck</th>
            <th className="r">Simulated</th>
            <th className="r">Expected</th>
            <th className="r">Range</th>
            <th className="r">Correction</th>
          </tr>
        </thead>
        <tbody>
          {decks.map((d) => (
            <tr key={d.deck}>
              <td>{d.deck}</td>
              <td className="r mono">{d.sim_win_rate.toFixed(1)}%</td>
              <td className="r mono">
                <b>{d.expected_win_rate.toFixed(1)}%</b>
              </td>
              <td className="r mono">
                {d.low.toFixed(1)} to {d.high.toFixed(1)}
              </td>
              <td className="r mono">
                {pp(d.expected_win_rate - d.sim_win_rate)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="note">
        Out-of-sample rank correlation {basis.loo_spearman.toFixed(2)} on leave-one-out
        testing, fitted against {basis.arm}. The model orders decks better than it pins
        any single number, so read the ranking first and the point estimate second. A
        correction of {pp(decks[0].expected_win_rate - decks[0].sim_win_rate)} points
        does not mean the simulation was wrong; it means the simulated table is harsher
        than a real one.
      </p>
    </section>
  );
}
