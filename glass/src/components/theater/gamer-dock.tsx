import { scorebugPair } from "@/lib/coupling/board";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

/** Gamer instruments under the command bar. No operator telemetry. */
export function GamerDock() {
  const padConnected = useTheater((s) => s.padConnected);
  const ticketLive = useTheater((s) => s.ticketLive);
  const boardLocked = useTheater((s) => s.boardLocked);
  const homeScore = useTheater((s) => s.homeScore);
  const awayScore = useTheater((s) => s.awayScore);
  const livePaint = useTheater((s) => s.livePaint);
  const sameSeq = useTheater((s) => s.sameSeq);
  const planeDim = useTheater((s) => s.planeDim);
  const honesty = useTheater((s) => s.honesty);
  const bind = honesty.glyphs.find((g) => g.id === "bind");

  const widgetsOk = livePaint && sameSeq && !planeDim;
  const licensed = widgetsOk && boardLocked && homeScore != null && awayScore != null && !honesty.paintBlocked;
  const board = licensed
    ? scorebugPair({ homeScore, awayScore, dash: "–" }) || "□–□"
    : "□–□";
  const pad = !padConnected ? "pad off" : ticketLive ? "pad on picture" : "pad quiet";
  const join = bind && honesty.state === "live" ? bind.value : "looking";

  return (
    <div
      className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-1.5 font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase sm:px-5"
      aria-label="Play instruments"
    >
      <span data-gamer-board={licensed ? "lock" : "blank"} className={cn(licensed && "text-live")}>
        Board {board}
      </span>
      <span data-gamer-pad={padConnected ? "on" : "off"} className={cn(ticketLive && "text-live")}>
        {pad}
      </span>
      <span data-gamer-join={join} className="hidden sm:inline">
        Join {join}
      </span>
      <span className="ml-auto hidden text-subtle-foreground sm:inline">
        1 live · 2 replay · 3 clip
      </span>
    </div>
  );
}
