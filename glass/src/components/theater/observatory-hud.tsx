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
  // Licensed gate — same fail-closed primitives the LockbugStrip uses.
  const livePaint = useTheater((s) => s.livePaint);
  const sameSeq = useTheater((s) => s.sameSeq);
  const planeDim = useTheater((s) => s.planeDim);
  const boardLocked = useTheater((s) => s.boardLocked);
  const homeScore = useTheater((s) => s.homeScore);
  const awayScore = useTheater((s) => s.awayScore);
  const confirm = useTheater((s) => s.confirm);

  if (stageMode === "replay") return null;

  const widgetsOk = livePaint && sameSeq && !planeDim;
  const licensed =
    widgetsOk && boardLocked && homeScore != null && awayScore != null && (confirm != null || boardLocked);
  const stale = videoAgeS >= 2;

  return (
    <div className="pointer-events-none absolute inset-0 z-10 flex flex-col justify-between p-3 sm:p-4">
      {/* Top HUD: aperture LIVE pill under lock / HOLD iron otherwise + licensed strip + SYNC */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <span
            data-live={licensed ? "live" : stale ? "stale" : "hold"}
            className={cn(
              "rounded-sm px-2.5 py-1 font-mono text-[11px] font-semibold tracking-[0.12em] uppercase",
              stale
                ? "bg-bg text-veto shadow-[var(--shadow-border)]"
                : licensed
                  ? "bg-bg text-live shadow-[var(--shadow-live)]"
                  : "bg-bg text-muted-foreground shadow-[var(--shadow-border)]",
            )}
          >
            {stale ? `AGE ${videoAgeS.toFixed(1)}s` : licensed ? "LIVE" : "HOLD"}
          </span>
          <LockbugStrip />
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <span
            data-sync={licensed && pllLock ? "lock" : "open"}
            className={cn(
              "rounded-sm px-2.5 py-1 font-mono text-[10px] tracking-[0.12em] uppercase shadow-[var(--shadow-border)]",
              licensed && pllLock ? "bg-bg text-sync" : "bg-bg text-muted-foreground",
            )}
          >
            {/* Measured SYNC only under a licensed lock — never a fake 0 ms on HOLD. */}
            SYNC {licensed && pllLock ? `${syncLagMs}ms` : "—"}
            {licensed && bindKind ? ` · ${bindKind}` : ""}
          </span>
        </div>
      </div>

      {/* Observatory Instrument: sheet chip, last named press, honesty */}
      <ObservatoryInstrument />

      {/* Bottom HUD: PGM label */}
      <div className="flex items-end justify-between">
        <span className="rounded-sm bg-bg/75 px-2 py-1 font-mono text-[10px] tracking-[0.16em] text-photon uppercase backdrop-blur-sm">
          PGM
        </span>
      </div>
    </div>
  );
}
