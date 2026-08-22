import assert from "node:assert/strict";
import test from "node:test";
import { clipHref, clipPublicPath, clipSeconds, parseClipResult, shouldClip } from "../src/lib/coupling/clip.ts";
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
  assert.equal(m!.url, "/media/clips/hdmi_clip_abc.mp4");
});

test("agent filesystem path becomes a clickable /media/clips href", () => {
  assert.equal(
    clipPublicPath(String.raw`C:\Users\con\Qoresence\clips\hdmi_clip_xyz.mp4`),
    "/media/clips/hdmi_clip_xyz.mp4",
  );
  const m = parseFeedMoment({
    type: "moment",
    payload: {
      title: "FAST HDMI CLIP 8s",
      action: "clip",
      path: String.raw`C:\Users\con\clips\hdmi_clip_xyz.mp4`,
      moment_path: "fast",
      name: "hdmi_clip_xyz.mp4",
    },
  });
  assert.ok(m);
  assert.equal(m!.url, "/media/clips/hdmi_clip_xyz.mp4");
  assert.equal(m!.path, "fast");
  assert.equal(clipHref(m!.url || "", "http://127.0.0.1:8765"), "http://127.0.0.1:8765/media/clips/hdmi_clip_xyz.mp4");
});
