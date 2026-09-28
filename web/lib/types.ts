/** Shapes match engine/mtg_engine.py responses exactly — see frontend_handoff/API_SPEC.md */

export interface DeckEntry {
  file: string;
  name: string;
  /** From the .dck [Commander] section; null when the deck has none. The
   *  picker resolves art + color identity through /cards, batched. */
  commander?: string | null;
  /** Every [Commander] entry (partners, backgrounds), a joined DFC name shown
   *  as the face Forge logs. Optional: an older engine sends `commander` only. */
  commanders?: string[];
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
  /** Who piloted the run, in words (engine validity.pilot). Optional: an
   *  engine older than R1 does not send it. */
  pilot?: Pilot;
  /** Each deck's commanders by deck name (engine/commanders.py). */
  commanders?: Commanders;
  error?: string;
}

/** {deck name (the player key minus its Ai(n)- prefix): [commanders]},
 *  read by the engine from each deck's own [Commander] section. A deck whose
 *  file could not be found has no entry: show its name alone, never a guess. */
export type Commanders = Record<string, string[]>;

/** engine/validity.py pilot(): who piloted a run. `label` and `note` are the
 *  words to show; the rest is for logic. */
export interface Pilot {
  kind: "plan" | "stock" | "mixed" | "unknown";
  agent: string | null;
  shim: string | null;
  plan_decks: number | null;
  stock_decks: number | null;
  plan_version: number | null;
  plan_fix: string[] | null;
  /** True while any random dial remains in the pilot. */
  random: boolean;
  label: string;
  /** "Some choices are random on purpose." or null. */
  note: string | null;
}

/** One knockout (engine/game_story.py). `turn` is Forge's per-player turn
 *  counter; `round` is the table turn a player counts, and the one to show
 *  as "turn N". cause, by and card are null when MTG_KNOCKOUT_DETAIL is off
 *  on the server. `basis` says where `by` came from: the shim's zone stream
 *  (a read) or Forge's event log. */
export interface Knockout {
  player: string;
  turn: number;
  round: number;
  cause:
    | "combat_damage"
    | "noncombat_damage"
    | "life_loss"
    | "life_total"
    | "poison"
    | "commander_damage"
    | "alt_win"
    | "lose_effect"
    | "deckout"
    | "concession"
    | "unknown"
    | null;
  by: string | null;
  card: string | null;
  basis: "zones" | "log";
}

/** A seat that went out, and the event Forge dates it by: the lethal event's
 *  `seq`, or null when only Forge's turn order bounds it (then the seat is out
 *  from the end of that turn). */
export interface OutSeat {
  player: string;
  turn: number;
  round: number;
  seq: number | null;
}

/** The turn the board swung hardest toward the winner. `label` is what to
 *  call it ("Biggest swing" until the hand audit passes, then "Turning
 *  point"); `basis` "inferred" means reconstructed from the stdout log, and
 *  must be labelled so. `card` is null when combat moved it (`combat`) or
 *  nothing could be named. */
export interface TurningPoint {
  turn: number;
  round: number;
  card: string | null;
  by: string | null;
  combat: boolean;
  basis: "zones" | "inferred";
  label: string;
  seq: number | null;
  share_before: number | null;
  share_after: number | null;
}

/** The story fields every game carries in the summary and the game payload.
 *  Optional: an engine older than R1 sends none of them. */
export interface GameStory {
  knockouts?: Knockout[];
  out?: OutSeat[];
  turning_point?: TurningPoint | null;
}

/** Run-level story facts: the turning-point label in force (null when the
 *  server holds it), whether causes and killers are shown, and which board
 *  path the stories were read from. */
export interface StoryMeta {
  turning_point_label: string | null;
  knockout_detail: boolean;
  basis: "zones" | "inferred" | "mixed";
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
  /** Further lines of a multi-line Forge entry (modal spell text such as
   *  "• Destroy all artifacts."), kept on the event they belong to. Combat
   *  declarations are the exception: Forge joins one line per defender into a
   *  single entry, and the adapter emits each of those as its own event. */
  more?: string[];
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
  /** Shim >= 0.3.0: Forge's core types as of the move ("Creature,Artifact"),
   *  net P/T ("5/5") and whether the object is a token. What lets the table
   *  type a token copy without Scryfall. */
  types?: string;
  pt?: string;
  token?: boolean;
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
    /** censored split by cause: too slow (clock) vs could not close (turn
     *  cap). A game tripping both is attributed to the clock, so these two
     *  sum to censored and never above it. */
    timedOut?: number; turnCapped?: number;
    baseline: number | null;
    medianGameRound: number | null;
    hasBehaviour: boolean;
  };
}

/** Display names parallel to meta.decks, sent by the summary endpoint.
 *  Optional: an engine older than this still answers without it. */
export type DeckLabels = string[];

/** One deck's corrected win rate. Every figure is a percentage 0-100, not a
 *  fraction, which is what the engine sends. */
export interface PredictionDeck {
  deck: string;
  sim_win_rate: number;
  expected_win_rate: number;
  low: number;
  high: number;
  typical_error_pp: number;
  survival_pct: number | null;
  contributions: Record<string, number>;
  basis: {
    trained_on_decks: number;
    human_games: number;
    arm: string;
    loo_spearman: number;
  };
  available: boolean;
  /** Plain-language sentences the engine already writes. Render these rather
   *  than re-deriving the explanation in TSX, so the page and any coaching
   *  text can never disagree about what the model said. */
  explanation: string[];
  reason?: string;
}

/** The endpoint answers {available:false, reason} when no fitted model is in
 *  the image, which is exactly how it failed silently in production for
 *  weeks. Callers MUST branch on available before touching decks. */
export interface PredictionReport {
  file: string;
  available: boolean;
  reason?: string;
  decks?: PredictionDeck[];
  model?: Record<string, unknown>;
  /** Pilot honesty (repair plan WS11 task 11). Present on every answer from
   *  a fitted model; absent from an engine older than R1, so each is optional
   *  and the panel renders as before without them. */
  /** model is predict.model_fingerprint: a rank check applies only to the
   *  fitted model it measured, so a refit starts with no check. */
  model_arm?: { text: string | null; pilot: string; model?: string };
  pilot?: PredictionPilot;
  pilot_match?: boolean;
  /** One sentence, written by the engine: "Fit on stock Forge games; this
   *  run used Sim Lab's pilot." Render it beside the figures, verbatim. */
  label?: string;
  rank_check?: {
    status: "model_arm" | "none" | "pass" | "fail" | "unreadable";
    text: string;
  };
  /** True when the latest rank check for this run's pilot failed (or the
   *  record is missing): the engine then sends no figures at all. */
  suppressed?: boolean;
  suppressed_by?: "rank_check" | "rank_record_missing" | null;
  suppressed_reason?: string | null;
}

/** engine/pilot.py run_pilot(): which pilot played the run. */
export interface PredictionPilot {
  id: string;
  kind: "stock" | "plan" | "mixed" | "unknown";
  shim: string | null;
  plan_version: number | null;
  text: string;
}

export interface SimResult {
  meta: { decks?: string[]; format?: string; [k: string]: unknown };
  games: SimGame[];
  summary: SimSummary;
  /** Attached by the API at read time, not stored in the file. */
  validity?: Validity;
}

/** GET /results/{file}/summary — a run without its event logs. */
export interface RunGameSummary extends GameStory {
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
  commanders?: Commanders;
  pilot?: Pilot;
  story?: StoryMeta;
}

/** GET /results/{file}/game/{n} — one game's full event log, plus its story. */
export interface RunGame extends GameStory {
  meta: SimResult["meta"];
  file: string;
  n: number;
  games_total: number;
  game: SimGame;
  commanders?: Commanders;
  pilot?: Pilot;
  story?: StoryMeta;
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
  /** Games the deck won after the pieces had been together (ANALYSIS_VERSION
   *  5+). Correlation, never "the combo won": shown unbadged. */
  won_after_assembly?: number;
  /** Deprecated alias of won_after_assembly; WS1 replaces it. */
  converted_games: number;
  median_assembled_turn: number | null;
  idle_online_turns: number;
  /** Sum of per-game P(all library pieces drawn by game end) — what raw draws
   *  alone predicted. Actual above it means tutors did work. */
  expected_drawn_games?: number;
  /** Instant/sorcery pieces: counted as present on turns they were cast,
   *  since they never sit on the battlefield. */
  nonpermanent_pieces?: string[];
  /** Server-computed description, never a verdict on the pilot. "fired" and
   *  "assembled_not_fired" were retired in ANALYSIS_VERSION 5; they can only
   *  come from a stale payload. "sample_too_small" means draw odds predicted
   *  ~0 assemblies across the run, so a zero is expected, not a finding. */
  reading?:
    | "assembled"
    | "sample_too_small"
    | "not_assembled"
    | "fired"
    | "assembled_not_fired";
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
  /** Which board path the assembly numbers came from (ANALYSIS_VERSION 5+):
   *  a read of the shim's zone records, stdout inference, or both. */
  basis?: "zone_stream" | "inferred" | "mixed";
  /** The honesty note, worded by the engine for that path. */
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
