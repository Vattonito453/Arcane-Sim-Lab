// The replay log never shows Forge's raw bookkeeping strings or instance ids
// (repair plan WS11 task 7), and a reworded line keeps its step, so "event N
// of M", ?t= links and a flag's event index still point at the same event.
//
// Run from web/ after `npm install`:  node --test scripts/replay_log.test.mjs
// No build and no extra dependency: lib/replay.ts is transpiled in memory
// with the `typescript` devDependency, as scripts/replay_phase.test.mjs does.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, "..");
const ts = createRequire(import.meta.url)("typescript");

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
const K = "Ai(1)-Kess, Reanimator";
const S = "Ai(2)-Skrat's Revenge";
const ev = (seq, action, raw) => ({ seq, action, raw });

// Two turns each (so the table turn is 2), a game-end block the way Forge
// prints it, two Slug Tokens that need telling apart, and one Island that
// does not.
const game = {
  players: [K, S],
  events_pregame: [],
  turns: [
    { turn: 1, active_player: K, events: [ev(1, "phase", `${K}'s Untap step`)] },
    { turn: 2, active_player: S, events: [ev(2, "phase", `${S}'s Untap step`)] },
    { turn: 3, active_player: K, events: [ev(3, "phase", `${K}'s Untap step`)] },
    {
      turn: 4, active_player: S, events: [
        ev(4, "phase", `${S}'s Combat damage step`),
        ev(5, "damage", `Slug Token (1300) deals 1 combat damage to ${K}.`),
        ev(6, "damage", `Slug Token (1306) deals 1 combat damage to ${K}.`),
        ev(7, "zone_change", "Island (59) was put into Graveyard from Battlefield."),
        ev(8, "zone_change", "Send countered spell to Graveyard"),
        ev(9, "life_change", `Life: ${K} 2 > 0`),
        ev(10, "player_control", `${K} has restored control over themself`),
        ev(11, "game_outcome", "Turn 18"),
        ev(12, "game_outcome", `${K} has lost because of obtaining 10 poison counters`),
        ev(13, "game_outcome", `${K} has lost due to accumulation of 21 damage from generals`),
        ev(14, "game_outcome", `${S} has won because all opponents have lost`),
        ev(15, "match_result", `${K}: 0 ${S}: 1`),
      ],
    },
  ],
};

const timeline = replay.buildTimeline(game);
const text = (seq) => timeline.steps.find((s) => s.seq === seq).text;

test("every event keeps its own step (indices, ?t= links and flags hold)", () => {
  assert.equal(timeline.steps.length, 15);
  assert.deepEqual(timeline.steps.map((s) => s.seq), Array.from({ length: 15 }, (_, i) => i + 1));
});

test("Forge's bookkeeping lines are reworded", () => {
  assert.equal(text(9), "Kess, Reanimator goes from 2 to 0 life.");
  assert.equal(text(10), "Kess, Reanimator controls their own choices again.");
  // "Turn 18" is Forge's own figure; the table turn is 2 (each seat took two).
  assert.equal(text(11), "The game ended on turn 2.");
  assert.equal(text(12), "Kess, Reanimator has lost to 10 poison counters.");
  assert.equal(text(13), "Kess, Reanimator has lost to 21 commander damage.");
  assert.equal(text(14), "Skrat's Revenge has won because all opponents have lost");
  assert.equal(text(15), "Forge's match tally: Kess, Reanimator 0; Skrat's Revenge 1.");
  assert.equal(text(8), "The countered spell goes to its owner's graveyard.");
});

test("namesakes are numbered, never shown by Forge's instance id", () => {
  assert.equal(text(5), "Slug Token #1 deals 1 combat damage to Kess, Reanimator.");
  assert.equal(text(6), "Slug Token #2 deals 1 combat damage to Kess, Reanimator.");
  assert.equal(text(7), "Island was put into Graveyard from Battlefield.");
  for (const s of timeline.steps) {
    assert.doesNotMatch(s.text, /\(\d{3,}\)|Ai\(\d\)|restored control|^Turn \d+$/, s.text);
  }
});

test("the ops still read the raw line (the fold is unchanged)", () => {
  const life = timeline.steps.find((s) => s.seq === 9);
  assert.deepEqual(life.op, { t: "life", p: K, to: 0 });
  const out = timeline.steps.find((s) => s.seq === 12);
  assert.deepEqual(out.op, { t: "out", p: K });
});
