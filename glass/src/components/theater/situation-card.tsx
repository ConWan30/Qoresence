import { useTheater } from "@/lib/coupling/store";

export function SituationCard() {
  const situation = useTheater((s) => s.situation);
  const gameTitle = useTheater((s) => s.gameTitle);
  const boardLine = useTheater((s) => s.boardLine);
  const vlm = useTheater((s) => s.agentPlane.vlmLocked);
  const hdmi = useTheater((s) => s.hdmi);
  const planeDim = useTheater((s) => s.planeDim);
  const sameSeq = useTheater((s) => s.sameSeq);
  const livePaint = useTheater((s) => s.livePaint);
  const line = planeDim || !sameSeq || !livePaint ? "" : situation || boardLine;

  return (
    <section className="flex flex-col gap-2 rounded-xl bg-surface p-4 shadow-[var(--shadow-border)]">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Situation
        </h2>
        <span className="font-mono text-[10px] tracking-wide text-subtle-foreground uppercase">
          {vlm ? "scorebug lock" : hdmi === "menu" ? "menu" : "scorebug"}
        </span>
      </div>
      <p
        data-situation={line || "wait"}
        className="font-display text-xl font-extrabold leading-snug tracking-tight text-fg"
      >
        {line || (planeDim ? "Plane dim" : !sameSeq ? "" : "Waiting for scoreboard…")}
      </p>
      <p className="font-mono text-[10px] tracking-wide text-subtle-foreground uppercase">
        {gameTitle || "title-presence from HDMI"}
      </p>
    </section>
  );
}