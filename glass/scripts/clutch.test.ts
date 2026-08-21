import assert from "node:assert/strict";
import test from "node:test";
import { clutchAdvanced, parseFeedMoment, scoreClutch, QUIET_CLUTCH } from "../src/lib/coupling/clutch.ts";
import { parseDeckMessage } from "../src/lib/coupling/board.ts";

const base = {
  coupling: 0,
  climax: 0,
  phase: "",
  clipWorth: 0,
  winProb: null as number | null,
  phrase: "HUDDLE" as const,
  ticketLive: false,
  quarter: null as number | null,
  down: null as number | null,
  distance: null as number | null,
  clock: "",
  boardLocked: false,
  homeScore: null as number | null,
  awayScore: null as number | null,
  scorePlay: false,
};

test("quiet when nothing is happening", () => {
  const c = scoreClutch(base);
  assert.equal(c.kind, "quiet");
});

test("Q4 two-minute close board is a clutch window", () => {
  const c = scoreClutch({
    ...base,
    boardLocked: true,
    homeScore: 21,
    awayScore: 17,
    quarter: 4,
    clock: "1:08",
    down: 4,
    distance: 2,
  });
  assert.ok(c.score >= 0.45, String(c.score));
  assert.ok(c.kind === "window" || c.kind === "climax" || c.kind === "score_play");
  assert.match(c.why, /4th/);
});

test("DriveGraph climax_score on coupling is harvested", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    situation: { game_state: "gameplay", score_vlm_locked: true, home_score: 14, away_score: 14, quarter: 4 },
    coupling: { climax_score: 0.81, coupling: 0.4, phrase: "SPRINT" },
    timeline: { drive_graph: { phase: "armed", climax: { score: 0.7 } } },
  });
  assert.ok(ing);
  assert.ok(ing.climax >= 0.81);
  assert.equal(ing.drivePhase, "armed");
  const c = scoreClutch({
    ...base,
    coupling: ing.coupling,
    climax: ing.climax,
    phase: ing.drivePhase,
    phrase: ing.phrase,
    boardLocked: ing.boardLocked,
    homeScore: ing.homeScore,
    awayScore: ing.awayScore,
    quarter: ing.quarter,
    clock: ing.clock,
    down: ing.down,
    distance: ing.distance,
  });
  assert.ok(c.kind === "climax" || c.kind === "score_play" || c.kind === "window");
});

test("clutchAdvanced fires on kind upgrade", () => {
  const next = scoreClutch({ ...base, climax: 0.7, phrase: "CUT" });
  assert.equal(clutchAdvanced(QUIET_CLUTCH, next), true);
  assert.equal(clutchAdvanced(next, next), false);
});

test("WS moment becomes a fast clutch-feed chip", () => {
  const m = parseFeedMoment({
    type: "moment",
    payload: { title: "Red-zone energy spike — something's cooking.", path: "fast", clock: "00:42", reason: "coupling" },
  });
  assert.ok(m);
  assert.equal(m.path, "fast");
  assert.match(m.title, /Red-zone/);
});
