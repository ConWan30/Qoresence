import assert from "node:assert/strict";
import { test } from "node:test";
import { clutchPulse } from "./clutch-pulse.ts";

test("quiet low score does not pulse the plinth", () => {
  assert.equal(clutchPulse({ kind: "quiet", score: 0.1, armed: false }), "off");
});

test("pressure or a rising score is a near pulse", () => {
  assert.equal(clutchPulse({ kind: "pressure", score: 0.35, armed: false }), "near");
  assert.equal(clutchPulse({ kind: "quiet", score: 0.45, armed: false }), "near");
});

test("climax, score play, or armed clip is a hot pulse", () => {
  assert.equal(clutchPulse({ kind: "climax", score: 0.5, armed: false }), "hot");
  assert.equal(clutchPulse({ kind: "score_play", score: 0.2, armed: false }), "hot");
  assert.equal(clutchPulse({ kind: "window", score: 0.4, armed: true }), "hot");
  assert.equal(clutchPulse({ kind: "quiet", score: 0.74, armed: false }), "hot");
});

test("companion drive pressure pulses the plinth even if clutch snap is quiet", () => {
  assert.equal(
    clutchPulse({
      kind: "quiet",
      score: 0.1,
      armed: false,
      companionPhase: "pressure",
      companionClimax: 0.35,
    }),
    "near",
  );
});
