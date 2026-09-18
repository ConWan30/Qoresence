import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

function load(rel: string): string {
  return readFileSync(join(ROOT, rel), "utf8");
}

test("HonestyStrip sits under CommandBar, never inside HdmiStage", () => {
  const page = load("src/components/theater/theater-page.tsx");
  const stage = load("src/components/theater/hdmi-stage.tsx");
  const hud = load("src/components/theater/observatory-hud.tsx");
  assert.match(page, /<CommandBar\s*\/>/);
  assert.match(page, /<HonestyStrip\s*\/>/);
  const cmd = page.indexOf("<CommandBar");
  const strip = page.indexOf("<HonestyStrip");
  const hdmi = page.indexOf("<HdmiStage");
  assert.ok(cmd >= 0 && strip > cmd && hdmi > strip, "strip must sit between CommandBar and HdmiStage");
  assert.doesNotMatch(stage, /HonestyStrip/);
  assert.doesNotMatch(stage, /honesty-strip/);
  assert.doesNotMatch(hud, /HonestyStrip/);
  assert.doesNotMatch(hud, /HonestyLine/);
});

test("overlay does not mount the 6-glyph Honesty strip", () => {
  const overlayRoute = load("src/routes/overlay[.]html.tsx");
  const lens = load("src/components/theater/lens-overlay.tsx");
  assert.doesNotMatch(overlayRoute, /HonestyStrip/);
  assert.doesNotMatch(lens, /HonestyStrip/);
  assert.match(lens, /HonestyVoidChip/);
});

test("monitor polls /health and does not touch capture or JPEG", () => {
  const mon = load("src/lib/coupling/monitor.ts");
  assert.match(mon, /\/health/);
  assert.match(mon, /parseHonestyHealth/);
  assert.doesNotMatch(mon, /ensureCapture\s*\(/);
  assert.doesNotMatch(mon, /live\.jpg/);
  assert.doesNotMatch(mon, /createImageBitmap/);
  assert.doesNotMatch(mon, /VideoCapture/);
  const health = load("src/lib/coupling/honesty-health.ts");
  assert.doesNotMatch(health, /ensureCapture\s*\(/);
  assert.doesNotMatch(health, /live\.jpg/);
  assert.doesNotMatch(health, /from "\.\/hardware/);
});

test("no --x-glass flips in honesty UI", () => {
  const strip = load("src/components/theater/honesty-strip.tsx");
  const page = load("src/components/theater/theater-page.tsx");
  assert.doesNotMatch(strip, /x-glass|xGlass|--x-glass/);
  assert.doesNotMatch(page, /--x-glass/);
});

test("pickBoard consumers OR ticket_glass paint veto", () => {
  const board = load("src/lib/coupling/board.ts");
  assert.match(board, /digitsPaintBlocked/);
  const plane = load("src/lib/coupling/agent-plane.ts");
  assert.match(plane, /ticket_glass/);
});

test("OFF mode: iron chip only — no six ghost glyphs in strip source path", () => {
  const strip = load("src/components/theater/honesty-strip.tsx");
  const health = load("src/lib/coupling/honesty-health.ts");
  assert.match(strip, /data-honesty=\{state\}/);
  assert.match(strip, /data-honesty-iron/);
  assert.match(strip, /honesty-iron-chip/);
  assert.match(strip, /state === "off"/);
  assert.match(strip, /honesty-dark-tally/);
  assert.match(strip, /data-honesty-tally="dark"/);
  // OFF branch must not map six glyphs — iron chip only
  assert.match(strip, /state === "off"[\s\S]*?honesty-iron-chip/);
  assert.doesNotMatch(strip, /licensesDigits\s*=\s*true/);
  assert.match(health, /HonestyState = "off" \| "dark" \| "live"/);
  assert.match(health, /state: "off"/);
  assert.match(health, /licensesDigits: false/);
  assert.match(health, /glyphs: \[\]/);
});

test("LIVE crossfade uses 150ms / motion-quick on glyphs", () => {
  const css = load("src/styles.css");
  assert.match(css, /\.honesty-glyph[\s\S]*?transition:[\s\S]*?var\(--motion-quick\)/);
  assert.match(css, /\.honesty-iron-chip/);
  assert.match(css, /\.honesty-dark-tally/);
  assert.match(css, /\[data-honesty="off"\]/);
});

test("licenses_digits stays false forever in honesty health", () => {
  const health = load("src/lib/coupling/honesty-health.ts");
  assert.match(health, /licensesDigits: false/);
  assert.doesNotMatch(health, /licensesDigits:\s*true/);
  assert.doesNotMatch(health, /licensesDigits\s*=\s*true/);
});
