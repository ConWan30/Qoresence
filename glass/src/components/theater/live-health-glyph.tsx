import { cn } from "@/lib/utils";
import type { LiveHealth } from "@/lib/coupling/live-health";

export function LiveHealthGlyph({ health }: { health: LiveHealth }) {
  return (
    <div
      data-live-health={health.tone}
      title={health.reason}
      className="pointer-events-none absolute top-3 right-3 z-30 flex items-center gap-2 rounded-full bg-black/70 px-2.5 py-1 font-mono text-[10px] tracking-wide text-white uppercase"
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
