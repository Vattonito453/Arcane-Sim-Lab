/** Shapes match engine/mtg_engine.py responses exactly — see frontend_handoff/API_SPEC.md */

export interface DeckEntry {
  file: string;
  name: string;
}

export interface ResultIndexEntry {
  file: string;
  bytes: number;
  modified: number; // unix seconds
  decks?: string[];
  games?: number;
  summary?: SimSummary;
  error?: string;
}

export interface SimSummary {
  games: number;
  draws: number;
  wins: Record<string, number>;
  win_rates: Record<string, number>; // 0..1, keys may carry "Ai(n)-" prefix
}

export interface SimEvent {
  seq: number;
  action:
    | "phase"
    | "land_drop"
    | "mana"
    | "stack_add"
    | "stack_resolve"
    | "damage"
    | "life_change"
    | "zone_change"
    | "combat"
    | "replacement_effect"
    | "player_control"
    | "game_outcome"
    | "match_result"
    | "discard"
    | string;
  raw: string;
  object?: string;
}

export interface SimTurn {
  turn: number;
  active_player: string;
  events: SimEvent[];
}

export interface SimGame {
  players: string[]; // "Ai(1)-Deck Name"
  turns: SimTurn[];
  events_pregame?: SimEvent[];
  result: { winner: string | null; draw: boolean; duration_ms: number; raw: string };
}

export interface SimResult {
  meta: { decks?: string[]; format?: string; [k: string]: unknown };
  games: SimGame[];
  summary: SimSummary;
}

/** GET /results/{file}/summary — a run without its event logs. */
export interface RunGameSummary {
  n: number;
  players: string[];
  result: SimGame["result"];
  turns: number;
  ended_turn: number | null;
  events: number;
}

export interface RunSummary {
  meta: SimResult["meta"];
  summary: SimSummary;
  games: RunGameSummary[];
  file: string;
}

/** GET /results/{file}/game/{n} — one game's full event log. */
export interface RunGame {
  meta: SimResult["meta"];
  file: string;
  n: number;
  games_total: number;
  game: SimGame;
}

export interface JobStatus {
  state: "idle" | "queued" | "running" | "done" | "error";
  id?: string;
  decks?: string[];
  games?: number;
  started?: number;
  elapsed?: number;
  error?: string | null;
  result?: SimSummary;
  result_file?: string;
  /** Queued jobs ahead of this one. Present only while state is "queued". */
  queued_ahead?: number;
}

/** GET /sim-live — the game currently being played, parsed from the partial
 *  Forge log. Same `game` shape as RunGame so the timeline fold is reused. */
export interface LiveGame {
  job_id: string;
  games_done: number;
  games_seen?: number;
  n: number;
  game: SimGame | null;
  in_progress: boolean;
  bytes: number;
}

export interface ImportReport {
  deck: string;
  commander: string;
  main_count: number;
  expected: number;
  ok: boolean;
  duplicates_nonbasic: string[];
  sideboard_dropped: number;
}

export interface ImportResponse {
  ok: boolean;
  error?: string;
  file?: string;
  saved?: boolean;
  report?: ImportReport;
}

export interface RuleHit {
  rule?: string;
  score?: number;
  text?: string;
  [k: string]: unknown;
}
