import assert from "node:assert/strict";
import { test } from "node:test";
import { composeHonestyLattice, gamerHonestyCopy, parseNoulHealth } from "./honesty-lattice.ts";

test("select-plate temptation is Ident, never licenses digits", () => {
  const lat = composeHonestyLattice({
    boardHonesty: 0,
    presenceDensity: 0,
    lastGoodTemptation: 0.88,
    groundedNoul: 0.12,
  });
  assert.equal(lat.honestyBand, "ident");
  assert.equal(lat.identNow, true);
  assert.equal(lat.licensesDigits, false);
  assert.equal(lat.presenceToken, "idle");
});

test("grounded live HUD can be ok without licensing digits", () => {
  const lat = composeHonestyLattice({
    boardHonesty: 2,
    presenceDensity: 2,
    lastGoodTemptation: 0.1,
    groundedNoul: 0.9,
    coupling: 0.4,
  });
  assert.equal(lat.honestyBand, "ok");
  assert.equal(lat.licensesDigits, false);
  assert.equal(lat.presenceToken, "join");
});

test("parseNoulHealth fail-closes when disabled", () => {
  const p = parseNoulHealth({ enabled: false });
  assert.equal(p.enabled, false);
  assert.equal(p.honestyBand, "void");
  assert.equal(p.licensesDigits, false);
});

test("parseNoulHealth reads Deck /health noul stats", () => {
  const p = parseNoulHealth({
    noul: {
      enabled: true,
      honesty_band: "ident",
      presence_token: "idle",
      ident_now: true,
      licenses_digits: true,
      hud_kind: "select_plate",
      board_speech: "vlm_ungrounded",
    },
  });
  assert.equal(p.enabled, true);
  assert.equal(p.honestyBand, "ident");
  assert.equal(p.hudKind, "select_plate");
  assert.equal(p.licensesDigits, false);
  assert.match(p.gamerLine, /blank|stale/i);
});

test("gamer honesty copy never says clutch", () => {
  const c = gamerHonestyCopy({ enabled: true, honestyBand: "ok", presenceToken: "dense" });
  assert.equal(c.line, "");
  assert.doesNotMatch(c.presence, /clutch|highlight/i);
});
