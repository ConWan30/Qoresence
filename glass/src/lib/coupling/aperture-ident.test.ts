import assert from "node:assert/strict";
import { test } from "node:test";
import { APERTURE_IDENT, apertureIdentOn } from "./aperture-ident.ts";
import { hdmiPictureVisible } from "./hdmi-picture.ts";

const live = {
  jpgOk: true,
  replay: false,
  hdmi: "live" as const,
  sameSeq: true,
};

test("ident is the ship token", () => {
  assert.equal(APERTURE_IDENT, "apertureIdent");
});

test("ident paints when JPEG has not arrived", () => {
  assert.equal(apertureIdentOn({ jpgOk: false }), true);
  assert.equal(apertureIdentOn({ jpgOk: false, replay: false }), true);
});

test("ident stays off while JPEG is current on LIVE same-seq", () => {
  assert.equal(apertureIdentOn(live), false);
  assert.equal(hdmiPictureVisible(true), true);
});

test("pause, menu, and stale keep a current JPEG on the stage", () => {
  assert.equal(apertureIdentOn({ ...live, hdmi: "menu" }), false);
  assert.equal(apertureIdentOn({ ...live, hdmi: "stale" }), false);
  assert.equal(hdmiPictureVisible(true), true);
});

test("seq-skew keeps a current JPEG on the stage", () => {
  assert.equal(apertureIdentOn({ ...live, sameSeq: false }), false);
  assert.equal(hdmiPictureVisible(true), true);
});

test("planeDim is not an ident field — picture stays", () => {
  assert.equal(apertureIdentOn(live), false);
  assert.equal(hdmiPictureVisible(true), true);
});

test("livePaint is not an ident field — picture stays", () => {
  assert.equal(apertureIdentOn(live), false);
  assert.equal(hdmiPictureVisible(true), true);
});

test("ident stays off in replay even with no JPEG", () => {
  assert.equal(apertureIdentOn({ jpgOk: false, replay: true }), false);
  assert.equal(apertureIdentOn({ ...live, replay: true, jpgOk: false }), false);
});

test("fresh LIVE JPEG and ident are exclusive", () => {
  const ident = apertureIdentOn(live);
  const picture = hdmiPictureVisible(true);
  assert.equal(ident, false);
  assert.equal(picture, true);
});

test("a current JPEG stays up on the pause menu", () => {
  const ident = apertureIdentOn({ ...live, hdmi: "menu" });
  const picture = hdmiPictureVisible(true);
  assert.equal(ident, false);
  assert.equal(picture, true);
});
