import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { skewState } from "./skew-alarm.ts";

test("skew ok inside budget", () => {
  assert.equal(
    skewState({ hidClockNs: 1_000_000, hdmiClockNs: 1_010_000, frameSeqGap: 0, ageS: 0.05 }),
    "ok",
  );
});

test("skew warn at 60ms or age 1s", () => {
  assert.equal(
    skewState({ hidClockNs: 0, hdmiClockNs: 70_000_000, frameSeqGap: 0, ageS: 0.1 }),
    "warn",
  );
  assert.equal(
    skewState({ hidClockNs: 1, hdmiClockNs: 1, frameSeqGap: 0, ageS: 1.2 }),
    "warn",
  );
});

test("skew alarm at 120ms or age 2s or seq gap 30", () => {
  assert.equal(
    skewState({ hidClockNs: 0, hdmiClockNs: 130_000_000, frameSeqGap: 0, ageS: 0.1 }),
    "alarm",
  );
  assert.equal(
    skewState({ hidClockNs: 1, hdmiClockNs: 1, frameSeqGap: 0, ageS: 2.1 }),
    "alarm",
  );
  assert.equal(
    skewState({ hidClockNs: 1, hdmiClockNs: 1, frameSeqGap: 31, ageS: 0.1 }),
    "alarm",
  );
});

test("skew copy never interpolates or blames a person", () => {
  const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "skew-alarm.ts"), "utf8");
  assert.doesNotMatch(src, /cheat|lag switch|fix|eligib|human/i);
});
