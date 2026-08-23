import assert from "node:assert/strict";
import { test } from "node:test";
import { parseStemProgram } from "./stem.ts";

test("parses bus stem_program", () => {
  const p = parseStemProgram({
    type: "stem_program",
    payload: { mode: "prime", why: "Red zone", arm_hot: true },
  });
  assert.equal(p?.mode, "prime");
  assert.equal(p?.why, "Red zone");
  assert.equal(p?.armHot, true);
});

test("rejects unknown mode", () => {
  assert.equal(parseStemProgram({ type: "stem_program", payload: { mode: "scene2" } }), null);
});
