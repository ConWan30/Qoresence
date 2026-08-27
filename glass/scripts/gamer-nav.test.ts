import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const GLASS_ROOT = join(import.meta.dirname, "..");

test("gamer nav: Theater and Session show only Theater + Session in glass-nav", () => {
  const commandBarPath = join(GLASS_ROOT, "src/components/theater/command-bar.tsx");
  const commandBar = readFileSync(commandBarPath, "utf-8");

  // GAMER_GLASSES array must exist with only Theater and Session
  assert.ok(
    commandBar.includes("GAMER_GLASSES"),
    "command-bar.tsx must define GAMER_GLASSES array for gamer routes",
  );

  // GAMER_GLASSES must contain exactly Theater and Session
  const gamerGlassesMatch = /const GAMER_GLASSES = \[([\s\S]*?)\] as const;/.exec(commandBar);
  assert.ok(gamerGlassesMatch, "GAMER_GLASSES array must be defined");

  const gamerGlassesContent = gamerGlassesMatch[1];
  assert.ok(
    gamerGlassesContent.includes('label: "Theater"'),
    'GAMER_GLASSES must include Theater',
  );
  assert.ok(
    gamerGlassesContent.includes('label: "Session"'),
    'GAMER_GLASSES must include Session',
  );

  // GAMER_GLASSES must not contain Home, CIVIF, Lens, Foundry, or Mobile
  assert.ok(
    !gamerGlassesContent.includes('label: "Home"'),
    'GAMER_GLASSES must not include Home',
  );
  assert.ok(
    !gamerGlassesContent.includes('label: "CIVIF"'),
    'GAMER_GLASSES must not include CIVIF',
  );
  assert.ok(
    !gamerGlassesContent.includes('label: "Lens"'),
    'GAMER_GLASSES must not include Lens',
  );
  assert.ok(
    !gamerGlassesContent.includes('label: "Foundry"'),
    'GAMER_GLASSES must not include Foundry',
  );
  assert.ok(
    !gamerGlassesContent.includes('label: "Mobile"'),
    'GAMER_GLASSES must not include Mobile',
  );

  // GAMER_GLASSES should have exactly 2 items (Theater + Session)
  const itemCount = (gamerGlassesContent.match(/href:/g) || []).length;
  assert.strictEqual(itemCount, 2, "GAMER_GLASSES must have exactly 2 items");
});

test("gamer nav: isGamerRoute flag identifies Theater and Session", () => {
  const commandBarPath = join(GLASS_ROOT, "src/components/theater/command-bar.tsx");
  const commandBar = readFileSync(commandBarPath, "utf-8");

  // isGamerRoute must be defined
  assert.ok(
    commandBar.includes("isGamerRoute"),
    "command-bar.tsx must define isGamerRoute flag",
  );

  // isGamerRoute must check for /deck.html and /session.html
  const isGamerRouteMatch = /const isGamerRoute = (.+?);/.exec(commandBar);
  assert.ok(isGamerRouteMatch, "isGamerRoute assignment must exist");

  const isGamerRouteDef = isGamerRouteMatch[1];
  assert.ok(
    isGamerRouteDef.includes('"/deck.html"'),
    'isGamerRoute must check for "/deck.html" (Theater)',
  );
  assert.ok(
    isGamerRouteDef.includes('"/session.html"'),
    'isGamerRoute must check for "/session.html" (Session)',
  );
});

test("gamer nav: glass-nav uses GAMER_GLASSES when isGamerRoute", () => {
  const commandBarPath = join(GLASS_ROOT, "src/components/theater/command-bar.tsx");
  const commandBar = readFileSync(commandBarPath, "utf-8");

  // Nav should conditionally render GAMER_GLASSES or GLASSES
  assert.ok(
    commandBar.includes("isGamerRoute ? GAMER_GLASSES : GLASSES"),
    "glass-nav must conditionally use GAMER_GLASSES for gamer routes (Theater/Session)",
  );
});

test("gamer nav: GLASSES array unchanged (all routes still valid)", () => {
  const commandBarPath = join(GLASS_ROOT, "src/components/theater/command-bar.tsx");
  const commandBar = readFileSync(commandBarPath, "utf-8");

  // Full GLASSES array must still exist with all routes
  const glassesMatch = /const GLASSES = \[([\s\S]*?)\] as const;\s*\nconst GAMER_GLASSES/.exec(commandBar);
  assert.ok(glassesMatch, "GLASSES array must still exist before GAMER_GLASSES");

  const glassesContent = glassesMatch[1];
  const allGlasses = ["Home", "Theater", "Session", "CIVIF", "Lens", "Foundry", "Mobile"];

  for (const label of allGlasses) {
    assert.ok(
      glassesContent.includes(`label: "${label}"`),
      `GLASSES must still include ${label} (routes not deleted)`,
    );
  }
});
