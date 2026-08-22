import { downDistanceLabel } from "@/lib/coupling/board";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

/** Phosphor Shell §1 — Down Pill (lime when ticket-coupled lock ok). */
export function DownPill({ className }: { className?: string }) {
  const livePaint = useTheater((s) => s.livePaint);
  const sameSeq = useTheater((s) => s.sameSeq);
  const planeDim = useTheater((s) => s.planeDim);
  const boardLocked = useTheater((s) => s.boardLocked);
  const ticketLive = useTheater((s) => s.ticketLive);
  const confirm = useTheater((s) => s.confirm);
  const down = useTheater((s) => s.down);
  const distance = useTheater((s) => s.distance);

  const widgetsOk = livePaint && sameSeq && !planeDim;
  const lockedOk =
    widgetsOk && boardLocked && (ticketLive || Boolean(confirm)) && down != null;

  const label = lockedOk ? downDistanceLabel(down, distance) : "— & —";

  return (
    <span
      data-down-pill={lockedOk ? "locked" : "unlocked"}
      className={cn(
        "rounded-full px-2.5 py-1 font-mono text-[10px] tracking-wide uppercase shadow-[var(--shadow-border)]",
        lockedOk ? "bg-live/15 text-live" : "bg-surface/80 text-subtle-foreground/70",
        className,
      )}
    >
      {label}
    </span>
  );
}
