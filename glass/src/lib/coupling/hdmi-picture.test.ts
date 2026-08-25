import assert from "node:assert/strict";
import { test } from "node:test";
import { HDMI_LIVE_FEED } from "./qoresence-deck.ts";
import {
  HDMI_JPEG_KEEP,
  HDMI_JPEG_OVERLAP,
  HDMI_JPEG_PUMP_MS,
  HDMI_JPEG_PUSH,
  HDMI_PICTURE_SWAP,
  HDMI_LIVE_PAINT,
  hdmiPictureVisible,
  hdmiStackLayers,
} from "./hdmi-picture.ts";

test("picture stays up when JPEG arrived even if livePaint flickers", () => {
  assert.equal(hdmiPictureVisible(true, true), true);
  assert.equal(hdmiPictureVisible(true, false), true);
  assert.equal(hdmiPictureVisible(true), true);
});

test("picture hides only when no JPEG has arrived", () => {
  assert.equal(hdmiPictureVisible(false, true), false);
  assert.equal(hdmiPictureVisible(false, false), false);
});

test("hygiene marker is the ship token", () => {
  assert.equal(HDMI_JPEG_KEEP, "hdmiJpegKeep");
  assert.equal(HDMI_LIVE_FEED, "jpeg");
});

test("JPEG pump does not add a display delay", () => {
  assert.ok(HDMI_JPEG_PUMP_MS <= 16);
  assert.equal(HDMI_JPEG_OVERLAP, true);
  assert.equal(HDMI_JPEG_PUSH, true);
});

test("LIVE paints on a canvas so JPEG decode cannot flash the stage", () => {
  assert.equal(HDMI_LIVE_PAINT, "canvas");
});

test("LIVE swap keeps both layers opaque so the stage cannot flash black", () => {
  assert.equal(HDMI_PICTURE_SWAP, "stack");
  const aFront = hdmiStackLayers(true);
  const bFront = hdmiStackLayers(false);
  assert.equal(aFront.a.opacity, "1");
  assert.equal(aFront.b.opacity, "1");
  assert.equal(bFront.a.opacity, "1");
  assert.equal(bFront.b.opacity, "1");
  assert.notEqual(aFront.a.zIndex, aFront.b.zIndex);
  assert.notEqual(bFront.a.zIndex, bFront.b.zIndex);
});
