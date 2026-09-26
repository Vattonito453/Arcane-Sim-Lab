// Phase lines are read against the game's own player keys (web/lib/replay.ts).
//
// "Skrat's Revenge's Main phase, precombat" used to parse as player "Skrat" in
// phase "Revenge's main phase, precombat": the replay header showed that, the
// attack lanes vanished at declare blockers (the label failed the combat
// test), and the shim zone read jumped to end-of-turn state (the label matched
// no phase, so every record of the turn applied). This runs the real
// lib/replay.ts against the synthetic fixture that engine/tests/
// test_possessive_phase.py builds and checks, so the Python and TypeScript
// statements of the rule share one set of cases.
//
// Run from web/ after `npm install`:  node --test scripts/replay_phase.test.mjs
// No build and no extra dependency: the lib files are transpiled in memory
// with the `typescript` devDependency the app already has.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, "..");
const fixtures = join(web, "..", "engine", "tests", "fixtures");
const ts = createRequire(import.meta.url)("typescript");

/** A web/lib module as the app sees it, transpiled to CommonJS in memory.
 *  Only relative "./x" imports are followed; "./types" is type-only and is
 *  erased by the transpile. */
function load(name, cache = new Map()) {
  if (cache.has(name)) return cache.get(name);
  const src = readFileSync(join(web, "lib", `${name}.ts`), "utf8");
  const { outputText } = ts.transpileModule(src, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  });
  const mod = { exports: {} };
  cache.set(name, mod.exports);
  const req = (spec) => {
    if (!spec.startsWith("./")) throw new Error(`lib/${name}.ts imports ${spec}; only ./ is supported`);
    return load(spec.slice(2), cache);
  };
  new Function("exports", "require", "module", outputText)(mod.exports, req, mod);
  return mod.exports;
}

const replay = load("replay");
const json = (f) => JSON.parse(readFileSync(join(fixtures, f), "utf8"));
const spec = json("possessive_names_cases.json");
const result = json("possessive_names.json");
const game = result.games[0];
const [SKRAT, YURIKO, ATRAXA] = spec.players;

// Forge's labels as the replay shows them (prettyPhase: first letter capital).
const LABELS = [
  "Untap step", "Upkeep step", "Draw step", "Main phase, precombat",
  "Beginning of combat step", "Declare attackers step", "Declare blockers step",
  "First strike damage step", "Combat damage step", "End of combat step",
  "Main phase, postcombat", "End step", "Cleanup step",
];

const timeline = replay.buildTimeline(game);
/** Index of the phase step `label` in turn `turn`. */
const at = (turn, label) => {
  const i = timeline.steps.findIndex((s) => s.turn === turn && s.kind === "phase" && s.phase === label);
  assert.ok(i >= 0, `no ${label} step in turn ${turn}`);
  return i;
};
const names = (cards) => (cards ?? []).map((c) => c.name).sort();

test("shared phase-line cases (engine/tests/fixtures/possessive_names_cases.json)", () => {
  for (const c of spec.cases) {
    const known = replay.phasePossessives(c.players ?? spec.players);
    assert.deepEqual(replay.parsePhase(c.raw, known), { p: c.p, label: c.label }, c.why);
  }
});

test("every phase step carries a clean Forge label", () => {
  const phases = timeline.steps.filter((s) => s.kind === "phase");
  assert.equal(phases.length, 13 * game.turns.length);
  for (const t of game.turns) {
    const labels = phases.filter((s) => s.turn === t.turn).map((s) => s.phase);
    assert.deepEqual(labels, LABELS, `turn ${t.turn} (${t.active_player})`);
  }
  // What the replay header renders: "Round 2 · main phase, precombat".
  const s = timeline.steps[at(5, "Main phase, precombat")];
  assert.equal(s.round, 2);
  assert.equal(s.active, SKRAT);
});

test("attack lanes survive declare blockers and clear at end of combat", () => {
  const lanes = [
    { from: SKRAT, to: ATRAXA, cards: ["Goblin Instigator"] },
    { from: SKRAT, to: YURIKO, cards: ["Goblin Token"] },
  ];
  assert.deepEqual(replay.foldTo(timeline, at(5, "Declare attackers step") + 2).attacks, lanes);
  const blockers = replay.foldTo(timeline, at(5, "First strike damage step") - 1);
  assert.deepEqual(blockers.attacks, lanes);
  assert.deepEqual(blockers.blocks, [
    { by: ATRAXA, attacker: "Goblin Instigator", blockers: ["Thraben Inspector"] },
    { by: YURIKO, attacker: "Goblin Token", blockers: ["Ninja of the Deep Hours"] },
  ]);
  assert.deepEqual(replay.foldTo(timeline, at(5, "Combat damage step")).attacks, lanes);
  assert.deepEqual(replay.foldTo(timeline, at(5, "End of combat step")).attacks, []);
});

test("the zone read stays in its phase: second-main tokens are absent at declare attackers", () => {
  const read = (i) => names(replay.foldTo(timeline, i, game.zones).battlefield.get(SKRAT));
  assert.deepEqual(read(at(5, "Declare attackers step")), ["Goblin Instigator", "Goblin Token", "Mountain"]);
  assert.deepEqual(read(at(5, "Main phase, postcombat")), ["Goblin Token", "Goblin Token", "Mountain"]);
  assert.deepEqual(
    names(replay.battlefieldAt(game.zones, 5, "Declare attackers step", game.players).get(SKRAT)),
    ["Goblin Instigator", "Goblin Token", "Mountain"],
  );
});

test("isCombatPhase takes the label without its possessive", () => {
  for (const l of LABELS.slice(4, 9)) assert.equal(replay.isCombatPhase(l), true, l);
  for (const l of [...LABELS.slice(0, 4), ...LABELS.slice(9)]) assert.equal(replay.isCombatPhase(l), false, l);
  assert.equal(replay.isCombatPhase("Revenge's declare blockers step"), false);
});
