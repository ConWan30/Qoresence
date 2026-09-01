import { APERTURE_IDENT_SRC } from "@/lib/coupling/aperture-ident";

/** HDMI Q on void. HOLD chrome only. No digits, no pad, no last frame. */
export function ApertureIdent() {
  return (
    <div
      data-aperture-ident="on"
      className="pointer-events-none absolute inset-0 z-10 grid place-items-center bg-bg"
    >
      <img
        src={APERTURE_IDENT_SRC}
        alt=""
        width={320}
        height={320}
        className="max-h-[42%] w-auto object-contain"
      />
      <span className="absolute bottom-3 left-3 font-mono text-[10px] tracking-[0.2em] text-live uppercase">
        Aperture Ident
      </span>
      <span className="absolute right-3 bottom-3 font-mono text-[10px] tracking-[0.2em] text-muted-foreground uppercase">
        HOLD · board not licensed
      </span>
    </div>
  );
}
