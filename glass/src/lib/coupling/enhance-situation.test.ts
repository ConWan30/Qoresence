import assert from "node:assert/strict";
import { test } from "node:test";
import { QUIET_CLUTCH } from "./clutch.ts";
import { buildEnhanceSituation } from "./enhance-situation.ts";

test("empty gameTitle does not invent Madden in enhance payload", () => {
  const situation = buildEnhanceSituation({
    gameTitle: "",
    hdmi: "live",
    phrase: { phrase: "HUDDLE", confidence: 0.6, live: false },
    coupling: 0.4,
    clutch: { ...QUIET_CLUTCH, kind: "window", score: 0.5 },
    confirm: null,
  });
  assert.equal(situation.game_title, "");
  assert.equal(JSON.stringify(situation).includes("Madden"), false);
});

test("licensed gameTitle passes through unchanged", () => {
  const situation = buildEnhanceSituation({
    gameTitle: "EA SPORTS College Football 27",
    hdmi: "live",
    phrase: { phrase: "HUDDLE", confidence: 0.6, live: false },
    coupling: 0.4,
    clutch: QUIET_CLUTCH,
    confirm: null,
  });
  assert.equal(situation.game_title, "EA SPORTS College Football 27");
});
