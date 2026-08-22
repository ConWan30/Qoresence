import assert from "node:assert/strict";
import { test } from "node:test";
import { scoreLiveHealth } from "./live-health.ts";

const base = {
  ageS: 0.2,
  frames: 120,
  pushes: 118,
  prevFrames: 110,
  prevPushes: 110,
  jpgOk: true,
  jpgAgeMs: 40,
  stageMode: "live" as const,
};

test("green only when age is fresh and frames/pushes climb", () => {
  const h = scoreLiveHealth(base);
  assert.equal(h.tone, "green");
  assert.equal(h.label, "LIVE");
});

test("amber when JPEG pumps but frames have stopped", () => {
  const h = scoreLiveHealth({ ...base, frames: 120, prevFrames: 120, pushes: 118, prevPushes: 118, ageS: 2.4 });
  assert.equal(h.tone, "amber");
  assert.match(h.reason, /not the capture card|JPEG still arriving/);
});

test("red stall never blames the capture card", () => {
  const h = scoreLiveHealth({
    ...base,
    ageS: 8,
    frames: 40,
    prevFrames: 40,
    pushes: 40,
    prevPushes: 40,
    jpgOk: false,
    jpgAgeMs: 9000,
  });
  assert.equal(h.tone, "red");
  assert.match(h.reason, /lock cascade|not the card/);
});

test("replay is amber — LIVE owns the picture", () => {
  const h = scoreLiveHealth({ ...base, stageMode: "replay" });
  assert.equal(h.tone, "amber");
  assert.equal(h.label, "REPLAY");
});
