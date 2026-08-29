import assert from "node:assert/strict";
import { test } from "node:test";
import { pictureLagMs, scorePadSync, syncChipText } from "./pad-sync.ts";

const live = {
  connected: true,
  reports: 3100,
  prevReports: 3000,
  pllLock: false,
  binds: 0,
  lagMs: 21,
  jitterMs: 52,
  videoAgeS: 0.06,
  hidSeq: 23531,
  videoSeq: 23533,
  energy: 0,
  held: [] as string[],
};

test("fresh HDMI + HID on the same seq is a video-clock lock", () => {
  const s = scorePadSync(live);
  assert.equal(s.hid, "live");
  assert.equal(s.lock, "lock");
  assert.match(s.why, /video clock/i);
});

test("HID reports climbing counts as registering even with empty buttons", () => {
  const s = scorePadSync(live);
  assert.equal(s.registering, true);
});

test("empty laptop HID is DualSense-on-PS5 success, not PAD WAIT", () => {
  const s = scorePadSync({ ...live, connected: false, reports: 0, prevReports: 0, hidSeq: 0 });
  assert.equal(s.hid, "wait");
  assert.equal(s.lock, "open");
  assert.equal(s.registering, false);
  assert.equal(s.why, "pad_not_on_this_host");
  assert.doesNotMatch(s.why, /PAD WAIT/i);
  assert.doesNotMatch(s.why, /press R2/i);
});

test("stale picture with a live pad is drift — not a lock", () => {
  const s = scorePadSync({ ...live, videoAgeS: 4, hidSeq: 10, videoSeq: 900 });
  assert.equal(s.hid, "live");
  assert.equal(s.lock, "drift");
});

test("PLL lock is sync even if seq is quiet", () => {
  const s = scorePadSync({ ...live, pllLock: true, hidSeq: 0, videoSeq: 0 });
  assert.equal(s.lock, "lock");
});

test("SYNC chip is measured lag or UNBOUND — never a decorated 0", () => {
  assert.equal(syncChipText(null), "UNBOUND");
  assert.equal(syncChipText(undefined), "UNBOUND");
  assert.equal(syncChipText(0), "UNBOUND");
  assert.equal(syncChipText(80), "80ms");
  assert.equal(pictureLagMs(0, 0, 0), null);
  assert.equal(pictureLagMs(0.04, 0, 0), 40);
  assert.equal(pictureLagMs(0, 0, 80), 80);
});
