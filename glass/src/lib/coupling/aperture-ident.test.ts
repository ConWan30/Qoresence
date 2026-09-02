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

test("ident latches on non-play even when JPEG is current", () => {
  assert.equal(apertureIdentOn({ ...live, hdmi: "menu" }), true);
  assert.equal(apertureIdentOn({ ...live, hdmi: "stale" }), true);
});

test("ident latches on seq-skew even when JPEG is current", () => {
  assert.equal(apertureIdentOn({ ...live, sameSeq: false }), true);
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

test("HOLD ident can cover a current JPEG on menu", () => {
  const ident = apertureIdentOn({ ...live, hdmi: "menu" });
  const picture = hdmiPictureVisible(true);
  assert.equal(ident, true);
  assert.equal(picture, true);
});
