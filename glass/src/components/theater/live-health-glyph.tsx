import { cn } from "@/lib/utils";
import type { LiveHealth } from "@/lib/coupling/live-health";

export function LiveHealthGlyph({ health }: { health: LiveHealth }) {
  return (
    <div
      data-live-health={health.tone}
      title={health.reason}
      className="pointer-events-none absolute top-3 right-3 z-20 flex items-center gap-2 rounded-sm bg-bg/80 px-2.5 py-1 font-mono text-[10px] tracking-[0.16em] text-white uppercase shadow-[var(--shadow-border)] backdrop-blur-sm"
    >
      <span
        className={cn(
          "size-2 rounded-full",
          health.tone === "green" ? "bg-live" : health.tone === "amber" ? "bg-fast" : "bg-veto",
        )}
      />
      {health.label}
    </div>
  );
}
