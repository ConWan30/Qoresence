import assert from "node:assert/strict";
import { test } from "node:test";
import { visibleAgentReceipts, type AgentReceipt } from "./agents.ts";

function rec(partial: Partial<AgentReceipt> & Pick<AgentReceipt, "role">): AgentReceipt {
  return {
    action: "quiet",
    text: "",
    model: "rules",
    policyOk: true,
    reason: "society wait",
    ...partial,
  };
}

test("hides persona rows; keeps last real receipt", () => {
  const rows = visibleAgentReceipts([
    rec({ role: "drive_coach", action: "note", text: "Society armed", reason: "agent society live" }),
    rec({ role: "clutchbot", action: "chat", text: "Pressure building", reason: "a2a soft commit" }),
    rec({ role: "ghost_editor", action: "quiet", reason: "society wait" }),
  ]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].role, "clutchbot");
  assert.equal(rows[0].text, "Pressure building");
});

test("empty when every role is quiet", () => {
  const rows = visibleAgentReceipts([
    rec({ role: "drive_coach" }),
    rec({ role: "clutchbot" }),
  ]);
  assert.equal(rows.length, 0);
});
