import assert from "node:assert/strict";
import test from "node:test";
import { EMPTY_METER, framesDelta, parseSignalMeter, readTicks, tallyState, type SignalMeter } from "./signal-meter.ts";

const NOW = 1_000_000;

function health(video: Record<string, unknown>, sb: Record<string, unknown> = {}) {
  return {
    state: { video, local_scorebug: { enabled: true, state: "blank", reason: "idle", reads: 0, agreed: 0, ...sb } },
    sync_health: { fps_meas: 59.6 },
    lease: { ok: true, device: "USB3.0 Video" },
  };
}

const LIVE_VIDEO = { frames: 900, pushes: 900, has_frame: true, age_s: 0.04, paint: true, same_seq: true, plane_dim: false };

test("no capture: real no-frame /health is DARK, never LIVE", () => {
  const m = parseSignalMeter(health({ frames: 0, has_frame: false, age_s: null, paint: false, same_seq: false, plane_dim: true, paint_reason: "no_frame" }), NOW)!;
  assert.equal(tallyState(m, { now: NOW }), "dark");
});

test("LIVE only when paint + same_seq + fresh age + frames", () => {
  const m = parseSignalMeter(health(LIVE_VIDEO), NOW)!;
  assert.equal(tallyState(m, { now: NOW }), "live");
  assert.equal(m.card, "USB3.0 Video");
  assert.equal(m.fpsMeas, 59.6);
});

test("seq skew, plane dim or unpainted is HOLD, not LIVE", () => {
  for (const patch of [{ same_seq: false }, { plane_dim: true }, { paint: false }, { age_s: 2.5 }]) {
    const m = parseSignalMeter(health({ ...LIVE_VIDEO, ...patch }), NOW)!;
    assert.equal(tallyState(m, { now: NOW }), "hold", JSON.stringify(patch));
  }
});

test("aged-out hub or frames that stopped climbing is STALL", () => {
  const m = parseSignalMeter(health({ ...LIVE_VIDEO, age_s: 6.4 }), NOW)!;
  assert.equal(tallyState(m, { now: NOW }), "stall");
  const m2 = parseSignalMeter(health(LIVE_VIDEO), NOW)!;
  assert.equal(tallyState(m2, { now: NOW, advancing: false }), "stall");
});

test("stale /health (Deck stopped answering) goes DARK", () => {
  const m = parseSignalMeter(health(LIVE_VIDEO), NOW)!;
  assert.equal(tallyState(m, { now: NOW + 10_000 }), "dark");
  assert.equal(tallyState(EMPTY_METER as SignalMeter, { now: NOW }), "dark");
});

test("read ticks only claim what the backend reports", () => {
  const sure = parseSignalMeter(health(LIVE_VIDEO, { state: "sure", reason: "ok" }), NOW)!;
  assert.deepEqual([readTicks(sure.scorebug).lit, readTicks(sure.scorebug).tone], [3, "locked"]);
  const agreeing = parseSignalMeter(health(LIVE_VIDEO, { reason: "agreeing" }), NOW)!;
  assert.deepEqual([readTicks(agreeing.scorebug).lit, readTicks(agreeing.scorebug).need], [1, 3]);
  const recheck = parseSignalMeter(health(LIVE_VIDEO, { reason: "recheck" }), NOW)!;
  assert.equal(readTicks(recheck.scorebug).need, 9);
  const blank = parseSignalMeter(health(LIVE_VIDEO, { reason: "blank" }), NOW)!;
  assert.equal(readTicks(blank.scorebug).lit, 0);
});

test("empty or junk /health parses to null", () => {
  assert.equal(parseSignalMeter(null), null);
  assert.equal(parseSignalMeter("nope"), null);
});

test("frames++ follows pushes, not the ClipBuffer fill that plateaus", () => {
  const a = parseSignalMeter(health({ ...LIVE_VIDEO, frames: 1802, pushes: 5000 }), NOW)!;
  const b = parseSignalMeter(health({ ...LIVE_VIDEO, frames: 1802, pushes: 5060 }), NOW + 1000)!;
  assert.equal(framesDelta(a, b), 60);
  assert.equal(framesDelta(EMPTY_METER as SignalMeter, b), null);
});

test("lens word: LIVE hidden without capture; shown only when the tally is live", async () => {
  const { lensWord } = await import("./signal-meter.ts");
  const base = { replay: false, throwAttempt: false, clutchLabel: null };
  const dark = parseSignalMeter(health({ frames: 0, has_frame: false, age_s: null, paint: false, same_seq: false, plane_dim: true, paint_reason: "no_frame" }), NOW)!;
  assert.equal(lensWord({ ...base, tally: tallyState(dark, { now: NOW }) }), null);
  assert.equal(lensWord({ ...base, tally: tallyState(EMPTY_METER, { now: NOW }) }), null);
  for (const t of ["dark", "hold", "stall"] as const) assert.equal(lensWord({ ...base, tally: t }), null);
  const live = parseSignalMeter(health(LIVE_VIDEO), NOW)!;
  assert.equal(lensWord({ ...base, tally: tallyState(live, { now: NOW }) }), "LIVE");
  assert.equal(lensWord({ ...base, tally: "dark", replay: true }), "REPLAY");
  assert.equal(lensWord({ ...base, tally: "dark", throwAttempt: true }), "—");
});
