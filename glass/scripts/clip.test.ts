import assert from "node:assert/strict";
import test from "node:test";
import { clipSeconds, parseClipResult, shouldClip } from "../src/lib/coupling/clip.ts";
import { parseFeedMoment } from "../src/lib/coupling/clutch.ts";

test("clips on climax and high worth, not quiet", () => {
  assert.equal(shouldClip("quiet", 0.1), false);
  assert.equal(shouldClip("window", 0.4), false);
  assert.equal(shouldClip("climax", 0.2), true);
  assert.equal(shouldClip("score_play", 0), true);
  assert.equal(shouldClip("window", 0.7), true);
  assert.equal(clipSeconds("score_play"), 15);
});

test("parses Deck export payload", () => {
  const r = parseClipResult(
    { ok: true, path: "clips/hdmi_clip_abc.mp4", name: "hdmi_clip_abc.mp4", url: "/media/clips/hdmi_clip_abc.mp4" },
    12,
  );
  assert.equal(r.ok, true);
  assert.equal(r.url, "/media/clips/hdmi_clip_abc.mp4");
});

test("moment feed keeps clip chips", () => {
  const m = parseFeedMoment({
    type: "moment",
    payload: { title: "FAST HDMI CLIP 12s", action: "clip", url: "/media/clips/hdmi_clip_abc.mp4", path: "fast" },
  });
  assert.ok(m);
  assert.match(m!.key, /^clip:/);
  assert.equal(m!.icon, "🎬");
  assert.equal(m!.path, "fast");
});
