/** Shapes match engine/mtg_engine.py responses exactly — see frontend_handoff/API_SPEC.md */

export interface DeckEntry {
  file: string;
  name: string;
  /** From the .dck [Commander] section; null when the deck has none. The
   *  picker resolves art + color identity through /cards, batched. */
  commander?: string | null;
  source?: "imported" | "bundled";
}

/** GET /decks/{file} — one deck's contents, counts expanded. Pure data for
 *  the playtest sandbox and the deck page: no legality, no rules. */
export interface DeckCards {
  file: string;
  name: string;
  /** "imported" decks are deletable; "bundled" ship inside the image. */
  source?: "imported" | "bundled";
  commanders: string[];
  main: string[];
}

export interface ResultIndexEntry {
  file: string;
  bytes: number;
  modified: number; // unix seconds
  decks?: string[];
  games?: number;
  summary?: SimSummary;
  /** Seat-rotated, so win rates are comparable across decks. */
  rotated?: boolean;
  /** True when every seat ran a plan agent, false for stock Forge. */
  humanized?: boolean;
  agent?: string;
  validity?: Validity;
  error?: string;
}

export interface SimSummary {
  games: number;
  draws: number;
  /** Games the per-game clock cut off. Counted inside `draws` as well, since a
   *  clock-cut game has no real winner. Absent on results written before
   *  2026-08-03. */
  timeouts?: number;
  wins: Record<string, number>;
  win_rates: Record<string, number>; // 0..1, keys may carry "Ai(n)-" prefix
}

/** engine/validity.py — whether a run's numbers can be trusted, and why not. */
export type ValidityQuality = "clean" | "suspect" | "polluted";

export interface Validity {
  quality: ValidityQuality;
  flags: string[];
  usable_for_ranking: boolean;
  reasons: string[];
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
  /** Board-state stream from shim >= 0.12.0: per-card tap state, counter
   *  totals, attachments. Absent on older results; every reader must cope. */
  boardfx?: BoardFxRec[];
  /** Zone-change stream (shim path). Hidden zones included: the shim reads
   *  the game in-process, so hands are EXACT, unlike the inferred board.
   *  `phase` from shim >= 0.13.0. */
  zones?: ZoneRec[];
}

export interface ZoneRec {
  turn: number;
  phase?: string;
  card: string;
  cardId: number;
  from: string;
  to: string;
  fromPlayer?: string;
  toPlayer?: string;
}

export interface BoardFxRec {
  rec: "tap" | "counters" | "attach";
  turn: number;
  phase?: string; // Forge PhaseType enum name, e.g. "MAIN1"
  cardId: number;
  card: string;
  tapped?: boolean; // rec === "tap"
  type?: string; // rec === "counters": counter type name, e.g. "P1P1"
  n?: number; // rec === "counters": new total of that type
  to?: string | null; // rec === "attach": target name, null = detached
}

/** Per-deck scorecard from GET /results/{file}/scorecards. Behaviour
 *  sections are null on runs older than shim 0.9.0: null means NOT RECORDED,
 *  never zero, and the UI must render the difference. */
export interface DeckScorecard {
  deck: string;
  games: number;
  wins: number;
  draws: number;
  censored: number;
  winRate: number | null;
  survivalRate: number | null;
  medianWinRound: number | null;
  medianDeathRound: number | null;
  methods: Record<string, number>;
  /** Land drops per own turn. The one play-quality figure every archived run
   *  can answer: land_drop is an adapter action on both engine paths. */
  landsPerTurn: number | null;
  ownTurns: number;
  blocking: {
    combats: number; faced: number;
    engage: number | null; declined: number | null;
    freeOpportunities: number; blocksMade: number;
    freeCapture: number | null; safeCapture: number | null;
    chumpShare: number | null;
    damagePerCombat: number | null;
  } | null;
  attacking: {
    combats: number; attackersPerCombat: number | null;
    commitment: number | null; defendersPerAttack: number | null;
    keptEnough: number | null;
  } | null;
  mulligans: {
    seatGames: number; kept7: number | null;
    mullsPerGame: number | null; landsKept: number | null;
  } | null;
}

export interface ScorecardReport {
  decks: DeckScorecard[];
  run: {
    games: number; decided: number; censored: number;
    baseline: number | null;
    medianGameRound: number | null;
    hasBehaviour: boolean;
  };
}

export interface SimResult {
  meta: { decks?: string[]; format?: string; [k: string]: unknown };
  games: SimGame[];
  summary: SimSummary;
  /** Attached by the API at read time, not stored in the file. */
  validity?: Validity;
}

/** GET /results/{file}/summary — a run without its event logs. */
export interface RunGameSummary {
  n: number;
  players: string[];
  result: SimGame["result"];
  turns: number;
  ended_turn: number | null;
  /** Table rounds (a player's Nth turn is round N). ended_turn is Forge's
   *  per-player counter and reads ~4x high to a Magic player. Optional: a
   *  summary served before this field existed does not carry it. */
  ended_round?: number | null;
  events: number;
}

export interface RunSummary {
  meta: SimResult["meta"];
  summary: SimSummary;
  games: RunGameSummary[];
  file: string;
  validity?: Validity;
}

/** GET /results/{file}/game/{n} — one game's full event log. */
export interface RunGame {
  meta: SimResult["meta"];
  file: string;
  n: number;
  games_total: number;
  game: SimGame;
}

/** GET /sim-status .progress — how far along, and whether it is still moving.
 *
 *  A four-deck gauntlet is tens of minutes of a silent JVM, so an elapsed
 *  timer alone cannot distinguish "working" from "died". Every field here
 *  exists to answer that. */
export interface JobProgress {
  /** Games that will actually be played: rounded up to whole seat rotations,
   *  so it is usually MORE than the number requested. */
  expected_games: number;
  rotations: number;
  /** [low, high] seconds a run this size typically takes. */
  typical_seconds: [number, number];
  /** The hang ceiling. Many times any real run; not an estimate. */
  ceiling_seconds: number;
  /** Finished games across every rotation. Running jobs only. */
  games_done?: number;
  elapsed?: number;
  seconds_per_game?: number;
  eta_seconds?: number;
  /** Since the run last wrote anything. The real liveness signal. */
  seconds_since_activity?: number;
  /** Nothing written for far longer than one game's clock. */
  stalled?: boolean;
  /** Slower than typical, which on its own is not a problem. */
  over_typical?: boolean;
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
  progress?: JobProgress;
  /** The run was cut short but its finished games were kept. */
  incomplete?: boolean;
  warning?: string;
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

/** One known combo, from Commander Spellbook via the engine's cache. */
export interface KnownCombo {
  id: string;
  cards: string[];
  produces: string[];
  description: string;
  mana_needed: string;
  prerequisites: string;
}

/** GET /analysis/{file} — how games ended and how each deck's combos fared. */
export interface ComboGame {
  n: number;
  pieces: Record<string, number | null>;
  assembled_turn: number | null;
  online_turns: number;
  won: boolean;
  cards_seen?: number;
  p_all_drawn?: number;
}

export interface AnalysedCombo extends KnownCombo {
  games: ComboGame[];
  games_played: number;
  assembled_games: number;
  converted_games: number;
  median_assembled_turn: number | null;
  idle_online_turns: number;
  /** Sum of per-game P(all library pieces drawn by game end) — what raw draws
   *  alone predicted. Actual above it means tutors did work. */
  expected_drawn_games?: number;
  /** Instant/sorcery pieces: counted as present on turns they were cast,
   *  since they never sit on the battlefield. */
  nonpermanent_pieces?: string[];
  /** Server-computed verdict. "sample_too_small" means draw odds predicted
   *  ~0 assemblies across the run, so a zero is expected, not a finding. */
  reading?: "fired" | "assembled_not_fired" | "sample_too_small" | "not_assembled";
}

export interface AnalysisDeck {
  deck_file: string;
  combo_status: "ok" | "unknown";
  combos: AnalysedCombo[];
  almost_included: number;
  deck_size?: number;
  commanders?: string[];
  draws?: { games: number; avg_cards_seen: number; per_own_turn: number | null };
}

export interface AnalysisGame {
  n: number;
  winner: string | null;
  ended_turn: number;
  method: string;
  detail: string;
}

export interface AnalysisReport {
  version?: number;
  file: string | null;
  games: AnalysisGame[];
  decks: Record<string, AnalysisDeck>;
  summary: { games: number; methods: Record<string, number> };
  /** analyse() has returned this since ANALYSIS_VERSION 4; the type omitted
   *  it, so a polluted run's combo table rendered with no caveat at all. */
  validity?: Validity;
  note: string;
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

export interface OneAway {
  missing: string;
  unlocks: number;
  example: string[];
  produces: string[];
}

export interface DeckCombos {
  status: "ok" | "unknown";
  included?: KnownCombo[];
  almost_included?: number;
  one_away?: OneAway[];
}

export interface ImportResponse {
  ok: boolean;
  error?: string;
  file?: string;
  saved?: boolean;
  report?: ImportReport;
  cards_cached?: number;
  combos?: DeckCombos;
}

/** GET /results/{file}/telemetry?deck= — deck_telemetry.compute() output.
 *  Statuses come from documented thresholds in engine/deck_telemetry.py;
 *  never recompute them client-side. */
export interface TelemetryWatched {
  name: string;
  events: number;
  events_per_game: number;
  status: "healthy" | "partial" | "cold";
}

export interface TelemetryReport {
  games: number; // games actually present in the payload, not summary.games
  deck: string;
  player_key: string | null;
  source: string | null; // "rotated" when seat-rotated
  commander: {
    name: string;
    cast_rate: number; // 0..1, share of games with >=1 cast
    median_turn: number | null;
    casts_per_game: number;
    status: "healthy" | "partial" | "cold";
  } | null;
  engine: {
    charge_events: number;
    charge_events_per_game: number;
    charge_status: "healthy" | "partial" | "cold";
    proliferate_events: number;
    proliferate_per_game: number;
    proliferate_status: "healthy" | "partial" | "cold";
  };
  watched: TelemetryWatched[];
  deaths: {
    by_source: { source: string; damage: number }[];
    median_turn: number | null;
  };
  wins: number;
  win_rate: number;
  method: string;
  file: string;
  decks: string[];
}

export interface RuleHit {
  rule?: string;
  score?: number;
  text?: string;
  [k: string]: unknown;
}

/** GET/POST /coaching — coach.report(). Verdict numbers are enforced facts
 *  from the run and archetype tables, never model output. */
export interface CoachingReport {
  ok: boolean;
  reason?: string;
  cached?: boolean;
  deck?: string;
  games?: number;
  verdict?: {
    headline: string;
    prose: string;
    win_rate: number;
    baseline: number | null;
    sim_is_floor: boolean;
  };
  support_chain?: {
    link: string;
    status: "running" | "partial" | "cold";
    measured: string;
    reading: string;
  }[];
  matchups?: { pod: string; win_rate: number; note: string }[];
  changes?: {
    action: "add" | "cut";
    card: string;
    reason: string;
    evidence: string;
  }[];
  play_guide?: string[];
  archetype?: { class: string; baseline: number | null; sim_is_floor: boolean; why: string };
  meta?: { model: string; deck_hash: string; gauntlet_id: string; generated: string };
}

/** GET /rule/{n} — exact rule plus its direct subrules. */
export interface RuleLookup {
  rule?: string;
  entries?: { rule: string; text: string }[];
  error?: string;
  suggestion?: string;
}

/** GET/POST /ask — rules_qa.answer(). ok:false carries `reason` and still
 *  populates `hits`, so the UI can degrade to plain rules search. */
export interface RulesAnswer {
  ok: boolean;
  reason?: string;
  question?: string;
  normalized?: string;
  key?: string;
  answer?: string;
  citations?: { rule: string; text: string }[];
  hits: RuleHit[];
  covered?: boolean;
  cached?: boolean;
  ungrounded?: string[];
  meta?: { model: string; generated: string; kb: string };
}
