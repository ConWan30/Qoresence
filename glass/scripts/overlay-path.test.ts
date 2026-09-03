import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

/** Fallback overlay.html digitsLicensed — FrameHub video.crop_hash first. */
const OVERLAY = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "qoresence",
  "deck",
  "overlay.html",
);

function loadOverlayDigitsLicensed(): (s: unknown, snap: unknown) => boolean {
  const html = readFileSync(OVERLAY, "utf8");
  const start = html.indexOf("function digitsLicensed(s, snap){");
  assert.ok(start >= 0, "overlay.html missing digitsLicensed");
  const end = html.indexOf("\n}", start);
  assert.ok(end > start, "overlay.html digitsLicensed unclosed");
  const src = html.slice(start, end + 2);
  const compact = src.replace(/\s+/g, "");
  assert.ok(compact.includes("video.crop_hash||s.crop_hash||s.frame_hash"), src);
  return new Function(`${src}; return digitsLicensed;`)() as (s: unknown, snap: unknown) => boolean;
}

const TICKET = "fixture-confirm";
const WAS = "crop-was";
const NOW = "crop-now";

function sit(crop: string) {
  return {
    score_home: 0,
    score_away: 1,
    score_vlm_locked: true,
    confirm_ticket_id: TICKET,
    crop_hash: crop,
  };
}

function snap(args: { sitCrop: string; videoCrop?: string }) {
  const s = sit(args.sitCrop);
  return {
    type: "snapshot",
    situation: s,
    confirm: {
      last_confirm: {
        ticket_id: TICKET,
        crop_hash: WAS,
        score_vlm_locked: true,
      },
    },
    video: {
      has_frame: true,
      same_seq: true,
      ...(args.videoCrop != null ? { crop_hash: args.videoCrop } : {}),
    },
  };
}

test("overlay liveCrop prefers FrameHub video.crop_hash", () => {
  const digitsLicensed = loadOverlayDigitsLicensed();
  const s = sit(WAS);
  const moved = snap({ sitCrop: WAS, videoCrop: NOW });
  assert.equal(digitsLicensed(s, moved), false, "video move + stale situation → EMPTY");
});

test("overlay digits EMPTY when video.crop_hash moves and situation is stale", () => {
  const digitsLicensed = loadOverlayDigitsLicensed();
  const s = sit(WAS);
  assert.equal(digitsLicensed(s, snap({ sitCrop: WAS, videoCrop: NOW })), false);
  assert.equal(digitsLicensed(s, snap({ sitCrop: WAS, videoCrop: WAS })), true);
});

test("overlay liveCrop falls back to situation when FrameHub crop is absent", () => {
  const digitsLicensed = loadOverlayDigitsLicensed();
  assert.equal(digitsLicensed(sit(WAS), snap({ sitCrop: WAS })), true);
  assert.equal(digitsLicensed(sit(NOW), snap({ sitCrop: NOW })), false);
});
