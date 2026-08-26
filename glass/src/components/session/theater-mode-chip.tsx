import { Link, useLocation } from "@tanstack/react-router";
import { cn } from "@/lib/utils";

/** Phosphor Shell §2 — Theater Mode Chip (HDMI | SESSION). */
export function TheaterModeChip() {
  const { pathname } = useLocation();
  const isHdmi = pathname === "/" || pathname === "/deck.html";
  const isSession = pathname === "/session.html" || pathname === "/civif.html";

  return (
    <div className="flex items-center gap-1.5 rounded-lg bg-surface/60 p-1 shadow-[var(--shadow-border)]">
      <Link
        to="/deck.html"
        className={cn(
          "rounded-md px-3 py-1.5 font-mono text-[10px] tracking-[0.14em] uppercase transition-colors",
          isHdmi
            ? "bg-live/15 text-live"
            : "text-muted-foreground hover:bg-surface hover:text-fg",
        )}
      >
        HDMI
      </Link>
      <Link
        to="/session.html"
        className={cn(
          "rounded-md px-3 py-1.5 font-mono text-[10px] tracking-[0.14em] uppercase transition-colors",
          isSession
            ? "bg-live/15 text-live"
            : "text-muted-foreground hover:bg-surface hover:text-fg",
        )}
      >
        SESSION
      </Link>
    </div>
  );
}
