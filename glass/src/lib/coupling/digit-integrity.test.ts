import assert from "node:assert/strict";
import { test } from "node:test";
import { digitVoidReason, freshnessBand } from "./digit-integrity.ts";
import { CONFIRM_DIGIT_MAX_AGE_NS } from "./board.ts";

const licensed = {
  confirmTicketId: "c-1",
  scoreVlmLocked: true,
  path: "confirm",
  ticketCropHash: "crop-a",
  liveCropHash: "crop-a",
  sameSeq: true as boolean | null,
  ticketClockNs: 1_000,
  liveClockNs: 2_000,
};

test("no ticket is digit-void even with leftover last-good scores", () => {
  const reason = digitVoidReason({
    ...licensed,
    confirmTicketId: "",
  });
  assert.equal(reason, "no_ticket");
});

test("ticket without VLM lock is vlm_unlocked", () => {
  assert.equal(digitVoidReason({ ...licensed, scoreVlmLocked: false }), "vlm_unlocked");
});

test("path=fast never licenses digits", () => {
  assert.equal(digitVoidReason({ ...licensed, path: "fast" }), "path_fast");
});

test("clock older than confirm window is ticket_stale", () => {
  const reason = digitVoidReason({
    ...licensed,
    ticketClockNs: 1,
    liveClockNs: 1 + CONFIRM_DIGIT_MAX_AGE_NS + 1,
  });
  assert.equal(reason, "ticket_stale");
  assert.equal(freshnessBand(CONFIRM_DIGIT_MAX_AGE_NS + 1), "ident");
});

test("crop mismatch blanks", () => {
  assert.equal(digitVoidReason({ ...licensed, liveCropHash: "crop-b" }), "crop_mismatch");
});

test("seq skew blanks", () => {
  assert.equal(digitVoidReason({ ...licensed, sameSeq: false }), "seq_skew");
});

test("VLM abstain blanks", () => {
  assert.equal(digitVoidReason({ ...licensed, vlmAbstain: true }), "vlm_abstain");
});

test("confirm + lock + fresh is licensed and ok band", () => {
  assert.equal(digitVoidReason(licensed), "licensed");
  assert.equal(freshnessBand(0), "ok");
  assert.equal(freshnessBand(CONFIRM_DIGIT_MAX_AGE_NS * 0.5), "ok");
  assert.equal(freshnessBand(CONFIRM_DIGIT_MAX_AGE_NS * 0.7), "amber");
  assert.equal(freshnessBand(CONFIRM_DIGIT_MAX_AGE_NS * 0.9), "red");
});

test("freshnessBand ident over max", () => {
  assert.equal(freshnessBand(CONFIRM_DIGIT_MAX_AGE_NS), "red");
  assert.equal(freshnessBand(CONFIRM_DIGIT_MAX_AGE_NS + 1), "ident");
});
