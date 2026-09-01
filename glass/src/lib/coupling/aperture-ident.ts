/** Aperture Ident — fail-closed picture.

When Theater has no honest HDMI (no JPEG), paint the HDMI Q on void.
Never a last-good-frame freeze. Never digits. Never DualSense glyphs.
JPEG arriving wins — same law as hdmiPictureVisible.
Replay owns the stage; ident stays off.
*/
export const APERTURE_IDENT = "apertureIdent";
export const APERTURE_IDENT_SRC = "/qoresence-logo.png";

export function apertureIdentOn(jpgOk: boolean, replay = false): boolean {
  return !replay && !Boolean(jpgOk);
}
