import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const GLASS_ROOT = join(import.meta.dirname, "..");

test("session theater inner tabs include pack without a new gamer glass", () => {
  const theater = readFileSync(join(GLASS_ROOT, "src/components/session/session-theater.tsx"), "utf-8");
  assert.ok(theater.includes('"pack"'), "SessionTheater must add inner tab pack");
  assert.ok(theater.includes("PresencePackBay"), "SessionTheater must render PresencePackBay");

  const commandBar = readFileSync(join(GLASS_ROOT, "src/components/theater/command-bar.tsx"), "utf-8");
  const gamerGlassesMatch = /const GAMER_GLASSES = \[([\s\S]*?)\] as const;/.exec(commandBar);
  assert.ok(gamerGlassesMatch, "GAMER_GLASSES array must be defined");
  const itemCount = (gamerGlassesMatch[1].match(/href:/g) || []).length;
  assert.strictEqual(itemCount, 2, "GAMER_GLASSES must stay Theater + Session");
  assert.ok(!gamerGlassesMatch[1].includes('label: "Pack"'), "Pack is not a top-level gamer glass");
});
