import assert from "node:assert/strict";
import test from "node:test";
import { vetoQsLine } from "../src/lib/coupling/quicksilver.server.ts";

test("fast path cannot invent a scoreline", () => {
  assert.equal(vetoQsLine("Huge 21-14 in the red zone.", "fast"), "");
  assert.ok(vetoQsLine("Red-zone energy spike — something's cooking.", "fast"));
});

test("confirm path may keep digits", () => {
  assert.match(vetoQsLine("Score update: 21-14", "confirm"), /21-14/);
});

test("THROW is forbidden", () => {
  assert.equal(vetoQsLine("THROW — he launched it.", "fast"), "");
});
