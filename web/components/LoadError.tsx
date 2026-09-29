"use client";

/** Why a page could not load, in a player's words (repair plan WS11 task 7).
 *
 *  Pages used to print the raw fetch message ("GET /results/x/summary → 404:
 *  no such result") followed by "Check that the engine API is running", which
 *  is a path, a status code and an instruction for whoever runs the server.
 *  The raw message still shows in a dev build, where it is the useful part;
 *  the literal NODE_ENV comparison drops it from the production bundle. */

import { loadError } from "@/lib/format";

export function LoadError({ err, wait, what }: { err: string; wait: number | null; what: string }) {
  if (wait != null) {
    return (
      <p className="note">
        Too many requests right now. Try again in about <span className="mono">{wait}</span> s.
      </p>
    );
  }
  return (
    <p className="note">
      {loadError(err, what)}
      {process.env.NODE_ENV !== "production" && <> (dev build: {err})</>}
    </p>
  );
}
