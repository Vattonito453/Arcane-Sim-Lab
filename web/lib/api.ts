/** Engine API client. Base URL per API_SPEC.md:
 *  localStorage "simlab.apiBase" (dev builds only) → NEXT_PUBLIC_API_BASE →
 *  http://127.0.0.1:8484 */
import type {
  AnalysisReport,
  CoachingReport,
  DeckCards,
  DeckEntry,
  ImportResponse,
  JobStatus,
  LiveGame,
  ResultIndexEntry,
  RuleLookup,
  RulesAnswer,
  RunGame,
  RunSummary,
  PredictionReport,
  ScorecardReport,
  SimResult,
  TelemetryReport,
} from "./types";

/** The saved override is honoured only in dev builds. The only control that
 *  writes it (ApiBaseSetting) renders only in dev, so a production build that
 *  still read it would strand any player who once saved a bad address there
 *  (it used to sit in the public phone nav): every page would say the server
 *  isn't answering, forever, with nothing in the UI to clear it. The literal
 *  NODE_ENV comparison lets the minifier drop the branch from the production
 *  bundle (see SERVER_DOWN in format.ts). */
export function apiBase(): string {
  if (process.env.NODE_ENV !== "production" && typeof window !== "undefined") {
    const saved = window.localStorage.getItem("simlab.apiBase");
    if (saved) return saved.replace(/\/$/, "");
  }
  return (process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8484").replace(/\/$/, "");
}

export function setApiBase(url: string) {
  window.localStorage.setItem("simlab.apiBase", url.replace(/\/$/, ""));
}

/** API key for write endpoints (/simulate, /decks). Reads stay public.
 *
 *  Same precedence as apiBase(): a key saved in this browser wins, otherwise the
 *  build-time default. The env fallback used to sit behind the `typeof window`
 *  check, which made it server-only — and since every caller is a client
 *  component fetching from an effect, it was never reachable. A deployment with
 *  MTG_API_KEYS set therefore had no way to authenticate a write at all, so
 *  "Start run" failed for everyone. Note NEXT_PUBLIC_* is inlined into the
 *  client bundle: this is a shared key for a trusted playtest group, not a
 *  per-user secret (tasks/06 replaces it with real identity). */
export function apiKey(): string {
  if (typeof window !== "undefined") {
    const saved = window.localStorage.getItem("simlab.apiKey");
    if (saved) return saved;
  }
  return process.env.NEXT_PUBLIC_API_KEY ?? "";
}

export function setApiKey(key: string) {
  if (key) window.localStorage.setItem("simlab.apiKey", key);
  else window.localStorage.removeItem("simlab.apiKey");
}

/** The playtester's flags-only key ("Flag this moment", POST /flags).
 *
 *  Its own storage key, never mixed with simlab.apiKey: a flag key can flag and
 *  nothing else, and it is sent ONLY with sendFlag() below, never by get/post/
 *  del. Every accessor tolerates storage that throws (private windows, blocked
 *  site data): the form then simply asks for the key each time. */
const FLAG_KEY_STORAGE = "simlab.flagKey";

export function savedFlagKey(): string {
  try {
    return window.localStorage.getItem(FLAG_KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

export function saveFlagKey(key: string): void {
  try {
    if (key) window.localStorage.setItem(FLAG_KEY_STORAGE, key);
    else window.localStorage.removeItem(FLAG_KEY_STORAGE);
  } catch {
    /* storage unavailable: the key is used for this send only */
  }
}

/** Where a flag points. `event_index` is the replay's step index (its ?t=);
 *  the engine derives the turn itself and cross-checks `event_seq` and `turn`,
 *  answering 409 when this browser's copy of the game is stale. */
export interface FlagAnchor {
  event_index: number;
  event_seq?: number;
  turn?: number;
  /** Raw seat key ("Ai(2)-Deck"), or null for "not about one seat". */
  player?: string | null;
}

export interface FlagRequest {
  run: string;
  game: number;
  anchor: FlagAnchor;
  note: string;
}

export interface FlagReceipt {
  ok: boolean;
  id: string;
  reporter: string;
  created: string;
}

/** A refused or failed flag, with what the form needs to explain it. */
export class FlagError extends Error {
  status: number; // 0 = the request never got an answer
  retryAfter: number;
  constructor(message: string, status: number, retryAfter = 0) {
    super(message);
    this.name = "FlagError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

/** POST /flags with the flag key and nothing else as the credential. */
export async function sendFlag(req: FlagRequest, flagKey: string): Promise<FlagReceipt> {
  let r: Response;
  try {
    r = await fetch(`${apiBase()}/flags`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(flagKey ? { Authorization: `Bearer ${flagKey}` } : {}),
      },
      body: JSON.stringify(req),
    });
  } catch (e) {
    throw new FlagError(e instanceof Error ? e.message : String(e), 0);
  }
  let body: { error?: unknown; retry_after?: unknown } & Partial<FlagReceipt> = {};
  try {
    body = await r.json();
  } catch {
    /* a proxy error page, say: the status alone has to explain it */
  }
  if (!r.ok) {
    const retry = Number(r.headers.get("Retry-After") ?? body.retry_after ?? 0) || 0;
    throw new FlagError(typeof body.error === "string" ? body.error : "", r.status, retry);
  }
  return body as FlagReceipt;
}

/** Thrown for 429/503 so callers can show the wait instead of a raw error. */
export class RateLimited extends Error {
  retryAfter: number;
  constructor(message: string, retryAfter: number) {
    super(message);
    this.name = "RateLimited";
    this.retryAfter = retryAfter;
  }
}

async function fail(r: Response, method: string, path: string): Promise<never> {
  let msg = "";
  let retry = Number(r.headers.get("Retry-After") ?? 0);
  try {
    const j = await r.json();
    msg = typeof j?.error === "string" ? j.error : JSON.stringify(j);
    if (!retry && typeof j?.retry_after === "number") retry = j.retry_after;
  } catch {
    msg = await r.text().catch(() => "");
  }
  if (r.status === 429 || r.status === 503) {
    throw new RateLimited(msg || "rate limited", retry || 60);
  }
  if (r.status === 401) {
    // Was "Set one under Engine", but nothing in the interface sets a key: the
    // key is baked into the build (NEXT_PUBLIC_API_KEY) or saved by hand.
    throw new Error(msg || "this server needs a key to do that, and this site isn't sending one");
  }
  throw new Error(`${method} ${path} → ${r.status}${msg ? `: ${msg.slice(0, 200)}` : ""}`);
}

async function get<T>(path: string, opts: { cache?: RequestCache } = {}): Promise<T> {
  const r = await fetch(`${apiBase()}${path}`, { cache: opts.cache ?? "no-store" });
  if (!r.ok) return fail(r, "GET", path);
  return r.json();
}

async function del<T>(path: string): Promise<T> {
  const key = apiKey();
  const r = await fetch(`${apiBase()}${path}`, {
    method: "DELETE",
    headers: key ? { Authorization: `Bearer ${key}` } : {},
  });
  if (!r.ok) return fail(r, "DELETE", path);
  return r.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const key = apiKey();
  const r = await fetch(`${apiBase()}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(key ? { Authorization: `Bearer ${key}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) return fail(r, "POST", path);
  return r.json();
}

/** GET /health: KB stats, plus whether generation is switched on at all. */
export interface Health {
  rules: number;
  keywords: number;
  glossary_terms: number;
  /** A boolean flag only; the key itself is never sent to the browser.
   *  Optional so an older engine still typechecks. */
  llm?: boolean;
  llm_model?: string | null;
  /** The game-story display switches in force (engine/game_story.py). The
   *  payloads already apply them; this is for operators. */
  story?: {
    turning_point: "swing" | "audited" | "off";
    turning_point_label: string | null;
    knockout_detail: boolean;
    invalid: string[];
  } | null;
}

/** GET /estimate: what a sim of this size will play and how long it usually
 *  takes, before it is queued. The same numbers /sim-status reports once the
 *  job exists, so the button and the run page can never disagree. */
export interface SimEstimate {
  decks: number;
  games_requested: number;
  /** Rounded up to whole seat rotations: every deck sits in every seat the
   *  same number of times, so this can be MORE than requested. */
  games_to_play: number;
  rotations: number;
  /** [low, high] seconds a sim this size typically takes. Not a timeout. */
  typical_seconds: [number, number];
}

/** Query tag on the summary and game payloads. Until R1 the engine served
 *  both as immutable and the client fetched them with force-cache, so any
 *  browser that had opened a run holds the pre-R1 payload (no game story, no
 *  commanders) under the bare URL for a year. A new URL is the only way past
 *  that cache; the engine now sends max-age=300 because the story follows
 *  server-side switches, and these fetches use the default cache mode so the
 *  header is honoured. Bump this only when a payload change must reach
 *  browsers at once. The engine ignores the parameter. */
const PAYLOAD_TAG = "v=r1";

let healthMemo: Promise<Health> | null = null;

/** /health, fetched once per page load and shared. The flags it carries only
 *  change on a redeploy, and several components ask (the tab row hides
 *  Coaching while `llm` is false). A failure is not remembered, so the next
 *  caller tries again. */
export function healthOnce(): Promise<Health> {
  if (!healthMemo) {
    healthMemo = api.health().catch((e: unknown) => {
      healthMemo = null;
      throw e;
    });
  }
  return healthMemo;
}

export const api = {
  health: () => get<Health>("/health"),
  estimate: (decks: number, games: number) =>
    get<SimEstimate>(`/estimate?decks=${decks}&games=${games}`),
  decks: () => get<DeckEntry[]>("/decks"),
  /** One deck's card names, counts expanded — the playtest sandbox's load. */
  deck: (file: string) => get<DeckCards>(`/decks/${encodeURIComponent(file)}`),
  /** Remove an imported deck. Authed and destructive; bundled decks refuse. */
  deleteDeck: (file: string) =>
    del<{ ok: boolean; deleted?: string; error?: string }>(
      `/decks/${encodeURIComponent(file)}`,
    ),
  results: () => get<ResultIndexEntry[]>("/results"),

  /** Run overview WITHOUT event logs — a few KB instead of ~2.6 MB — with
   *  each game's story, the decks' commanders and the pilot. */
  runSummary: (file: string) =>
    get<RunSummary>(`/results/${encodeURIComponent(file)}/summary?${PAYLOAD_TAG}`, {
      cache: "default",
    }),
  /** One game's full event log and its story — what a replay needs (~21 KB
   *  gzipped). */
  runGame: (file: string, n: number, snapshots = false) =>
    get<RunGame>(
      `/results/${encodeURIComponent(file)}/game/${n}?${PAYLOAD_TAG}${snapshots ? "&snapshots=1" : ""}`,
      { cache: "default" },
    ),
  /** Win-condition telemetry for one deck — computed server-side so the
   *  browser never fetches the whole ~235 KB run (CLAUDE.md gotcha 4). */
  runTelemetry: (file: string, deck: string, watch?: string[]) =>
    get<TelemetryReport>(
      `/results/${encodeURIComponent(file)}/telemetry?deck=${encodeURIComponent(deck)}` +
        (watch?.length ? `&watch=${encodeURIComponent(watch.join("|"))}` : ""),
      { cache: "force-cache" },
    ),
  /** Per-deck scorecards: outcomes, timing, and play quality. A few KB, and
   *  the only place the shim's neutral per-seat records reach the browser. */
  runScorecards: (file: string) =>
    get<ScorecardReport>(`/results/${encodeURIComponent(file)}/scorecards`),
  /** Predicted real-playgroup win rates, corrected off the raw sim.
   *
   *  This endpoint has existed and worked for a while and had NO web consumer
   *  at all, so the correction the whole calibration argument rests on was
   *  invisible to users. It answers {available:false, reason} when the fitted
   *  model is not present, so every caller must handle that rather than
   *  assume decks[]. */
  runPrediction: (file: string) =>
    get<PredictionReport>(`/results/${encodeURIComponent(file)}/prediction`),
  /** Wincon report: win methods + combo assembly/conversion. Deliberately NOT
   *  force-cached: the payload carries an analysis version and evolves — a
   *  browser that pinned v1 under an immutable header kept serving it after the
   *  engine moved on. The report is a few KB and the engine disk-caches the
   *  computation, so refetching costs almost nothing. */
  analysis: (file: string) =>
    get<AnalysisReport>(`/analysis/${encodeURIComponent(file)}`),
  /** Whole run including every event log. Prefer runSummary/runGame. */
  result: (file: string) => get<SimResult>(`/results/${encodeURIComponent(file)}`),
  simulate: (decks: string[], games: number) =>
    post<{ ok: boolean; job_id: string; state: string }>("/simulate", { decks, games }),
  simStatus: (id?: string) => get<JobStatus>(`/sim-status${id ? `?id=${encodeURIComponent(id)}` : ""}`),
  /** A game from the run in flight. 404s until Forge has written its first
   *  line; `game` past the newest is clamped, so asking early is safe. */
  simLive: (id: string, game?: number) =>
    get<LiveGame>(
      `/sim-live?id=${encodeURIComponent(id)}${game ? `&game=${game}` : ""}`,
    ),
  importDeck: (name: string, text: string, commander?: string, save = true) =>
    post<ImportResponse>("/decks", { name, text, commander, save }),
  rule: (n: string) => get<RuleLookup>(`/rule/${encodeURIComponent(n)}`),
  search: (q: string, k = 8) =>
    get<unknown[]>(`/search?q=${encodeURIComponent(q)}&k=${k}`),
  /** Cache-only read of a coaching report. Never spends tokens. */
  coaching: (file: string, deck: string) =>
    get<CoachingReport>(
      `/coaching/${encodeURIComponent(file)}?deck=${encodeURIComponent(deck)}`,
    ),
  /** Generate a coaching report. Authed + quota'd paid-token path; the
   *  engine caches one report per (deck, gauntlet) forever. */
  coach: (file: string, deck: string) =>
    post<CoachingReport>("/coaching", { result_file: file, deck }),
  /** Generate a grounded rules answer. Authed + quota'd: the only paid-token
   *  path besides coaching. Cached server-side per normalized question. */
  ask: (q: string) => post<RulesAnswer>("/ask", { q }),
  /** Cache-only read of a previously generated answer. Never spends tokens. */
  askCached: (q: string) =>
    get<RulesAnswer>(`/ask?q=${encodeURIComponent(q)}`),
};
