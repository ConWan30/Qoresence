import { useId } from "react";
import { cn } from "@/lib/utils";

const PINS = [46.2, 49.4, 52.6, 55.8, 59.0, 62.2, 65.4, 68.6, 71.8];
const TURNS = [0, 60, 120, 180, 240, 300];

/** Aperture iris — the HDMI-Q logo as live chrome (same drawing as the Pages
 *  read stage). Opens only on a confirmed read; closes to dark when unsure.
 *  Motion is transform-only (blades slide + turn); reduced-motion = settled. */
export function ApertureIris({
  open,
  className,
  title,
}: {
  open: boolean;
  className?: string;
  title?: string;
}) {
  const clip = `q-iris-clip-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <span
      className={cn("q-iris", open && "is-open", className)}
      data-iris={open ? "open" : "closed"}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <svg viewBox="0 0 120 120" focusable="false">
        <defs>
          <clipPath id={clip}>
            <circle cx="60" cy="60" r="45" />
          </clipPath>
        </defs>
        <g clipPath={`url(#${clip})`}>
          <rect width="120" height="120" className="well" />
          <path className="port" d="M39.5 51.5h41v8.5l-6.5 7h-28l-6.5-7z" />
          <path className="port-line" d="M45 56h30" />
          {PINS.map((x) => (
            <rect key={x} className="pin" x={x} y="60.2" width="1.7" height="2.6" />
          ))}
          <g className="blades">
            {TURNS.map((r) => (
              <g key={`b${r}`} transform={`rotate(${r} 60 60)`}>
                <path className="blade" d="M76 70 L4 6 L80 -24 Z" />
              </g>
            ))}
            {TURNS.map((r) => (
              <g key={`e${r}`} transform={`rotate(${r} 60 60)`}>
                <path className="blade blade-edge" d="M71 49 L16 9" />
              </g>
            ))}
          </g>
        </g>
        <circle className="ring-glow" cx="60" cy="60" r="47" />
        <circle className="ring" cx="60" cy="60" r="47" />
        <path className="tick" d="M60 3v12" />
      </svg>
    </span>
  );
}
