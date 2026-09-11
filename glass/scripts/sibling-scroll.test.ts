import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

test("studio/mobile use locked shell + inner overflow-y-auto scrollport", () => {
  const studio = readFileSync(join(ROOT, "src/routes/studio[.]html.tsx"), "utf8");
  const mobile = readFileSync(join(ROOT, "src/routes/mobile[.]html.tsx"), "utf8");
  assert.match(studio, /h-dvh min-h-0 flex-col overflow-hidden/);
  assert.match(studio, /overflow-y-auto/);
  assert.doesNotMatch(studio, /min-h-dvh/);
  assert.match(mobile, /h-dvh min-h-0 flex-col overflow-hidden/);
  assert.match(mobile, /overflow-y-auto/);
});

test("session theater scrollport has min-h-0", () => {
  const src = readFileSync(join(ROOT, "src/components/session/session-theater.tsx"), "utf8");
  assert.match(src, /flex min-h-0 flex-1 flex-col overflow-hidden/);
  assert.match(src, /min-h-0 w-full max-w-\[88rem\].*overflow-y-auto/);
});

test("Theater LIVE stage stays overflow-hidden locked shell", () => {
  const src = readFileSync(join(ROOT, "src/components/theater/theater-page.tsx"), "utf8");
  assert.match(src, /flex h-dvh flex-col overflow-hidden/);
  assert.match(src, /overflow-hidden/);
});
