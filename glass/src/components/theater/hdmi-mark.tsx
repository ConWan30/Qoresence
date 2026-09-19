import { APERTURE_IDENT_SRC } from "@/lib/coupling/aperture-ident";
import { cn } from "@/lib/utils";

/** HDMI Q from the public Aperture Ident (same asset as GitHub Pages). */
export function HdmiMark({
  className,
  size = 32,
}: {
  className?: string;
  size?: number;
}) {
  return (
    <img
      src={APERTURE_IDENT_SRC}
      alt="Qoresence HDMI"
      width={size}
      height={size}
      className={cn("hdmi-mark object-contain", className)}
    />
  );
}
