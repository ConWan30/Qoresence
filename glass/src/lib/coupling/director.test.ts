import assert from "node:assert/strict";
import { test } from "node:test";
import {
  autoClipAllowed,
  directorBrief,
  directorReasons,
  type DirectorInput,
} from "./director.ts";

const quiet: DirectorInput = {
  now: 10_000,
  holdUntil: 0,
  clipBusy: false,
  companionArmed: false,
  redZone: false,
  late: false,
  close: false,
  clutchScore: 0,
  clutchKind: "quiet",
  clutchLabel: "watching",
  clutchWhy: "no clutch pressure",
  companionWhy: "",
  clipWorth: 0,
};

test("quiet picture stays on watch — no invented take", () => {
  const d = directorBrief(quiet);
  assert.equal(d.mode, "watch");
  assert.match(d.why, /watching/i);
  assert.equal(d.armHot, false);
});

test("red zone + clutch window primes the next take", () => {
  const d = directorBrief({
    ...quiet,
    redZone: true,
    clutchKind: "window",
    clutchScore: 0.62,
    clutchLabel: "window",
    clutchWhy: "red zone late",
    clipWorth: 0.7,
  });
  assert.equal(d.mode, "prime");
  assert.match(d.why, /red zone/i);
  assert.equal(d.armHot, true);
});

test("companion armed beats a quiet clutch score", () => {
  const d = directorBrief({
    ...quiet,
    companionArmed: true,
    companionWhy: "fast confirm match",
  });
  assert.equal(d.mode, "armed");
  assert.match(d.why, /armed|fast confirm/i);
});

test("HOLD silences auto-clip until the clock expires", () => {
  assert.equal(autoClipAllowed(20_000, 10_000), false);
  assert.equal(autoClipAllowed(10_000, 10_000), true);
  const d = directorBrief({ ...quiet, holdUntil: 20_000 });
  assert.equal(d.mode, "hold");
  assert.match(d.why, /hold/i);
});

test("encoding 30s owns the lamp", () => {
  const d = directorBrief({ ...quiet, clipBusy: true, holdUntil: 99_000, companionArmed: true });
  assert.equal(d.mode, "encode");
  assert.match(d.why, /encod/i);
});

test("ticker keeps last three clip or clutch lines", () => {
  const rows = directorReasons([
    { key: "a", title: "HDMI CLIP 30s", path: "confirm", reason: "x", clock: "now", icon: "🎬", at: 3 },
    { key: "b", title: "chat noise", path: "", reason: "", clock: "now", icon: "", at: 2 },
    { key: "c", title: "window · red zone", path: "fast", reason: "window", clock: "now", icon: "⚡", at: 1 },
    { key: "d", title: "older clip", path: "confirm", reason: "y", clock: "now", icon: "🎬", at: 0 },
    { key: "e", title: "HDMI CLIP 8s", path: "fast", reason: "z", clock: "now", icon: "🎬", at: 4 },
  ]);
  assert.deepEqual(rows, ["HDMI CLIP 8s", "HDMI CLIP 30s", "window · red zone"]);
});
