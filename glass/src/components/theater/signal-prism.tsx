import { cn } from "@/lib/utils";
import type { LiveHealth } from "@/lib/coupling/live-health";

/** Holographic signal bar under the HDMI plinth — fill tracks hub freshness. */
export function SignalPrism({
  ageS,
  tone,
}: {
  ageS: number | null;
  tone: LiveHealth["tone"];
}) {
  const age = typeof ageS === "number" && Number.isFinite(ageS) ? Math.max(0, ageS) : 1;
  const freshness = Math.max(0, Math.min(1, 1 - age / 1.2));
  return (
    <div className="signal-prism" data-tone={tone} aria-hidden>
      <div
        className={cn(
          "signal-prism-fill",
          tone === "green" && "is-live",
          tone === "amber" && "is-hold",
          tone === "red" && "is-stall",
        )}
        style={{ width: `${Math.round(freshness * 100)}%` }}
      />
    </div>
  );
}
