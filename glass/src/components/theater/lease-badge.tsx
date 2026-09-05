import { cn } from "@/lib/utils";

/** Operator chrome — capture-card single-open. Not on Lens / program glass. */
export function LeaseBadge({ ok }: { ok: boolean }) {
  return (
    <span
      data-lease={ok ? "ok" : "lost"}
      className={cn(
        "rounded-sm px-2.5 py-1 font-mono text-[10px] tracking-[0.12em] uppercase shadow-[var(--shadow-border)]",
        ok ? "bg-bg text-live" : "bg-bg text-veto",
      )}
    >
      {ok ? "LEASE OK" : "LEASE LOST"}
    </span>
  );
}
