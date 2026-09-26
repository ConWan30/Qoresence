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

test("dark theater covers a current JPEG with the HDMI Q ident", () => {
  assert.equal(apertureIdentOn({ ...live, planeDim: true }), true);
  assert.equal(apertureIdentOn({ ...live, livePaint: false }), true);
  assert.equal(apertureIdentOn({ ...live, planeDim: true, livePaint: false }), true);
  assert.equal(hdmiPictureVisible(true), true);
});

test("ident stays off in replay even when dark or with no JPEG", () => {
  assert.equal(apertureIdentOn({ jpgOk: false, replay: true }), false);
  assert.equal(apertureIdentOn({ ...live, replay: true, jpgOk: false }), false);
  assert.equal(
    apertureIdentOn({ ...live, replay: true, planeDim: true, livePaint: false }),
    false,
  );
});

test("fresh LIVE JPEG and ident are exclusive", () => {
  const ident = apertureIdentOn(live);
  const picture = hdmiPictureVisible(true);
  assert.equal(ident, false);
  assert.equal(picture, true);
});

test("a menu label alone keeps the JPEG; plane dim shows the HDMI Q", () => {
  assert.equal(apertureIdentOn({ ...live, hdmi: "menu" }), false);
  assert.equal(apertureIdentOn({ ...live, hdmi: "menu", planeDim: true }), true);
  assert.equal(hdmiPictureVisible(true), true);
});
