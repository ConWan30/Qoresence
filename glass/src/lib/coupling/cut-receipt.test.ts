import assert from "node:assert/strict";
import { test } from "node:test";
import {
  addDeadSpan,
  clipStem,
  cutRenderUrl,
  gateLine,
  receiptUrl,
  spanState,
  spanWhy,
  stripPieces,
  toPlayerT,
  toSourceT,
  type CutReceipt,
} from "./cut-receipt.ts";

const receipt: CutReceipt = {
  referee: "offline_triple_proof",
  source_duration_s: 20,
  edited_duration_s: 13.8,
  spans: [
    { id: "s0", t0_s: 5, t1_s: 12, kinds: ["pause"], decision: "cut", reason: "triple_proof" },
    { id: "s1", t0_s: 14, t1_s: 16, kinds: ["menu"], decision: "suggest" },
  ],
  time_map: [
    [0, 0, 5.4],
    [5.4, 11.6, 8.4],
  ],
  render: { state: "done", path: "hdmi_clip_20260925_020000.cut.mp4" },
};

test("clip urls only accept hdmi clip names", () => {
  assert.equal(clipStem("/media/clips/hdmi_clip_20260925_020000.mp4?v=1"), "hdmi_clip_20260925_020000");
  assert.equal(clipStem("/media/clips/stem_20260926_120000.mp4"), "stem_20260926_120000");
  assert.equal(
    cutRenderUrl("/media/clips/stem_20260926_120000.mp4", {
      ...receipt,
      render: { state: "done", path: "stem_20260926_120000.cut.mp4" },
    }),
    "/media/clips/stem_20260926_120000.cut.mp4",
  );
  assert.equal(receiptUrl("/media/clips/hdmi_clip_x.mp4"), "/media/clips/hdmi_clip_x.cut.json");
  assert.equal(clipStem("/media/clips/../etc.mp4"), "");
  assert.equal(
    cutRenderUrl("/media/clips/hdmi_clip_20260925_020000.mp4", receipt),
    "/media/clips/hdmi_clip_20260925_020000.cut.mp4",
  );
  assert.equal(
    cutRenderUrl("/media/clips/hdmi_clip_x.mp4", { ...receipt, render: { state: "done", path: "../x" } }),
    "",
  );
  assert.equal(cutRenderUrl("/media/clips/hdmi_clip_x.mp4", { ...receipt, render: { state: "pending" } }), "");
});

test("time map round trip and removed time snaps forward", () => {
  assert.equal(toSourceT(receipt, 6, true), 12.2);
  assert.equal(toPlayerT(receipt, 12.2, true), 6);
  assert.equal(toPlayerT(receipt, 8, true), 5.4);
  assert.equal(toSourceT(receipt, 6, false), 6);
  assert.equal(toPlayerT(null, 6, true), 6);
});

test("span state honours user override and suggestions", () => {
  const [s0, s1] = receipt.spans!;
  assert.equal(spanState(s0), "removed");
  assert.equal(spanState(s1), "suggested");
  assert.equal(spanState({ ...s0, user: "keep" }), "kept");
  assert.equal(spanState({ ...s1, user: "cut" }), "removed");
  assert.match(spanWhy({ ...s0, evidence: { still_s: 6.9, options_press_before_s: 0.2 } }), /still 6\.9s · Options −0\.2s · triple_proof/);
});

test("strip pieces cover the source once", () => {
  const p = stripPieces(receipt);
  assert.deepEqual(
    p.map((x) => x.kind),
    ["keep", "cut", "keep", "suggest", "keep"],
  );
  assert.ok(Math.abs(p.reduce((a, x) => a + x.frac, 0) - 1) < 1e-9);
});

test("dead span marking validates order", () => {
  assert.equal(addDeadSpan([], null, 5, "pause").error, "mark start first");
  assert.equal(addDeadSpan([], 5, 5.1, "pause").error, "end must be after start");
  const a = addDeadSpan([[9, 11, "menu"]], 2.12345, 4, "pause");
  assert.deepEqual(a.dead, [
    [2.123, 4, "pause"],
    [9, 11, "menu"],
  ]);
});

test("gate line", () => {
  assert.equal(gateLine(null), "");
  assert.equal(
    gateLine({ verdict: "insufficient", min_clips: 20, gaps: ["no labelled menu"], summary: { football_clips_with_dead: 3, over_cut_s: 0 } }),
    "Pilot gate: insufficient · 3/20 clips · over-cut 0s · no labelled menu",
  );
  assert.equal(
    gateLine({
      verdict: "insufficient",
      min_clips: 20,
      summary: { football_clips_with_dead: 6, over_cut_s: 0, witness_proposed_s: 4.5, witness_dead_s: 12 },
    }),
    "Pilot gate: insufficient · 6/20 clips · over-cut 0s · witness 4.5s / dead 12s",
  );
});
