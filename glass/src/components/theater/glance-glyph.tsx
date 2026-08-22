import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

/** Phosphor Shell §1 — Glance Glyph F·C·L·P (ice on / subtle hollow off). */
export function GlanceGlyph({ compact }: { compact?: boolean }) {
  const livePaint = useTheater((s) => s.livePaint);
  const sameSeq = useTheater((s) => s.sameSeq);
  const planeDim = useTheater((s) => s.planeDim);
  const deckLive = useTheater((s) => s.deckLive);
  const ticketLive = useTheater((s) => s.ticketLive);
  const boardLocked = useTheater((s) => s.boardLocked);
  const confirm = useTheater((s) => s.confirm);
  const syncLagMs = useTheater((s) => s.syncLagMs);

  const planeOk = livePaint && sameSeq && !planeDim;
  // Fail-closed: when Dark Theater / Same-Seq / paint dark, all glyphs off.
  const frameOn = planeOk && deckLive;
  const coupleOn = planeOk && ticketLive;
  const lockOn = planeOk && (boardLocked || Boolean(confirm));
  const planeOn = planeOk;

  const bits = compact
    ? [
        { key: "frame" as const, label: "F", on: frameOn },
        { key: "lock" as const, label: "L", on: lockOn },
      ]
    : [
        { key: "frame" as const, label: "F", on: frameOn },
        { key: "couple" as const, label: "C", on: coupleOn },
        { key: "lock" as const, label: "L", on: lockOn },
        { key: "plane" as const, label: "P", on: planeOn },
      ];

  return (
    <div
      className="pointer-events-none flex items-center gap-2"
      data-phosphor="glance-glyph"
      data-plane={planeOk ? "ok" : "dark"}
    >
      <div className="flex items-center gap-1.5 font-mono text-[11px] tracking-[0.18em]">
        {bits.map((b, i) => (
          <span key={b.key} className="inline-flex items-center gap-1.5">
            {i > 0 ? (
              <span className="text-subtle-foreground/40" aria-hidden>
                ·
              </span>
            ) : null}
            <span
              data-frame={b.key === "frame" ? (b.on ? "on" : "off") : undefined}
              data-couple={b.key === "couple" ? (b.on ? "on" : "off") : undefined}
              data-lock={b.key === "lock" ? (b.on ? "on" : "off") : undefined}
              data-plane={b.key === "plane" ? (b.on ? "on" : "off") : undefined}
              className={cn(
                "inline-grid size-5 place-items-center rounded-sm border font-bold leading-none",
                b.on
                  ? "border-sync text-sync shadow-[var(--shadow-sync)]"
                  : "border-subtle-foreground/40 text-subtle-foreground/40",
              )}
            >
              {b.label}
            </span>
          </span>
        ))}
      </div>
      <span
        data-sync="trail"
        className="font-mono text-[10px] tabular-nums tracking-wide text-sync uppercase"
      >
        SYNC {Number.isFinite(syncLagMs) ? Math.round(syncLagMs) : "—"}ms
      </span>
    </div>
  );
}
