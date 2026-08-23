import assert from "node:assert/strict";
import { test } from "node:test";
import { actuatorChips, parseActuatorReceipts } from "./actuators.ts";

test("parses health actuator receipts in registry order", () => {
  const rows = parseActuatorReceipts({
    receipts: [
      { actuator: "arm", kind: "hold", text: "arm hold", path: "fast" },
      { actuator: "aperture", kind: "live", text: "aperture live", path: "fast" },
      { actuator: "bind", kind: "open", text: "pll open", path: "fast" },
      { actuator: "license", kind: "veto", text: "license veto", path: "confirm" },
    ],
  });
  const chips = actuatorChips(rows);
  assert.deepEqual(
    chips.map((c) => c.actuator),
    ["aperture", "bind", "license", "arm"],
  );
  assert.equal(chips[0].kind, "live");
  assert.equal(chips[2].kind, "veto");
});

test("empty when no receipts", () => {
  assert.deepEqual(actuatorChips(parseActuatorReceipts({})), []);
});
