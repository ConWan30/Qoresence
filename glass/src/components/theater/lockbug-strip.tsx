import { downDistanceLabel, scorebugPair } from "@/lib/coupling/board";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

/** Phosphor Shell §1 — Lockbug Situation Strip (fail-closed digits). */
export function LockbugStrip({ className }: { className?: string }) {
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

  return (
    <p
      data-lockbug={licensed ? "locked" : "unlocked"}
      data-situation={licensed ? "live" : "dark"}
      className={cn(
        "font-mono text-[11px] tracking-wide tabular-nums",
        licensed ? "text-fg" : "text-subtle-foreground/70",
        className,
      )}
    >
      {text}
    </p>
  );
}
