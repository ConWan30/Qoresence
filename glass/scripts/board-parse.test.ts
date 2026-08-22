import assert from "node:assert/strict";
import test from "node:test";
import { boardLine, parseDeckMessage, pickBoard, situationLine } from "../src/lib/coupling/board.ts";

test("WS situation payload carries Madden board", () => {
  const ing = parseDeckMessage({
    type: "situation",
    payload: {
      game_state: "gameplay",
      game_category: "football",
      home_score: 21,
      away_score: 14,
      quarter: 3,
      down: 2,
      yards_to_go: 6,
      game_clock_seconds: 192,
      score_vlm_locked: true,
    },
  });
  assert.ok(ing);
  assert.equal(ing.homeScore, 21);
  assert.equal(ing.awayScore, 14);
  assert.equal(ing.quarter, 3);
  assert.equal(ing.down, 2);
  assert.equal(ing.clock, "3:12");
  assert.equal(ing.boardLocked, true);
  assert.equal(boardLine(ing), "21-14 · Q3 3:12 · 2nd & 6");
});

test("snapshot.situation + score_home aliases", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    situation: { score_home: 7, score_away: 0, game_state: "gameplay", score_vlm_locked: true },
  });
  assert.ok(ing);
  assert.equal(ing.homeScore, 7);
  assert.equal(ing.awayScore, 0);
  assert.equal(ing.boardLocked, true);
});

test("confirm last_confirm fills board when situation scores are null", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    situation: { game_state: "gameplay", home_score: null, away_score: null },
    confirm: {
      last_confirm: { home_score: 28, away_score: 17, quarter: 4 },
    },
  });
  assert.ok(ing);
  assert.equal(ing.homeScore, 28);
  assert.equal(ing.awayScore, 17);
  assert.equal(ing.quarter, 4);
  assert.equal(ing.boardLocked, true);
});

test("pickBoard reads visual_context", () => {
  const b = pickBoard({
    visual_context: { home_score: 3, away_score: 10, clock: "0:24", score_vlm_locked: true },
  });
  assert.equal(b.home, 3);
  assert.equal(b.away, 10);
  assert.equal(b.clock, "0:24");
  assert.equal(b.locked, true);
});

test("Gemini last_confirm beats unlocked OCR 20-20", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    situation: {
      game_state: "gameplay",
      home_score: 20,
      away_score: 20,
      score_vlm_locked: false,
    },
    confirm: { last_confirm: { home_score: 20, away_score: 0, quarter: 2 } },
  });
  assert.ok(ing);
  assert.equal(ing.homeScore, 20);
  assert.equal(ing.awayScore, 0);
  assert.equal(ing.boardLocked, true);
});

test("score_vlm_locked situation is an honest board", () => {
  const ing = parseDeckMessage({
    type: "situation",
    payload: {
      game_state: "gameplay",
      home_score: 14,
      away_score: 7,
      score_vlm_locked: true,
      quarter: 3,
      down: 1,
      yards_to_go: 10,
      game_clock_seconds: 90,
    },
  });
  assert.ok(ing);
  assert.equal(ing.boardLocked, true);
  assert.equal(ing.homeScore, 14);
  assert.equal(ing.awayScore, 7);
  assert.equal(boardLine(ing), "14-7 · Q3 1:30 · 1st & 10");
});

test("seq-skew ghosts digits so scorebug N cannot sit on frame N+k", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    situation: {
      game_state: "gameplay",
      home_score: 21,
      away_score: 14,
      score_vlm_locked: true,
      frame_seq: 7,
    },
    video: { has_frame: true, live_seq: 10, widget_seq: 7, same_seq: false, paint: false, plane_dim: false },
  });
  assert.ok(ing);
  assert.equal(ing.paint, false);
  assert.equal(ing.sameSeq, false);
  assert.equal(ing.homeScore, null);
  assert.equal(ing.awayScore, null);
});

test("plane dim on menu sleeps the board", () => {
  const ing = parseDeckMessage({
    type: "situation",
    payload: {
      game_state: "menu",
      home_score: 14,
      away_score: 7,
      score_vlm_locked: true,
    },
    video: { has_frame: true, paint: false, plane_dim: true, live_seq: 3, same_seq: true },
  });
  assert.ok(ing);
  assert.equal(ing.planeDim, true);
  assert.equal(ing.homeScore, null);
});

test("unlocked OCR pair is not a VLM lock", () => {
  const ing = parseDeckMessage({
    situation: { game_state: "gameplay", home_score: 21, away_score: 14 },
  });
  assert.ok(ing);
  assert.equal(ing.homeScore, 21);
  assert.equal(ing.awayScore, 14);
  assert.equal(ing.boardLocked, false);
});

test("situation strip matches original Deck scorebug line", () => {
  const ing = parseDeckMessage({
    type: "situation",
    payload: {
      game_state: "gameplay",
      game_title: "Madden NFL 27",
      home_team: "KC",
      away_team: "PHI",
      home_score: 14,
      away_score: 7,
      quarter: 3,
      down: 2,
      yards_to_go: 6,
      field_position: "PHI34",
      game_clock_seconds: 192,
      score_vlm_locked: true,
      win_prob: 0.58,
    },
  });
  assert.ok(ing);
  assert.equal(ing.gameTitle, "Madden NFL 27");
  assert.equal(ing.homeTeam, "KC");
  assert.equal(
    situationLine(ing),
    "KC 14 - PHI 7 · Q3 3:12 · 2nd & 6 @ PHI34 · WP 58%",
  );
});
