import { describe, expect, it } from "vitest";
import { downDistanceLabel } from "./board";

describe("phosphor-shell-s1", () => {
  it("downDistanceLabel unlocked when down null", () => {
    expect(downDistanceLabel(null, 7)).toBe("— & —");
  });
  it("downDistanceLabel locked ordinal", () => {
    expect(downDistanceLabel(3, 7)).toBe("3rd & 7");
    expect(downDistanceLabel(1, 10)).toBe("1st & 10");
  });
  it("fixture contract file exists", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const p = path.resolve(__dirname, "../../../fixtures/phosphor-shell-s1.json");
    expect(fs.existsSync(p)).toBe(true);
    const j = JSON.parse(fs.readFileSync(p, "utf8"));
    expect(j.contract.glanceGlyph.bits).toEqual(["F", "C", "L", "P"]);
    expect(j.contract.syncTrail.neverForceZero).toBe(true);
  });
});
