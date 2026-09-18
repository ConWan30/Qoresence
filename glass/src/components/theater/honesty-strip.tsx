import { useTheater } from "@/lib/coupling/store";
import type { HonestyConf, HonestyState } from "@/lib/coupling/honesty-health";
import { cn } from "@/lib/utils";

/** TicketGlass + SyncGlass votes. Lives under CommandBar, never inside HdmiStage. */
export function HonestyStrip({ compact }: { compact?: boolean }) {
  const honesty = useTheater((s) => s.honesty);
  const syncLagMs = useTheater((s) => s.syncLagMs);
  const livePaint = useTheater((s) => s.livePaint);
  const sameSeq = useTheater((s) => s.sameSeq);
  const planeDim = useTheater((s) => s.planeDim);
  const darkTheater = planeDim || !livePaint || !sameSeq;
  const state: HonestyState = honesty.enabled && honesty.state === "live" && !darkTheater ? "live" : "dark";

  return (
    <div
      id="honestyStrip"
      data-honesty={state}
      className={cn("honesty-strip", compact && "honesty-strip-compact")}
      aria-label="Honesty"
    >
      {honesty.glyphs.map((g) => {
        const conf: HonestyConf = state === "dark" ? "ghost" : g.conf;
        const lagFact =
          g.id === "lag" && state === "live" && Number.isFinite(syncLagMs) && syncLagMs > 0
            ? `${Math.round(syncLagMs)}ms`
            : "";
        const value = state === "dark" && !lagFact ? g.value : lagFact || g.value;
        return (
          <span
            key={g.id}
            data-glyph={g.id}
            data-conf={conf}
            data-value={g.value}
            data-honesty={state}
            title={g.title}
            className="honesty-glyph"
          >
            <span className="honesty-glyph-name">{g.id}</span>
            <span className="honesty-glyph-value">{value}</span>
          </span>
        );
      })}
    </div>
  );
}

/** Overlay / X: one quiet void chip. Never the 6-glyph strip. */
export function HonestyVoidChip() {
  const blocked = useTheater((s) => s.honesty.paintBlocked);
  if (!blocked) return null;
  return (
    <span
      data-honesty-void="blank"
      title="confirm pending"
      className="font-mono text-[10px] tracking-wide text-subtle-foreground/70"
    >
      □
    </span>
  );
}
