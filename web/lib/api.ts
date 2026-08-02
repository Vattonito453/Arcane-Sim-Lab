/** Engine API client. Base URL is runtime-configurable per API_SPEC.md:
 *  localStorage "simlab.apiBase" → NEXT_PUBLIC_API_BASE → http://127.0.0.1:8484 */
import type {
  AnalysisReport, CoachingReport, DeckCards, DeckEntry, ImportResponse,
  JobStatus, LiveGame, ResultIndexEntry, RuleLookup, RulesAnswer, RunGame,
  RunSummary, SimResult, TelemetryReport,
} from "./types";

export function apiBase(): string {
  if (typeof window !== "undefined") {
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
    throw new Error(msg || "this action needs an API key. Set one under Engine");
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

export const api = {
  health: () => get<{ rules: number; keywords: number; glossary_terms: number }>("/health"),
  decks: () => get<DeckEntry[]>("/decks"),
  /** One deck's card names, counts expanded — the playtest sandbox's load. */
  deck: (file: string) => get<DeckCards>(`/decks/${encodeURIComponent(file)}`),
  /** Remove an imported deck. Authed and destructive; bundled decks refuse. */
  deleteDeck: (file: string) =>
    del<{ ok: boolean; deleted?: string; error?: string }>(
      `/decks/${encodeURIComponent(file)}`,
    ),
  results: () => get<ResultIndexEntry[]>("/results"),

  /** Run overview WITHOUT event logs — a few KB instead of ~2.6 MB. */
  runSummary: (file: string) =>
    get<RunSummary>(`/results/${encodeURIComponent(file)}/summary`, { cache: "force-cache" }),
  /** One game's full event log — what a replay needs (~20 KB gzipped). */
  runGame: (file: string, n: number, snapshots = false) =>
    get<RunGame>(
      `/results/${encodeURIComponent(file)}/game/${n}${snapshots ? "?snapshots=1" : ""}`,
      { cache: "force-cache" },
    ),
  /** Win-condition telemetry for one deck — computed server-side so the
   *  browser never fetches the whole ~235 KB run (CLAUDE.md gotcha 4). */
  runTelemetry: (file: string, deck: string, watch?: string[]) =>
    get<TelemetryReport>(
      `/results/${encodeURIComponent(file)}/telemetry?deck=${encodeURIComponent(deck)}` +
        (watch?.length ? `&watch=${encodeURIComponent(watch.join("|"))}` : ""),
      { cache: "force-cache" },
    ),
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
