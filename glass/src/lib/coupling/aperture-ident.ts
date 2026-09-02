/** Aperture Ident — fail-closed picture.

HOLD ident on blank / seq-skew / non-play, or when JPEG has not arrived.
Never a last-good-frame freeze. Never digits. Never DualSense glyphs.
Fresh LIVE JPEG still wins: jpgOk + hdmi live + sameSeq.
planeDim / livePaint ghost widgets only — not an ident latch.
Replay owns the stage; ident stays off.
*/
export const APERTURE_IDENT = "apertureIdent";
export const APERTURE_IDENT_SRC = "/qoresence-logo.png";

export type IdentLatch = {
  jpgOk: boolean;
  replay?: boolean;
  hdmi?: "live" | "menu" | "stale";
  sameSeq?: boolean;
};

export function apertureIdentOn(latch: IdentLatch): boolean {
  if (latch.replay) return false;
  if (!latch.jpgOk) return true;
  if (latch.hdmi === "menu" || latch.hdmi === "stale") return true;
  if (latch.sameSeq === false) return true;
  return false;
}
