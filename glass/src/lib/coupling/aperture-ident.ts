/** Aperture Ident — HDMI Q on void.

The ident covers the stage when no LIVE JPEG has arrived, and when
Dark Theater is up: plane dim or live paint off (no frame, blank,
title-presence not play). Seq skew ghosts widgets only; a current
JPEG stays. An HDMI menu/stale label alone is not dark. Replay owns
the stage; ident stays off.
*/
export const APERTURE_IDENT = "apertureIdent";
export const APERTURE_IDENT_SRC = "/qoresence-logo.png";

export type IdentLatch = {
  jpgOk: boolean;
  replay?: boolean;
  hdmi?: "live" | "menu" | "stale";
  sameSeq?: boolean;
  /** False when LIVE paint is off (no frame, blank, not play). */
  livePaint?: boolean;
  /** True when title-presence is not play (menu, pause, witness dim). */
  planeDim?: boolean;
};

export function apertureIdentOn(latch: IdentLatch): boolean {
  if (latch.replay) return false;
  if (!latch.jpgOk) return true;
  if (latch.planeDim) return true;
  if (latch.livePaint === false) return true;
  return false;
}
