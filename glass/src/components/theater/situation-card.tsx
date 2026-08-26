import { downDistanceLabel, scorebugPair } from "@/lib/coupling/board";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

export function SituationCard() {
  const situation = useTheater((s) => s.situation);
  const gameTitle = useTheater((s) => s.gameTitle);
  const boardLine = useTheater((s) => s.boardLine);
  const vlm = useTheater((s) => s.agentPlane.vlmLocked);
  const hdmi = useTheater((s) => s.hdmi);
  const planeDim = useTheater((s) => s.planeDim);
  const sameSeq = useTheater((s) => s.sameSeq);
  const livePaint = useTheater((s) => s.livePaint);
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
  const licensed = widgetsOk && boardLocked && homeScore != null && awayScore != null && (confirm != null || boardLocked);
  const line = licensed ? situation || boardLine : "";

  // Fail-closed: unlocked shows □–□ · — & —
  const fallback = licensed
    ? ""
    : `${scorebugPair({ homeScore: null, awayScore: null, dash: "–" }) || "□–□"} · ${downDistanceLabel(null, null)}`;

  return (
    <section className="holo-plate flex flex-col gap-2 rounded-xl p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Situation
        </h2>
        <span className="font-mono text-[10px] tracking-wide text-subtle-foreground uppercase">
          {vlm ? "scorebug lock" : hdmi === "menu" ? "menu" : "scorebug"}
        </span>
      </div>
      <p
        data-situation={line || fallback}
        className={cn(
          "font-display text-xl font-extrabold leading-snug tracking-tight",
          line ? "text-fg" : "text-muted-foreground"
        )}
      >
        {line || fallback}
      </p>
      <p className="font-mono text-[10px] tracking-wide text-subtle-foreground uppercase">
        {gameTitle || "title-presence from HDMI"}
      </p>
    </section>
  );
}