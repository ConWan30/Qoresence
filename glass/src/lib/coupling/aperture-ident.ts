/** Aperture Ident — no capture yet.

The ident covers the stage only while a LIVE JPEG has not arrived.
Pause, menu, cutscene, and seq-skew ghost widgets. They do not cover
the HDMI picture. The JPEG pump drops jpgOk after a gap, so a frozen
last frame does not stay up. Replay owns the stage; ident stays off.
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
  return !latch.jpgOk;
}
