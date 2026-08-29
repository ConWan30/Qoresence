import { useEffect, useRef, useState } from "react";
import { downDistanceLabel, scorebugPair } from "@/lib/coupling/board";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

/** One-shot lockbug glow driven by the store's licensed clutch/climax token.
 *  `enabled` folds in the strip's own `licensed` gate so HOLD never glows. */
function useClutchLand(enabled: boolean): "fast" | "confirm" | null {
  const seq = useTheater((s) => s.clutchPulseSeq);
  const path = useTheater((s) => s.clutchPulsePath);
  const [land, setLand] = useState<"fast" | "confirm" | null>(null);
  const initRef = useRef(false);
  useEffect(() => {
    // Skip the mount tick — only new licensed triggers (seq bumps) glow.
    if (!initRef.current) {
      initRef.current = true;
      return;
    }
    if (!enabled || (path !== "fast" && path !== "confirm")) return;
    const p = path;
    setLand(p);
    const id = window.setTimeout(() => setLand((v) => (v === p ? null : v)), 260);
    return () => window.clearTimeout(id);
    // Fire on each new licensed clutch/climax start (seq), not on gate flips.
  }, [seq]); // eslint-disable-line react-hooks/exhaustive-deps
  return land;
}

/** Phosphor Shell §1 — Lockbug Situation Strip (fail-closed digits). */
export function LockbugStrip({ className, pulse = false }: { className?: string; pulse?: boolean }) {
  const livePaint = useTheater((s) => s.livePaint);
  const sameSeq = useTheater((s) => s.sameSeq);
  const planeDim = useTheater((s) => s.planeDim);
  const boardLocked = useTheater((s) => s.boardLocked);
  const homeScore = useTheater((s) => s.homeScore);
  const awayScore = useTheater((s) => s.awayScore);
  const homeTeam = useTheater((s) => s.homeTeam);
  const awayTeam = useTheater((s) => s.awayTeam);
  const homeLeft = useTheater((s) => s.homeLeft);
  const down = useTheater((s) => s.down);
  const distance = useTheater((s) => s.distance);
  const confirm = useTheater((s) => s.confirm);

  const widgetsOk = livePaint && sameSeq && !planeDim;
  const licensed =
    widgetsOk &&
    boardLocked &&
    homeScore != null &&
    awayScore != null &&
    (confirm != null || boardLocked);

  const score = licensed
    ? scorebugPair({
        homeScore,
        awayScore,
        homeTeam,
        awayTeam,
        homeLeft,
        dash: "–",
      }) || "□–□"
    : "□–□";
  const downLine = licensed ? downDistanceLabel(down, distance) : "— & —";
  const text = `${score} · ${downLine}`;

  // Chrome-only, one-shot glow on a licensed clutch/climax start. Never fires
  // on HOLD/unlocked (gated by `licensed`) and never touches the picture.
  const land = useClutchLand(pulse && licensed);

  return (
    <p
      data-lockbug={licensed ? "locked" : "unlocked"}
      data-situation={licensed ? "live" : "dark"}
      data-land={land ?? undefined}
      className={cn(
        "lockbug-lock font-mono text-[11px] tracking-wide tabular-nums",
        licensed ? "text-fg" : "text-subtle-foreground/70",
        className,
      )}
    >
      {text}
    </p>
  );
}
