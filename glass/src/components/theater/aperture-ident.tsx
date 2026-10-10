import { useTheater } from "@/lib/coupling/store";
import { ApertureIris } from "./aperture-iris";

/** Honest empty frame: the iris closed on a blank well. No digits, no pad, no
 *  last frame, no spinner. Says why it is dark when /health says so. */
export function ApertureIdent() {
  const reason = useTheater((s) => s.meter.paintReason);
  const at = useTheater((s) => s.meter.at);
  const why = reason && reason !== "ok" ? reason.replace(/_/g, " ") : at ? "picture not licensed" : "waiting for deck";
  return (
    <div data-aperture-ident="on" className="aperture-ident pointer-events-none absolute inset-0 z-10">
      <span className="aperture-ident-safe" aria-hidden />
      <div className="aperture-ident-core">
        <ApertureIris open={false} className="aperture-ident-iris" />
        <p className="aperture-ident-title">Dark</p>
        <p className="aperture-ident-why">No picture shown · {why}</p>
      </div>
      <span className="aperture-ident-corner is-left">HDMI in · blank frame</span>
      <span className="aperture-ident-corner is-right">Goes dark instead of lying</span>
    </div>
  );
}
