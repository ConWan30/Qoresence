import assert from "node:assert/strict";
import { test } from "node:test";
import {
  confBand,
  digitsPaintBlocked,
  EMPTY_HONESTY,
  parseHonestyHealth,
  silenceScorePair,
  tensionPlinth,
} from "./honesty-health.ts";

test("missing health fail-closes dark and never licenses digits", () => {
  for (const raw of [null, undefined, {}, { ticket_glass: {} }, "nope", 0]) {
    const h = parseHonestyHealth(raw);
    assert.equal(h.state, "dark");
    assert.equal(h.enabled, false);
    assert.equal(h.licensesDigits, false);
    assert.equal(h.paintBlocked, false);
    assert.equal(h.glyphs.length, 6);
    assert.equal(h.glyphs[0].id, "lock");
    assert.equal(h.glyphs[5].id, "haptic");
    assert.ok(h.glyphs.every((g) => g.conf === "ghost"));
  }
});

test("disabled packs stay dark even if glyphs look live", () => {
  const h = parseHonestyHealth({
    ticket_glass: { enabled: false, glyphs: { lock: "open", tension: 3, cut: "on" }, licenses_digits: true },
    sync_glass: { enabled: false, glyphs: { bind: "ok", lag: "ok", haptic: "on" } },
  });
  assert.equal(h.state, "dark");
  assert.equal(h.enabled, false);
  assert.equal(h.licensesDigits, false);
});

test("licenses_digits true on the wire is still false", () => {
  const h = parseHonestyHealth({
    ticket_glass: {
      enabled: true,
      licenses_digits: true,
      glyphs: { lock: "open", tension: 1, cut: "off" },
    },
    sync_glass: { enabled: true, licenses_digits: true, glyphs: { bind: "ok", lag: "ok", haptic: "on" } },
  });
  assert.equal(h.enabled, true);
  assert.equal(h.state, "live");
  assert.equal(h.licensesDigits, false);
  assert.equal(h.licensesDigits, EMPTY_HONESTY.licensesDigits);
});

test("never paints score pairs into glyphs", () => {
  const h = parseHonestyHealth({
    ticket_glass: {
      enabled: true,
      glyphs: { lock: "21-14", tension: "7-3", cut: "28-24" },
      home_score: 21,
      away_score: 14,
    },
    sync_glass: { enabled: true, glyphs: { bind: "14-7", lag: "3-0", haptic: "21–17" } },
  });
  assert.equal(h.licensesDigits, false);
  for (const g of h.glyphs) {
    assert.doesNotMatch(g.value, /\d{1,2}\s*[-–—]\s*\d{1,2}/);
    assert.doesNotMatch(g.title, /\d{1,2}\s*[-–—]\s*\d{1,2}/);
  }
});

test("board_paint_block high-conf veto is paintBlocked", () => {
  const h = parseHonestyHealth({
    ticket_glass: {
      enabled: true,
      glyphs: { lock: "unknown", tension: 0, cut: "off" },
      board_paint_block: 0.91,
      paint_block: "block",
    },
  });
  assert.equal(h.paintBlocked, true);
  assert.equal(h.licensesDigits, false);
});

test("lock=blocked is paintBlocked even without noul", () => {
  const h = parseHonestyHealth({
    ticket_glass: { enabled: true, glyphs: { lock: "blocked", tension: 2, cut: "off" } },
  });
  assert.equal(h.lockBlocked, true);
  assert.equal(h.paintBlocked, true);
});

test("conf bands: solid / dim / ghost", () => {
  assert.equal(confBand(0.7), "solid");
  assert.equal(confBand(1), "solid");
  assert.equal(confBand(0.4), "dim");
  assert.equal(confBand(0.69), "dim");
  assert.equal(confBand(0.39), "ghost");
  assert.equal(confBand(null), "ghost");
  assert.equal(confBand(undefined), "ghost");
});

test("bind_healthy noul drives bind opacity", () => {
  const solid = parseHonestyHealth({
    sync_glass: { enabled: true, glyphs: { bind: "ok", lag: "ok", haptic: "on" }, bind_healthy: 0.88 },
  });
  const dim = parseHonestyHealth({
    sync_glass: { enabled: true, glyphs: { bind: "soft", lag: "unknown", haptic: "unknown" }, bind_healthy: 0.5 },
  });
  const ghost = parseHonestyHealth({
    sync_glass: { enabled: true, glyphs: { bind: "off", lag: "unknown", haptic: "off" }, bind_healthy: 0.1 },
  });
  assert.equal(solid.glyphs.find((g) => g.id === "bind")?.conf, "solid");
  assert.equal(dim.glyphs.find((g) => g.id === "bind")?.conf, "dim");
  assert.equal(ghost.glyphs.find((g) => g.id === "bind")?.conf, "ghost");
});

test("tooltip is enum string, not prose", () => {
  const h = parseHonestyHealth({
    ticket_glass: { enabled: true, glyphs: { lock: "blocked", tension: 3, cut: "on" } },
    sync_glass: { enabled: true, glyphs: { bind: "ok", lag: "capture_starve", haptic: "on" } },
  });
  assert.equal(h.glyphs.find((g) => g.id === "lag")?.title, "lag=capture_starve");
  assert.equal(h.glyphs.find((g) => g.id === "lock")?.title, "lock=blocked");
  assert.doesNotMatch(h.glyphs.map((g) => g.title).join(" "), /would|should|because/i);
});

test("digitsPaintBlocked ORs lock and board_paint_block", () => {
  assert.equal(digitsPaintBlocked({}), false);
  assert.equal(digitsPaintBlocked({ glyphs: { lock: "open" } }), false);
  assert.equal(digitsPaintBlocked({ glyphs: { lock: "blocked" } }), true);
  assert.equal(digitsPaintBlocked({ board_paint_block: 0.7 }), true);
  assert.equal(digitsPaintBlocked({ board_paint_block: 0.2 }), false);
  assert.equal(digitsPaintBlocked({ paint_block: "block" }), true);
  assert.equal(digitsPaintBlocked({ ticket_glass: { glyphs: { lock: "blocked" } } }), true);
  // Licensed paint hold: open lock wins over thrashing TypeSafe noul.
  assert.equal(
    digitsPaintBlocked({ glyphs: { lock: "open" }, board_paint_block: 0.91, paint_block: "watch" }),
    false,
  );
});

test("licensed open lock ignores high board_paint_block noul in parseHonestyHealth", () => {
  const h = parseHonestyHealth({
    ticket_glass: {
      enabled: true,
      glyphs: { lock: "open", tension: 0, cut: "off" },
      board_paint_block: 0.91,
      paint_block: "watch",
    },
  });
  assert.equal(h.lockBlocked, false);
  assert.equal(h.paintBlocked, false);
  assert.equal(h.licensesDigits, false);
});

test("tensionPlinth maps 0 / 1-2 / 3", () => {
  assert.equal(tensionPlinth(0), "off");
  assert.equal(tensionPlinth(1), "near");
  assert.equal(tensionPlinth(2), "near");
  assert.equal(tensionPlinth(3), "hot");
  assert.equal(tensionPlinth(0, "on"), "hot");
});

test("silenceScorePair blanks pairs only when blocked", () => {
  assert.equal(silenceScorePair("CLIMAX · 21-14", false), "CLIMAX · 21-14");
  assert.equal(silenceScorePair("CLIMAX · 21-14", true), "CLIMAX · □–□");
  assert.equal(silenceScorePair("fast chat", true), "fast chat");
});
