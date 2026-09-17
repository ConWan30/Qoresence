import { freshnessBand } from "@/lib/coupling/digit-integrity";
import { skewState } from "@/lib/coupling/skew-alarm";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

function Tile({ label, value, tone }: { label: string; value: string; tone: "ok" | "warn" | "alarm" | "void" }) {
  return (
    <div
      data-integrity-tile={label}
      className={cn(
        "rounded-sm px-2 py-1 font-mono text-[10px] tracking-wide uppercase shadow-[var(--shadow-border)] bg-bg",
        tone === "ok" && "text-live",
        tone === "warn" && "text-fast",
        (tone === "alarm" || tone === "void") && "text-veto",
      )}
    >
      <span className="text-muted-foreground">{label} </span>
      {value}
    </div>
  );
}

/** Operator-only integrity tiles. Never mounted on Lens / overlay.html. No score bumpers. */
export function IntegrityBoard() {
  const deckLive = useTheater((s) => s.deckLive);
  const videoAgeS = useTheater((s) => s.videoAgeS);
  const sameSeq = useTheater((s) => s.sameSeq);
  const boardLocked = useTheater((s) => s.boardLocked);
  const confirm = useTheater((s) => s.confirm);
  const ticket = useTheater((s) => s.ticket);
  const path = useTheater((s) => s.clutchPulsePath);
  const livePaint = useTheater((s) => s.livePaint);
  const noulOn = useTheater((s) => s.agentPlane.noulEnabled);
  const honestyBand = useTheater((s) => s.agentPlane.honestyBand);
  const presenceToken = useTheater((s) => s.agentPlane.presenceToken);
  const identNow = useTheater((s) => s.agentPlane.identNow);
  const hudKind = useTheater((s) => s.agentPlane.hudKind);
  const jpgOk = livePaint;
  const hidNs = ticket?.clockNs || 0;
  const hdmiNs = confirm?.clockNs || hidNs;
  const skew = skewState({
    hidClockNs: hidNs,
    hdmiClockNs: hdmiNs,
    frameSeqGap: sameSeq ? 0 : 31,
    ageS: videoAgeS,
  });
  const ageNs = confirm && ticket ? Math.max(0, Number(ticket.clockNs || 0) - Number(confirm.clockNs || 0)) : 0;
  const fresh = boardLocked && confirm ? freshnessBand(ageNs) : "ident";
  const digitPath = boardLocked && confirm ? (path === "fast" ? "fast" : "confirm") : "void";
  const identTone: "ok" | "warn" | "alarm" | "void" = identNow || !jpgOk ? "alarm" : "ok";
  const honestyTone: "ok" | "warn" | "alarm" | "void" =
    honestyBand === "ok" ? "ok" : honestyBand === "amber" ? "warn" : honestyBand === "ident" ? "alarm" : "void";

  return (
    <div data-integrity-board="on" className="pointer-events-none flex flex-wrap gap-1.5">
      <Tile label="Lease" value={deckLive ? "ok" : "lost"} tone={deckLive ? "ok" : "alarm"} />
      <Tile label="Ticket" value={fresh} tone={fresh === "ok" ? "ok" : fresh === "amber" ? "warn" : "void"} />
      <Tile label="Digit" value={digitPath} tone={digitPath === "confirm" ? "ok" : digitPath === "fast" ? "warn" : "void"} />
      <Tile label="Skew" value={skew} tone={skew} />
      <Tile label="Ident" value={identNow || !jpgOk ? "now" : "off"} tone={identTone} />
      <Tile label="Digits" value={boardLocked ? "live" : "blank"} tone={boardLocked ? "ok" : "void"} />
      {noulOn ? (
        <>
          <Tile label="Honesty" value={honestyBand} tone={honestyTone} />
          <Tile label="Presence" value={presenceToken} tone={presenceToken === "dense" ? "ok" : presenceToken === "join" ? "warn" : "void"} />
          {hudKind ? <Tile label="HUD" value={hudKind.replace("_", " ")} tone={hudKind === "select_plate" || hudKind === "menu" ? "void" : "ok"} /> : null}
        </>
      ) : null}
    </div>
  );
}
