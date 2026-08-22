import assert from "node:assert/strict";
import { test } from "node:test";
import { HDMI_JPEG_KEEP, hdmiPictureVisible } from "./hdmi-picture.ts";

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
});
