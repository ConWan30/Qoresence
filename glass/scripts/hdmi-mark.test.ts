import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const GLASS_ROOT = join(import.meta.dirname, "..");

test("Sight Glass command bar uses HDMI Q ident, not letter Q", () => {
  const bar = readFileSync(join(GLASS_ROOT, "src/components/theater/command-bar.tsx"), "utf-8");
  assert.ok(bar.includes("HdmiMark"), "command-bar must mount HdmiMark");
  assert.ok(!bar.includes("holo-mark"), "letter-Q holo-mark is retired on Sight Glass");
  const mark = readFileSync(join(GLASS_ROOT, "src/components/theater/hdmi-mark.tsx"), "utf-8");
  assert.ok(mark.includes("APERTURE_IDENT_SRC"), "HdmiMark uses the public Aperture Ident asset");
  assert.ok(mark.includes("Qoresence HDMI"), "HdmiMark alt names the HDMI logo");
});

test("dark theater feeds plane dim and live paint into the HDMI Q ident", () => {
  const stage = readFileSync(join(GLASS_ROOT, "src/components/theater/hdmi-stage.tsx"), "utf-8");
  const call = stage.slice(stage.indexOf("apertureIdentOn("), stage.indexOf("apertureIdentOn(") + 280);
  assert.ok(call.includes("livePaint"), "HdmiStage must pass livePaint into apertureIdentOn");
  assert.ok(call.includes("planeDim"), "HdmiStage must pass planeDim into apertureIdentOn");
  assert.ok(stage.includes("<ApertureIdent"), "dark stage mounts the HDMI Q ident");
});

test("gamer dock is on Theater and does not sit inside HdmiStage", () => {
  const page = readFileSync(join(GLASS_ROOT, "src/components/theater/theater-page.tsx"), "utf-8");
  assert.ok(page.includes("<GamerDock"), "Theater mounts GamerDock");
  const dock = readFileSync(join(GLASS_ROOT, "src/components/theater/gamer-dock.tsx"), "utf-8");
  assert.ok(dock.includes("data-gamer-board"), "dock exposes board lock/blank");
  assert.ok(dock.includes("data-gamer-pad"), "dock exposes pad join");
  const stage = readFileSync(join(GLASS_ROOT, "src/components/theater/hdmi-stage.tsx"), "utf-8");
  assert.ok(!stage.includes("GamerDock"), "gamer dock stays off the picture");
});
