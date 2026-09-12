import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

/** Fallback overlay.html digitsLicensed — scorebug crop chain, not hub full-frame. */
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
  assert.ok(compact.includes("s.live_crop_hash||s.crop_hash||s.frame_hash"), src);
  assert.ok(!compact.includes("video.crop_hash||s.crop_hash||s.frame_hash"), src);
  return new Function(`${src}; return digitsLicensed;`)() as (s: unknown, snap: unknown) => boolean;
}

const TICKET = "fixture-confirm";
const WAS = "crop-was";
const NOW = "crop-now";

function sit(crop: string, liveCropHash?: string) {
  return {
    score_home: 0,
    score_away: 1,
    score_vlm_locked: true,
    confirm_ticket_id: TICKET,
    crop_hash: crop,
    ...(liveCropHash != null ? { live_crop_hash: liveCropHash } : {}),
  };
}

function snap(args: { sitCrop: string; videoCrop?: string; liveCropHash?: string }) {
  const s = sit(args.sitCrop, args.liveCropHash);
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

test("overlay liveCrop ignores FrameHub video.crop_hash", () => {
  const digitsLicensed = loadOverlayDigitsLicensed();
  const s = sit(WAS);
  const moved = snap({ sitCrop: WAS, videoCrop: NOW });
  assert.equal(digitsLicensed(s, moved), true, "hub full-frame move must not veto licensed digits");
});

test("overlay digits EMPTY when situation crop_hash moves", () => {
  const digitsLicensed = loadOverlayDigitsLicensed();
  assert.equal(digitsLicensed(sit(NOW), snap({ sitCrop: NOW })), false);
  assert.equal(digitsLicensed(sit(WAS), snap({ sitCrop: WAS })), true);
});

test("overlay liveCrop uses situation scorebug chain", () => {
  const digitsLicensed = loadOverlayDigitsLicensed();
  assert.equal(digitsLicensed(sit(WAS), snap({ sitCrop: WAS })), true);
  assert.equal(digitsLicensed(sit(WAS, NOW), snap({ sitCrop: WAS, liveCropHash: NOW })), false);
});
