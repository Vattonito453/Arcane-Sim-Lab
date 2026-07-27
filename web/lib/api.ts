/** Engine API client. Base URL is runtime-configurable per API_SPEC.md:
 *  localStorage "simlab.apiBase" → NEXT_PUBLIC_API_BASE → http://127.0.0.1:8484 */
import type {
  DeckEntry, ImportResponse, JobStatus, ResultIndexEntry, RunGame, RunSummary,
  SimResult,
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

/** API key for write endpoints (/simulate, /decks). Reads stay public. */
export function apiKey(): string {
  if (typeof window !== "undefined") {
    return window.localStorage.getItem("simlab.apiKey") ?? "";
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
    throw new Error(msg || "this action needs an API key — set one under Engine");
  }
  throw new Error(`${method} ${path} → ${r.status}${msg ? `: ${msg.slice(0, 200)}` : ""}`);
}

async function get<T>(path: string, opts: { cache?: RequestCache } = {}): Promise<T> {
  const r = await fetch(`${apiBase()}${path}`, { cache: opts.cache ?? "no-store" });
  if (!r.ok) return fail(r, "GET", path);
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
  /** Whole run including every event log. Prefer runSummary/runGame. */
  result: (file: string) => get<SimResult>(`/results/${encodeURIComponent(file)}`),
  simulate: (decks: string[], games: number) =>
    post<{ ok: boolean; job_id: string; state: string }>("/simulate", { decks, games }),
  simStatus: (id?: string) => get<JobStatus>(`/sim-status${id ? `?id=${encodeURIComponent(id)}` : ""}`),
  importDeck: (name: string, text: string, commander?: string, save = true) =>
    post<ImportResponse>("/decks", { name, text, commander, save }),
  rule: (n: string) => get<Record<string, unknown>>(`/rule/${encodeURIComponent(n)}`),
  search: (q: string, k = 8) =>
    get<unknown[]>(`/search?q=${encodeURIComponent(q)}&k=${k}`),
};
