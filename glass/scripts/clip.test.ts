import assert from "node:assert/strict";
import test from "node:test";
import {
  CLIP_RACK,
  clipHref,
  clipPublicPath,
  clipSeconds,
  momentPlayHref,
  parseClipResult,
  parseHdmiClipList,
  shouldClip,
} from "../src/lib/coupling/clip.ts";
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

test("parses legacy POST /api/clip nested clip object", () => {
  const r = parseClipResult(
    {
      ok: true,
      clip: {
        path: "clips/hdmi_clip_20260822_143015.mp4",
        name: "hdmi_clip_20260822_143015.mp4",
        url: "/media/clips/hdmi_clip_20260822_143015.mp4",
        duration_s: 30,
      },
    },
    30,
  );
  assert.equal(r.ok, true);
  assert.equal(r.name, "hdmi_clip_20260822_143015.mp4");
  assert.equal(r.url, "/media/clips/hdmi_clip_20260822_143015.mp4");
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

test("windows clip path in reason becomes a playable moment not a raw path title", () => {
  const m = parseFeedMoment({
    type: "moment",
    payload: {
      title: "HDMI CLIP 12s",
      action: "clip",
      icon: "🎬",
      reason: String.raw`C:\Users\Contr\Qoresence\clips\hdmi_clip_20260822_101224.mp4`,
      path: String.raw`C:\Users\Contr\Qoresence\clips\hdmi_clip_20260822_101224.mp4`,
      name: "hdmi_clip_20260822_101224.mp4",
    },
  });
  assert.ok(m);
  assert.equal(m!.url, "/media/clips/hdmi_clip_20260822_101224.mp4");
  assert.equal(m!.name, "hdmi_clip_20260822_101224.mp4");
  assert.doesNotMatch(m!.title, /C:\\Users/);
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

test("clutchbot moment with url+name is a playable media path", () => {
  const m = parseFeedMoment({
    type: "moment",
    payload: {
      title: "FAST HDMI CLIP 8s",
      action: "clip",
      icon: "🎬",
      url: "/media/clips/hdmi_clip_live.mp4",
      name: "hdmi_clip_live.mp4",
      moment_path: "fast",
      path: String.raw`C:\Users\con\clips\hdmi_clip_live.mp4`,
    },
  });
  assert.ok(m);
  assert.equal(m!.url, "/media/clips/hdmi_clip_live.mp4");
  assert.equal(m!.name, "hdmi_clip_live.mp4");
  assert.equal(m!.path, "fast");
  assert.match(clipHref(m!.url || ""), /\/media\/clips\/hdmi_clip_live\.mp4$/);
});

test("clutch chip without its own file does not borrow last HDMI clip", () => {
  const last = "http://127.0.0.1:8765/media/clips/hdmi_clip_live.mp4";
  assert.equal(
    momentPlayHref({ key: "clutch:window:red zone", title: "CLUTCH WINDOW · red zone", icon: "⚡" }, last),
    "",
  );
  assert.equal(momentPlayHref({ key: "chat:hello", title: "nice throw" }, last), "");
  assert.match(
    momentPlayHref({ url: "/media/clips/hdmi_clip_own.mp4", name: "hdmi_clip_own.mp4" }, last),
    /\/media\/clips\/hdmi_clip_own\.mp4$/,
  );
});

test("disk clip list skips sidecars and builds playable hrefs", () => {
  const clips = parseHdmiClipList(
    {
      ok: true,
      clips: [
        { name: "hdmi_clip_20260822_143015.mp4", url: "/media/clips/hdmi_clip_20260822_143015.mp4", size_bytes: 12 },
        { name: "hdmi_clip_20260822_143015.chapters.json", url: "/media/clips/hdmi_clip_20260822_143015.chapters.json" },
        { name: "notes.txt", url: "/media/clips/notes.txt" },
      ],
    },
    "http://127.0.0.1:8765",
  );
  assert.equal(clips.length, 1);
  assert.equal(clips[0].name, "hdmi_clip_20260822_143015.mp4");
  assert.equal(clips[0].href, "http://127.0.0.1:8765/media/clips/hdmi_clip_20260822_143015.mp4");
  assert.equal(CLIP_RACK, "clipRackDisk");
});
