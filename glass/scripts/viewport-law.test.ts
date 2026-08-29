import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const GLASS_ROOT = join(import.meta.dirname, "..");

test("viewport law: styles.css enforces overflow hidden on html/body/#root", () => {
  const stylesPath = join(GLASS_ROOT, "src/styles.css");
  const styles = readFileSync(stylesPath, "utf-8");

  // html, body, #root must have overflow: hidden
  const htmlBodyRootBlock = /html,\s*body,\s*#root\s*\{[^}]*\}/s.exec(styles);
  assert.ok(htmlBodyRootBlock, "html, body, #root block must exist in styles.css");

  const block = htmlBodyRootBlock[0];
  assert.ok(block.includes("overflow: hidden"), "html, body, #root must have overflow: hidden");
  assert.ok(
    block.includes("height: 100dvh"),
    "html, body, #root must have height: 100dvh for viewport law",
  );
});

test("viewport law: theater-page.tsx must not have overflow-y: auto on main", () => {
  const theaterPagePath = join(GLASS_ROOT, "src/components/theater/theater-page.tsx");
  const theaterPage = readFileSync(theaterPagePath, "utf-8");

  // Main element must not have overflow-y-auto or min-h-dvh (scrolling document pattern)
  assert.ok(
    !theaterPage.includes("overflow-y-auto"),
    "theater-page.tsx must not contain overflow-y-auto (this creates a scrolling document)",
  );
  assert.ok(
    !theaterPage.includes("min-h-dvh"),
    "theater-page.tsx must not use min-h-dvh on main (use h-dvh instead)",
  );

  // Main should be a flex column with overflow hidden
  assert.ok(
    theaterPage.includes("h-dvh"),
    "theater-page.tsx main should use h-dvh for viewport HUD",
  );
  assert.ok(
    theaterPage.includes("overflow-hidden"),
    "theater-page.tsx main should have overflow-hidden",
  );
});

test("viewport law: LIVE rail mounts SituationCard then ClutchFeed", () => {
  const theaterPagePath = join(GLASS_ROOT, "src/components/theater/theater-page.tsx");
  const theaterPage = readFileSync(theaterPagePath, "utf-8");
  const sit = theaterPage.indexOf("<SituationCard");
  const clutch = theaterPage.indexOf("<ClutchFeed");
  assert.ok(sit > -1, "SituationCard (scorebug plate) must be on the LIVE rail");
  assert.ok(clutch > -1, "ClutchFeed must stay on the LIVE rail");
  assert.ok(sit < clutch, "SituationCard must sit above ClutchFeed");
  assert.ok(
    !theaterPage.includes("<AgentRail"),
    "Receipt / AgentRail stays out of the LIVE rail",
  );
});

test("viewport law: theater-page.tsx first viewport must be the HDMI stage", () => {
  const theaterPagePath = join(GLASS_ROOT, "src/components/theater/theater-page.tsx");
  const theaterPage = readFileSync(theaterPagePath, "utf-8");

  // CommandBar should come before HdmiStage
  const commandBarIndex = theaterPage.indexOf("<CommandBar");
  const hdmiStageIndex = theaterPage.indexOf("<HdmiStage");

  assert.ok(commandBarIndex > -1, "CommandBar must exist");
  assert.ok(hdmiStageIndex > -1, "HdmiStage must exist");
  assert.ok(
    commandBarIndex < hdmiStageIndex,
    "CommandBar must come before HdmiStage (command bar first, then picture)",
  );

  // No grid layout that pushes cards above or beside the stage
  assert.ok(
    !theaterPage.includes("grid-cols"),
    "theater-page.tsx must not use grid layout (Observatory is flex column: command bar, stage, no side cards)",
  );
});

test("viewport law: intelligence-chamber.tsx internal scroll only", () => {
  const chamberPath = join(GLASS_ROOT, "src/components/theater/intelligence-chamber.tsx");
  const chamber = readFileSync(chamberPath, "utf-8");

  // Chamber drawer should have internal overflow-y: auto
  assert.ok(
    chamber.includes("overflow-y-auto"),
    "intelligence-chamber drawer content must have internal overflow-y-auto",
  );

  // Chamber should be fixed positioned (not in main flow)
  assert.ok(
    chamber.includes("fixed"),
    "intelligence-chamber should be position fixed (drawer, not page flow)",
  );
});

test("fail-closed copy law: unlocked strip must show □–□ not 0-0", () => {
  const lockbugPath = join(GLASS_ROOT, "src/components/theater/lockbug-strip.tsx");
  const lockbug = readFileSync(lockbugPath, "utf-8");

  // Unlocked score must be □–□ (boxes), never 0-0 or --
  assert.ok(lockbug.includes("□–□"), "lockbug-strip must use □–□ for unlocked score (fail-closed)");
  assert.ok(!lockbug.includes('"0-0"'), "lockbug-strip must never show 0-0 (fake score)");
  assert.ok(!lockbug.includes('"--"'), "lockbug-strip must never show -- (empty dash)");

  // Unlocked down/distance must be — & —
  assert.ok(lockbug.includes("— & —"), "lockbug-strip must use — & — for unlocked down/distance");
});

test("copy leak prevention: observatory-hud must not use situationText", () => {
  const observatoryHudPath = join(GLASS_ROOT, "src/components/theater/observatory-hud.tsx");
  const observatoryHud = readFileSync(observatoryHudPath, "utf-8");

  // ObservatoryHUD must not compute situationText from widgetsOk + situation/boardLine
  assert.ok(
    !observatoryHud.includes("situationText"),
    "observatory-hud must not use situationText (copy leak: widgetsOk + situation/boardLine can show local_hud junk)",
  );
  assert.ok(
    !observatoryHud.includes("situation ||"),
    "observatory-hud must not read situation (unlicensed copy leak)",
  );
  assert.ok(
    !observatoryHud.includes("boardLine"),
    "observatory-hud must not read boardLine (unlicensed copy leak)",
  );

  // LockbugStrip is the licensed copy source
  assert.ok(
    observatoryHud.includes("LockbugStrip"),
    "observatory-hud must use LockbugStrip (the fail-closed licensed copy)",
  );
});

test("observatory variant must not mount LensOverlay", () => {
  const hdmiStagePath = join(GLASS_ROOT, "src/components/theater/hdmi-stage.tsx");
  const hdmiStage = readFileSync(hdmiStagePath, "utf-8");

  // LensOverlay should be gated: not mounted when variant === "observatory"
  const lensOverlayLine = hdmiStage.match(/\{!replaySrc.*?<LensOverlay.*?\}/s);
  assert.ok(lensOverlayLine, "HdmiStage must conditionally mount LensOverlay");
  assert.ok(
    lensOverlayLine[0].includes('variant !== "observatory"'),
    'HdmiStage must NOT mount LensOverlay when variant === "observatory" (ObservatoryHUD owns stage chrome)',
  );
});

