import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { couplingMeter } from "./coupling-meter.ts";

test("unbound when pll open or lag missing", () => {
  const a = couplingMeter({ lagMs: null, pllLock: true, sameSeq: true });
  assert.equal(a.label, "unbound");
  const b = couplingMeter({ lagMs: 16, pllLock: false, sameSeq: true });
  assert.equal(b.label, "unbound");
});

test("co-occurrence when pll lock and same seq", () => {
  const m = couplingMeter({ lagMs: 33, pllLock: true, sameSeq: true });
  assert.equal(m.label, "co-occurrence");
  assert.equal(m.skewMs, 33);
  assert.ok(m.bins.some((b) => b.ms === 33 && b.n >= 1));
});

test("copy never eligibility or lag-switch", () => {
  const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "coupling-meter.ts"), "utf8");
  assert.doesNotMatch(src, /cheat|eligib|human|lag switch/i);
});
