import assert from "node:assert/strict";
import { test } from "node:test";
import { AGENT_COMPANION, companionDutyLine, parseCompanion } from "./companion.ts";

test("auto-clip stays on and clip arms on coupling + red zone", () => {
  const c = parseCompanion({
    companion: {
      ok: true,
      auto_clip: true,
      clip: {
        duty: "auto",
        armed: true,
        last: { title: "FAST HDMI CLIP 8s", path: "fast", url: "/media/clips/x.mp4", name: "x.mp4" },
        gates: { coupling: 0.72, red_zone: true, close: false, late: false, climax: 0.2 },
      },
      drive: { phase: "red_zone", climax: 0.2, why: "fast confirm match" },
      coach: { text: "Drive phase red_zone." },
      may_say: ["clip armed"],
    },
  });
  assert.equal(c.autoClip, true);
  assert.equal(c.armed, true);
  assert.equal(c.lastClip?.path, "fast");
  assert.equal(c.coach, "Drive phase red_zone.");
  assert.match(companionDutyLine(c), /CLIP ARMED/);
});

test("empty pack keeps auto-clip duty without inventing a last clip", () => {
  const c = parseCompanion({});
  assert.equal(c.autoClip, true);
  assert.equal(c.armed, false);
  assert.equal(c.lastClip, null);
  assert.match(companionDutyLine(c), /AUTO CLIP/);
});

test("hygiene marker is the ship token", () => {
  assert.equal(AGENT_COMPANION, "agentCompanion");
});
