import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";
import { LockbugStrip } from "./lockbug-strip";
import { ObservatoryInstrument } from "./observatory-instrument";

export function ObservatoryHUD() {
  const videoAgeS = useTheater((s) => s.videoAgeS);
  const pllLock = useTheater((s) => s.pllLock);
  const syncLagMs = useTheater((s) => s.syncLagMs);
  const bindKind = useTheater((s) => s.bindKind);
  const stageMode = useTheater((s) => s.stageMode);

  if (stageMode === "replay") return null;

  return (
    <div className="pointer-events-none absolute inset-0 z-10 flex flex-col justify-between p-3 sm:p-4">
      {/* Top HUD: LIVE pulse + licensed situation strip + SYNC */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <span
            className={cn(
              "rounded-full px-2.5 py-1 font-mono text-[11px] font-extrabold tracking-[0.14em] uppercase shadow-[var(--shadow-border)]",
              videoAgeS < 2 ? "bg-bg text-live" : "bg-bg text-veto",
            )}
          >
            {videoAgeS < 2 ? "LIVE" : `AGE ${videoAgeS.toFixed(1)}s`}
          </span>
          <LockbugStrip />
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <span
            className={cn(
              "rounded-full px-2.5 py-1 font-mono text-[10px] tracking-wide uppercase shadow-[var(--shadow-border)]",
              pllLock ? "bg-bg text-sync" : "bg-bg text-muted-foreground",
            )}
          >
            SYNC {syncLagMs}ms{bindKind ? ` · ${bindKind}` : ""}
          </span>
        </div>
      </div>

      {/* Observatory Instrument: sheet chip, last named press, honesty */}
      <ObservatoryInstrument />

      {/* Bottom HUD: PGM label */}
      <div className="flex items-end justify-between">
        <span className="rounded-sm bg-bg/75 px-2 py-1 font-mono text-[10px] tracking-[0.2em] text-photon uppercase backdrop-blur-sm">
          PGM
        </span>
      </div>
    </div>
  );
}
