import assert from "node:assert/strict";
import { test } from "node:test";
import { APERTURE_IDENT, apertureIdentOn } from "./aperture-ident.ts";
import { hdmiPictureVisible } from "./hdmi-picture.ts";

test("ident is the ship token", () => {
  assert.equal(APERTURE_IDENT, "apertureIdent");
});

test("ident paints only when JPEG has not arrived", () => {
  assert.equal(apertureIdentOn(false), true);
  assert.equal(apertureIdentOn(false, false), true);
});

test("ident stays off while JPEG is current", () => {
  assert.equal(apertureIdentOn(true), false);
  assert.equal(apertureIdentOn(true, false), false);
  assert.equal(hdmiPictureVisible(true), true);
});

test("ident stays off in replay even with no JPEG", () => {
  assert.equal(apertureIdentOn(false, true), false);
  assert.equal(apertureIdentOn(true, true), false);
});

test("ident and picture are exclusive", () => {
  for (const jpg of [true, false]) {
    const picture = hdmiPictureVisible(jpg);
    const ident = apertureIdentOn(jpg, false);
    assert.equal(picture && ident, false);
    assert.equal(picture || ident, true);
  }
});
