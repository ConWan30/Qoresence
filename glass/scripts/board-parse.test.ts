import assert from "node:assert/strict";
import test from "node:test";
import {
  boardLine,
  digitsLicensed,
  parseDeckMessage,
  pickBoard,
  scorebugPair,
  situationLine,
  ticketFresh,
} from "../src/lib/coupling/board.ts";

const CROP = "crop-ok";
const TICKET = "fixture-confirm";

function license(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    score_vlm_locked: true,
    confirm_ticket_id: TICKET,
    crop_hash: CROP,
    ...extra,
  };
}

function lastConfirm(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    ticket_id: TICKET,
    crop_hash: CROP,
    clock_ns: 1_000_000_000,
    ...extra,
  };
}

test("snapshot video frames and pushes land on ingest", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    schema_version: "qoresence-deck-v0",
    situation: { game_state: "gameplay" },
    video: { has_frame: true, age_s: 0.12, frames: 440, pushes: 438 },
  });
  assert.ok(ing);
  assert.equal(ing.videoAgeS, 0.12);
  assert.equal(ing.videoFrames, 440);
  assert.equal(ing.videoPushes, 438);
});

test("snapshot controller carries frame-clock DualSense pose", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    schema_version: "qoresence-deck-v0",
    situation: { game_state: "gameplay" },
    controller: {
      connected: true,
      device: "DualSense Edge",
      transport: "usb",
      reports: 3133,
      pad_r2: 0.72,
      pad_left: 0.31,
      sync_lag_ms: 52,
      lag_center_ms: 52,
      frame_seq: 100,
      buttons: ["r2"],
    },
  });
  assert.ok(ing);
  assert.equal(ing.padR2, 0.72);
  assert.equal(ing.padLeft, 0.31);
  assert.equal(ing.syncLagMs, 52);
  assert.equal(ing.padConnected, true);
  assert.equal(ing.padReports, 3133);
  assert.equal(ing.padTransport, "usb");
  assert.equal(ing.padHidSeq, 100);
});

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
      ...license(),
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

test("boolean game_title does not paint as true on the sit strip", () => {
  const ing = parseDeckMessage({
    type: "situation",
    payload: {
      game_title: true,
      home_left: true,
      home_score: 7,
      away_score: 0,
      home_team: "CHI",
      away_team: "IND",
      quarter: 1,
      down: 1,
      yards_to_go: 10,
      game_clock_seconds: 152,
      ...license(),
    },
  });
  assert.ok(ing);
  assert.equal(ing.gameTitle, "");
  assert.doesNotMatch(situationLine(ing), /\btrue\b/);
});

test("snapshot.situation + score_home aliases", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    situation: { score_home: 7, score_away: 0, game_state: "gameplay", ...license() },
  });
  assert.ok(ing);
  assert.equal(ing.homeScore, 7);
  assert.equal(ing.awayScore, 0);
  assert.equal(ing.boardLocked, true);
});

test("confirm last_confirm fills board when situation scores are null", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    situation: { game_state: "gameplay", home_score: null, away_score: null, ...license() },
    confirm: {
      last_confirm: lastConfirm({ home_score: 28, away_score: 17, quarter: 4, score_vlm_locked: true }),
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
    visual_context: { home_score: 3, away_score: 10, clock: "0:24", ...license() },
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
      confirm_ticket_id: TICKET,
      crop_hash: CROP,
    },
    confirm: { last_confirm: lastConfirm({ home_score: 20, away_score: 0, quarter: 2, score_vlm_locked: true }) },
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
      quarter: 3,
      down: 1,
      yards_to_go: 10,
      game_clock_seconds: 90,
      ...license(),
    },
  });
  assert.ok(ing);
  assert.equal(ing.boardLocked, true);
  assert.equal(ing.homeScore, 14);
  assert.equal(ing.awayScore, 7);
  assert.equal(boardLine(ing), "14-7 · Q3 1:30 · 1st & 10");
});

test("seq-skew is not ticket-fresh — blank beats hold", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    situation: {
      game_state: "gameplay",
      home_score: 21,
      away_score: 14,
      ...license(),
      frame_seq: 7,
    },
    confirm: { last_confirm: lastConfirm({ home_score: 21, away_score: 14, score_vlm_locked: true }) },
    video: { has_frame: true, live_seq: 10, widget_seq: 7, same_seq: false, paint: false, plane_dim: false },
  });
  assert.ok(ing);
  assert.equal(ing.paint, false);
  assert.equal(ing.sameSeq, false);
  assert.equal(ing.boardLocked, false);
  assert.equal(ing.homeScore, null);
  assert.equal(ing.awayScore, null);
});

test("plane dim on menu keeps locked digits; UI sleeps paint", () => {
  const ing = parseDeckMessage({
    type: "situation",
    payload: {
      game_state: "menu",
      home_score: 14,
      away_score: 7,
      ...license(),
    },
    video: { has_frame: true, paint: false, plane_dim: true, live_seq: 3, same_seq: true },
  });
  assert.ok(ing);
  assert.equal(ing.planeDim, true);
  assert.equal(ing.boardLocked, true);
  assert.equal(ing.homeScore, 14);
  assert.equal(ing.awayScore, 7);
});

test("unlocked OCR pair is not a VLM lock", () => {
  const ing = parseDeckMessage({
    situation: { game_state: "gameplay", home_score: 21, away_score: 14 },
  });
  assert.ok(ing);
  assert.equal(ing.homeScore, null);
  assert.equal(ing.awayScore, null);
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
      ...license(),
      win_prob: 0.58,
    },
  });
  assert.ok(ing);
  assert.equal(ing.gameTitle, "Madden NFL 27");
  assert.equal(ing.homeTeam, "KC");
  assert.equal(ing.awayTeam, "PHI");
  assert.equal(ing.homeLeft, false);
  // Madden scorebug is AWAY left, HOME right — paint HDMI order, not home-first.
  assert.equal(
    situationLine(ing),
    "PHI 7 - KC 14 · Q3 3:12 · 2nd & 6 @ PHI34 · WP 58%",
  );
});

test("home_left true keeps home on the left of the scorebug", () => {
  const ing = parseDeckMessage({
    type: "situation",
    payload: {
      game_state: "gameplay",
      home_team: "KC",
      away_team: "PHI",
      home_score: 14,
      away_score: 7,
      home_left: true,
      ...license(),
    },
  });
  assert.ok(ing);
  assert.equal(ing.homeLeft, true);
  assert.equal(situationLine(ing), "KC 14 - PHI 7");
  assert.equal(
    scorebugPair({ homeScore: 14, awayScore: 7, homeTeam: "KC", awayTeam: "PHI", homeLeft: true, dash: "–" }),
    "KC 14–7 PHI",
  );
});

test("HDMI crop left NO 21 / right DET 6 paints NO 21 DET 6 not NO 6 DET 21", () => {
  const lastConfirmLtr = lastConfirm({
    ticket_id: "fixture-no21-det6",
    home_score: 21,
    away_score: 6,
    home_left: false,
    left_team: "NO",
    right_team: "DET",
    left_score: 21,
    right_score: 6,
    score_vlm_locked: true,
  });
  const ing = parseDeckMessage({
    type: "snapshot",
    schema_version: "qoresence-deck-v0",
    situation: {
      game_state: "gameplay",
      game_title: "Madden NFL 27",
      home_score: 21,
      away_score: 6,
      home_left: false,
      home_team: "DET",
      away_team: "NO",
      left_team: "NO",
      right_team: "DET",
      left_score: 21,
      right_score: 6,
      ...license({ confirm_ticket_id: "fixture-no21-det6" }),
    },
    confirm: { last_confirm: lastConfirmLtr },
  });
  assert.ok(ing);
  assert.equal(ing.homeScore, 21);
  assert.equal(ing.awayScore, 6);
  assert.equal(ing.homeLeft, false);
  assert.equal(ing.leftTeam, "NO");
  assert.equal(ing.rightTeam, "DET");
  assert.equal(ing.leftScore, 21);
  assert.equal(ing.rightScore, 6);
  const pair = scorebugPair(ing);
  assert.equal(pair, "NO 21 - DET 6");
  assert.doesNotMatch(pair, /NO 6/);
  assert.doesNotMatch(pair, /DET 21/);
  assert.equal(
    scorebugPair({
      homeScore: 21,
      awayScore: 6,
      homeTeam: "DET",
      awayTeam: "NO",
      homeLeft: false,
      leftTeam: "NO",
      rightTeam: "DET",
      leftScore: 21,
      rightScore: 6,
      dash: "–",
    }),
    "NO 21–6 DET",
  );
  assert.equal(situationLine(ing), "NO 21 - DET 6");
});

test("situation identity beats swapped visual_context", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    situation: {
      game_state: "gameplay",
      home_team: "KC",
      away_team: "PHI",
      home_score: 14,
      away_score: 7,
      home_left: false,
      ...license(),
    },
    visual_context: {
      home_team: "PHI",
      away_team: "KC",
      home_score: 14,
      away_score: 7,
      home_left: true,
    },
  });
  assert.ok(ing);
  assert.equal(ing.homeTeam, "KC");
  assert.equal(ing.awayTeam, "PHI");
  assert.equal(ing.homeLeft, false);
  assert.equal(situationLine(ing), "PHI 7 - KC 14");
});

test("ghost stick paints on same-seq LIVE and vanishes on seq skew", () => {
  const live = parseDeckMessage({
    type: "snapshot",
    situation: { game_state: "gameplay", frame_seq: 10 },
    video: { has_frame: true, live_seq: 10, widget_seq: 10, same_seq: true, paint: true, plane_dim: false },
    ghost_stick: { enabled: true, paint: true, lx: 0.4, ly: -0.2, r2: 0.8, l2: 0, lag_ms: 48, frame_seq: 10, reason: "ok" },
  });
  assert.ok(live);
  assert.equal(live.ghostStick.paint, true);
  assert.equal(live.ghostStick.lx, 0.4);
  const skew = parseDeckMessage({
    type: "snapshot",
    situation: { game_state: "gameplay", frame_seq: 7 },
    video: { has_frame: true, live_seq: 10, widget_seq: 7, same_seq: false, paint: false, plane_dim: false },
    ghost_stick: { enabled: true, paint: true, lx: 0.4, ly: 0, r2: 0.8, l2: 0, lag_ms: 48, frame_seq: 10, reason: "ok" },
  });
  assert.ok(skew);
  assert.equal(skew.ghostStick.paint, false);
});


test("video-less situation does not demote board after snapshot optics", () => {
  const snap = parseDeckMessage({
    type: "snapshot",
    situation: {
      game_state: "gameplay",
      home_score: 28,
      away_score: 21,
      quarter: 3,
      ...license(),
      frame_seq: 40,
    },
    video: {
      has_frame: true,
      live_seq: 40,
      hub_seq: 40,
      same_seq: true,
      paint: true,
      plane_dim: false,
    },
  });
  assert.ok(snap);
  assert.equal(snap.videoOptics, true);
  assert.equal(snap.paint, true);
  assert.equal(snap.homeScore, 28);

  const sit = parseDeckMessage({
    type: "situation",
    payload: {
      game_state: "gameplay",
      home_score: 28,
      away_score: 21,
      quarter: 3,
      down: 2,
      yards_to_go: 7,
      ...license(),
      latency_ms: 12,
      updated_ns: 123,
    },
  });
  assert.ok(sit);
  assert.equal(sit.videoOptics, false);
  assert.equal(sit.paint, true);
  assert.equal(sit.sameSeq, true);
  assert.equal(sit.planeDim, false);
  assert.equal(sit.homeScore, 28);
  assert.equal(sit.awayScore, 21);
  assert.ok(boardLine(sit).includes("28-21"));
});

test("snapshot with plane_dim keeps locked digits; paint stays gated", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    situation: {
      game_state: "gameplay",
      home_score: 10,
      away_score: 3,
      ...license(),
      frame_seq: 9,
    },
    video: {
      has_frame: true,
      live_seq: 9,
      same_seq: true,
      paint: false,
      plane_dim: true,
    },
  });
  assert.ok(ing);
  assert.equal(ing.videoOptics, true);
  assert.equal(ing.planeDim, true);
  assert.equal(ing.paint, false);
  assert.equal(ing.boardLocked, true);
  assert.equal(ing.homeScore, 10);
  assert.equal(ing.awayScore, 3);
});

test("seq-skew ghosts unlocked OCR digits", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    situation: {
      game_state: "gameplay",
      home_score: 21,
      away_score: 14,
      frame_seq: 7,
    },
    video: { has_frame: true, live_seq: 10, widget_seq: 7, same_seq: false, paint: false, plane_dim: false },
  });
  assert.ok(ing);
  assert.equal(ing.boardLocked, false);
  assert.equal(ing.homeScore, null);
  assert.equal(ing.awayScore, null);
});

test("observation hid_source picture lands on ingest", () => {
  const ing = parseDeckMessage({
    type: "snapshot",
    schema_version: "qoresence-deck-v0",
    situation: { game_state: "gameplay" },
    video: { has_frame: true, age_s: 0.04, frames: 10, pushes: 10 },
    observation: {
      frame_seq: 42,
      clock_ns: 1,
      hid_button: "Cross",
      verb: "Snap Ball",
      hid_source: "picture",
    },
  });
  assert.ok(ing);
  assert.equal(ing.observation.hidButton, "Cross");
  assert.equal(ing.observation.verb, "Snap Ball");
  assert.equal(ing.observation.hidSource, "picture");
});

test("unlocked OCR silence — widgetsOk / scoreboard_locked are not digit permission", () => {
  const unlocked = pickBoard({
    game_state: "gameplay",
    home_score: 21,
    away_score: 14,
    scoreboard_locked: true,
    board_locked: true,
  });
  assert.equal(unlocked.home, null);
  assert.equal(unlocked.away, null);
  assert.equal(unlocked.locked, false);

  const widgets = parseDeckMessage({
    type: "snapshot",
    situation: { game_state: "gameplay", home_score: 21, away_score: 14, scoreboard_locked: true },
    video: { has_frame: true, live_seq: 10, same_seq: true, paint: true, plane_dim: false },
  });
  assert.ok(widgets);
  assert.equal(widgets.paint, true);
  assert.equal(widgets.sameSeq, true);
  assert.equal(widgets.homeScore, null);
  assert.equal(widgets.awayScore, null);
  assert.equal(widgets.boardLocked, false);
});

test("ConfirmTicket without VLM lock silence", () => {
  const b = pickBoard({
    home_score: 14,
    away_score: 7,
    confirm_ticket_id: TICKET,
    crop_hash: CROP,
    score_vlm_locked: false,
    last_confirm: lastConfirm({ home_score: 14, away_score: 7 }),
  });
  assert.equal(b.home, null);
  assert.equal(b.away, null);
  assert.equal(b.locked, false);

  const ing = parseDeckMessage({
    type: "snapshot",
    situation: {
      game_state: "gameplay",
      home_score: 14,
      away_score: 7,
      confirm_ticket_id: TICKET,
      crop_hash: CROP,
      score_vlm_locked: false,
    },
    confirm: { last_confirm: lastConfirm({ home_score: 14, away_score: 7 }) },
    video: { has_frame: true, same_seq: true, paint: true },
  });
  assert.ok(ing);
  assert.equal(ing.homeScore, null);
  assert.equal(ing.awayScore, null);
  assert.equal(ing.boardLocked, false);
});

test("ConfirmTicket + lock paints", () => {
  assert.equal(
    digitsLicensed({
      confirmTicketId: TICKET,
      scoreVlmLocked: true,
      ticketCropHash: CROP,
      liveCropHash: CROP,
      sameSeq: true,
    }),
    true,
  );
  const b = pickBoard({
    home_score: 21,
    away_score: 17,
    ...license(),
    last_confirm: lastConfirm({ home_score: 21, away_score: 17, score_vlm_locked: true }),
  });
  assert.equal(b.home, 21);
  assert.equal(b.away, 17);
  assert.equal(b.locked, true);

  const ing = parseDeckMessage({
    type: "snapshot",
    situation: { game_state: "gameplay", home_score: 21, away_score: 17, ...license() },
    confirm: { last_confirm: lastConfirm({ home_score: 21, away_score: 17, score_vlm_locked: true }) },
    video: { has_frame: true, live_seq: 8, same_seq: true, paint: true, plane_dim: false },
  });
  assert.ok(ing);
  assert.equal(ing.homeScore, 21);
  assert.equal(ing.awayScore, 17);
  assert.equal(ing.boardLocked, true);
  assert.ok(boardLine(ing).includes("21-17"));
});

test("pickBoard liveCrop prefers FrameHub video.crop_hash over last_fast", () => {
  const b = pickBoard({
    type: "snapshot",
    situation: {
      game_state: "gameplay",
      home_score: 0,
      away_score: 1,
      score_vlm_locked: true,
      confirm_ticket_id: TICKET,
      crop_hash: "crop-was",
    },
    confirm: {
      last_confirm: lastConfirm({
        home_score: 0,
        away_score: 1,
        crop_hash: "crop-was",
        score_vlm_locked: true,
      }),
      last_fast: { crop_hash: "crop-was", kind: "fast_chat" },
    },
    video: { has_frame: true, same_seq: true, paint: true, crop_hash: "crop-now" },
  });
  assert.equal(b.home, null);
  assert.equal(b.away, null);
  assert.equal(b.locked, false);

  const ing = parseDeckMessage({
    type: "snapshot",
    schema_version: "qoresence-deck-v0",
    situation: {
      game_state: "gameplay",
      home_score: 0,
      away_score: 1,
      score_vlm_locked: true,
      confirm_ticket_id: TICKET,
      crop_hash: "crop-was",
    },
    confirm: {
      last_confirm: lastConfirm({
        home_score: 0,
        away_score: 1,
        crop_hash: "crop-was",
        score_vlm_locked: true,
      }),
      last_fast: { crop_hash: "crop-was", kind: "fast_chat" },
    },
    video: { has_frame: true, same_seq: true, paint: true, crop_hash: "crop-now" },
  });
  assert.ok(ing);
  assert.equal(ing.homeScore, null);
  assert.equal(ing.awayScore, null);
  assert.equal(ing.boardLocked, false);
  assert.equal(scorebugPair(ing), "");
});

test("pickBoard liveCrop falls back to situation when FrameHub crop is absent", () => {
  const fresh = pickBoard({
    home_score: 21,
    away_score: 17,
    ...license(),
    last_confirm: lastConfirm({ home_score: 21, away_score: 17, score_vlm_locked: true }),
  });
  assert.equal(fresh.locked, true);
  assert.equal(fresh.home, 21);
  const staleSit = pickBoard({
    home_score: 21,
    away_score: 17,
    score_vlm_locked: true,
    confirm_ticket_id: TICKET,
    crop_hash: "crop-now",
    last_confirm: lastConfirm({ home_score: 21, away_score: 17, crop_hash: "crop-was", score_vlm_locked: true }),
  });
  assert.equal(staleSit.locked, false);
  assert.equal(staleSit.home, null);
});

test("Same-Seq skew empties pickBoard even with a fresh ticket crop", () => {
  const b = pickBoard({
    home_score: 21,
    away_score: 14,
    ...license(),
    last_confirm: lastConfirm({ home_score: 21, away_score: 14, score_vlm_locked: true }),
    video: { has_frame: true, same_seq: false, paint: false, crop_hash: CROP },
  });
  assert.equal(b.locked, false);
  assert.equal(b.home, null);
  const ing = parseDeckMessage({
    type: "snapshot",
    situation: { game_state: "gameplay", home_score: 21, away_score: 14, ...license() },
    confirm: { last_confirm: lastConfirm({ home_score: 21, away_score: 14, score_vlm_locked: true }) },
    video: { has_frame: true, live_seq: 10, widget_seq: 7, same_seq: false, paint: false, crop_hash: CROP },
  });
  assert.ok(ing);
  assert.equal(ing.sameSeq, false);
  assert.equal(ing.paint, false);
  assert.equal(ing.boardLocked, false);
  assert.equal(ing.homeScore, null);
});

test("stale ticket empties when crop_hash moves", () => {
  assert.equal(ticketFresh({ ticketCropHash: "aaa", liveCropHash: "bbb" }), false);
  const b = pickBoard({
    home_score: 21,
    away_score: 14,
    score_vlm_locked: true,
    confirm_ticket_id: TICKET,
    crop_hash: "crop-now",
    last_confirm: lastConfirm({
      home_score: 21,
      away_score: 14,
      crop_hash: "crop-was",
      score_vlm_locked: true,
    }),
  });
  assert.equal(b.home, null);
  assert.equal(b.away, null);
  assert.equal(b.locked, false);

  const ing = parseDeckMessage({
    type: "snapshot",
    situation: {
      game_state: "gameplay",
      home_score: 21,
      away_score: 14,
      score_vlm_locked: true,
      confirm_ticket_id: TICKET,
      crop_hash: "crop-now",
    },
    confirm: {
      last_confirm: lastConfirm({
        home_score: 21,
        away_score: 14,
        crop_hash: "crop-was",
        score_vlm_locked: true,
      }),
    },
    video: { has_frame: true, same_seq: true, paint: true, crop_hash: "crop-now" },
  });
  assert.ok(ing);
  assert.equal(ing.homeScore, null);
  assert.equal(ing.awayScore, null);
  assert.equal(ing.boardLocked, false);
  assert.equal(scorebugPair(ing), "");
});
