import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { parseAgentPlane } from "../src/lib/coupling/agent-plane.ts";
import { mergeAgentPlane, evaluateAgents } from "../src/lib/coupling/agents.ts";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const TICKET = "fixture-confirm";
const WAS = "crop-was";
const NOW = "crop-now";

function licensedSnap(args: { sitCrop: string; videoCrop: string; sameSeq?: boolean }) {
  return {
    type: "snapshot",
    situation: {
      game_state: "gameplay",
      home_score: 0,
      away_score: 1,
      score_vlm_locked: true,
      confirm_ticket_id: TICKET,
      crop_hash: args.sitCrop,
    },
    confirm: {
      last_confirm: {
        ticket_id: TICKET,
        home_score: 0,
        away_score: 1,
        crop_hash: WAS,
        score_vlm_locked: true,
        clock_ns: 1_000_000_000,
      },
    },
    video: {
      has_frame: true,
      same_seq: args.sameSeq !== false,
      paint: args.sameSeq !== false,
      crop_hash: args.videoCrop,
    },
  };
}

test("agent-plane leftover score OR-gate is gone", () => {
  const src = readFileSync(join(ROOT, "src/lib/coupling/agent-plane.ts"), "utf8");
  assert.equal(src.includes("scoreboard_locked"), false);
  assert.doesNotMatch(src, /score_vlm_locked\s*\|\|/);
  assert.ok(src.includes("pickBoard("));
});

test("parseAgentPlane does not paint digits from scoreboard_locked or last_confirm alone", () => {
  const plane = parseAgentPlane({
    snapshot: {
      situation: {
        game_state: "gameplay",
        home_score: 21,
        away_score: 14,
        scoreboard_locked: true,
        confirm_ticket_id: TICKET,
      },
      confirm: { last_confirm: { ticket_id: TICKET, home_score: 21, away_score: 14 } },
    },
  });
  assert.equal(plane.vlmLocked, false);
  assert.equal(plane.vlmBoard, "");
});

test("parseAgentPlane vlmBoard follows pickBoard — FrameHub crop_hash move blanks Theater", () => {
  const locked = parseAgentPlane({ snapshot: licensedSnap({ sitCrop: WAS, videoCrop: WAS }) });
  assert.equal(locked.vlmLocked, true);
  assert.equal(locked.vlmBoard, "0-1");

  const moved = parseAgentPlane({ snapshot: licensedSnap({ sitCrop: WAS, videoCrop: NOW }) });
  assert.equal(moved.vlmLocked, false);
  assert.equal(moved.vlmBoard, "");
});

test("parseAgentPlane Same-Seq skew blanks vlmBoard", () => {
  const plane = parseAgentPlane({
    snapshot: licensedSnap({ sitCrop: WAS, videoCrop: WAS, sameSeq: false }),
  });
  assert.equal(plane.vlmLocked, false);
  assert.equal(plane.vlmBoard, "");
});

test("agent rail Board lock text is pickBoard-gated", () => {
  const empty = mergeAgentPlane(
    evaluateAgents({
      phrase: "HUDDLE",
      phraseLive: false,
      ticketLive: false,
      ticketId: "",
      heatLine: "",
      heatVetoed: false,
      scoreLine: "",
      confirm: null,
      pllLock: true,
      hdmiLive: true,
    }),
    parseAgentPlane({
      snapshot: {
        situation: { home_score: 0, away_score: 1, scoreboard_locked: true },
        confirm: { last_confirm: { home_score: 0, away_score: 1 } },
      },
    }),
    false,
  );
  const gemini = empty.find((r) => r.role === "gemini");
  assert.ok(gemini);
  assert.equal(gemini.action === "note" && /Board lock/.test(gemini.text), false);

  const licensed = mergeAgentPlane(
    evaluateAgents({
      phrase: "HUDDLE",
      phraseLive: false,
      ticketLive: false,
      ticketId: "",
      heatLine: "",
      heatVetoed: false,
      scoreLine: "",
      confirm: null,
      pllLock: true,
      hdmiLive: true,
    }),
    parseAgentPlane({ snapshot: licensedSnap({ sitCrop: WAS, videoCrop: WAS }) }),
    false,
  );
  const geminiLock = licensed.find((r) => r.role === "gemini");
  assert.ok(geminiLock);
  assert.equal(geminiLock.action, "note");
  assert.match(geminiLock.text, /Board lock 0-1/);
});
