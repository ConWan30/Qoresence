import assert from "node:assert/strict";
import test from "node:test";
import { hidAt, measureLag, pushHid, resetHid, videoClock } from "../src/lib/coupling/sync.ts";

test("bind lag wins over video age when it looks like IVC", () => {
  assert.equal(measureLag(0.04, 84), 84);
  assert.equal(measureLag(0.12, 0), 120);
  assert.equal(measureLag(0, 0), 80);
  assert.equal(measureLag(0.04, 84, 48), 48);
});

test("HID retimes onto the video clock", () => {
  resetHid();
  pushHid({ t: 1000, r2: 0, left: 0, held: [] });
  pushHid({ t: 1080, r2: 1, left: 0.2, held: ["r2"] });
  pushHid({ t: 1160, r2: 1, left: 0.2, held: ["r2"] });
  const vis = hidAt(videoClock(1160, 80));
  assert.equal(vis.r2, 1);
  const tooEarly = hidAt(videoClock(1080, 80));
  assert.equal(tooEarly.r2, 0);
});
