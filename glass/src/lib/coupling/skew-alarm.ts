/** Operator skew — HID clock vs HDMI clock. Never interpolates HID. Never auto-cuts. */

export type SkewState = "ok" | "warn" | "alarm";

export function skewState(args: {
  hidClockNs: number;
  hdmiClockNs: number;
  frameSeqGap: number;
  ageS: number;
}): SkewState {
  const hid = Number(args.hidClockNs) || 0;
  const hdmi = Number(args.hdmiClockNs) || 0;
  const dtMs = Math.abs(hid - hdmi) / 1e6;
  const age = Number(args.ageS) || 0;
  const gap = Math.abs(Number(args.frameSeqGap) || 0);
  if (dtMs > 120 || age > 2 || gap > 30) return "alarm";
  if (dtMs > 60 || age > 1 || gap > 15) return "warn";
  return "ok";
}
