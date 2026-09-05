/** Null Digit Glass — why digits are blank. Inverse of last-good OCR hold. */

import {
  CONFIRM_DIGIT_MAX_AGE_NS,
  digitsLicensed,
  ticketFresh,
} from "./board.ts";

export type DigitVoidReason =
  | "no_ticket"
  | "vlm_unlocked"
  | "ticket_stale"
  | "crop_mismatch"
  | "seq_skew"
  | "path_fast"
  | "vlm_abstain"
  | "licensed";

export type FreshnessBand = "ok" | "amber" | "red" | "ident";

export function freshnessBand(ageNs: number, maxAgeNs: number = CONFIRM_DIGIT_MAX_AGE_NS): FreshnessBand {
  const age = Number(ageNs) || 0;
  const max = Math.max(1, Number(maxAgeNs) || CONFIRM_DIGIT_MAX_AGE_NS);
  if (age > max) return "ident";
  if (age > max * 0.8) return "red";
  if (age > max * 0.5) return "amber";
  return "ok";
}

export function digitVoidReason(args: {
  confirmTicketId: string;
  scoreVlmLocked: boolean;
  path: string;
  ticketCropHash: string;
  liveCropHash: string;
  sameSeq: boolean | null;
  ticketClockNs: number;
  liveClockNs: number;
  vlmAbstain?: boolean;
}): DigitVoidReason {
  if (String(args.path || "").toLowerCase() === "fast") return "path_fast";
  if (args.vlmAbstain) return "vlm_abstain";
  if (!String(args.confirmTicketId || "").trim()) return "no_ticket";
  if (!args.scoreVlmLocked) return "vlm_unlocked";
  const ticketCrop = String(args.ticketCropHash || "").trim();
  const liveCrop = String(args.liveCropHash || "").trim();
  if (liveCrop && ticketCrop && liveCrop !== ticketCrop) return "crop_mismatch";
  if (args.sameSeq === false) return "seq_skew";
  if (
    !ticketFresh({
      ticketCropHash: args.ticketCropHash,
      liveCropHash: args.liveCropHash,
      sameSeq: args.sameSeq,
      ticketClockNs: args.ticketClockNs,
      liveClockNs: args.liveClockNs,
    })
  ) {
    return "ticket_stale";
  }
  if (
    digitsLicensed({
      confirmTicketId: args.confirmTicketId,
      scoreVlmLocked: args.scoreVlmLocked,
      ticketCropHash: args.ticketCropHash,
      liveCropHash: args.liveCropHash,
      sameSeq: args.sameSeq,
      ticketClockNs: args.ticketClockNs,
      liveClockNs: args.liveClockNs,
    })
  ) {
    return "licensed";
  }
  return "ticket_stale";
}
