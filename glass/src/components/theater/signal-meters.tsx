import type { ReactNode } from "react";
import { useTheater } from "@/lib/coupling/store";
import { METER_HOLD_AGE_S, fmtAge, fmtCount, tallyState } from "@/lib/coupling/signal-meter";
import { cn } from "@/lib/utils";
import { BroadcastClock } from "./broadcast-clock";

/** Age ladder for the 5-segment freshness meter (seconds). */
const AGE_STEPS = [0.1, 0.25, 0.5, METER_HOLD_AGE_S, 5];

function Meter({
  label,
  children,
  tone = "idle",
  className,
  ...data
}: {
  label: string;
  children: ReactNode;
  tone?: "ok" | "hold" | "dark" | "fault" | "idle";
  className?: string;
  [k: `data-${string}`]: string | number | undefined;
}) {
  return (
    <div className={cn("meter", className)} data-tone={tone} {...data}>
      <span className="meter-label">{label}</span>
      <span className="meter-value">{children}</span>
    </div>
  );
}

/** Broadcast signal-health strip: every value is read from Deck /health or the
 *  live snapshot. Unknown renders as an em dash, never as a plausible number. */
export function SignalMeters({ syncLabel, compact = false }: { syncLabel: string; compact?: boolean }) {
  const meter = useTheater((s) => s.meter);
  const rate = useTheater((s) => s.meterRate);
  const captureStatus = useTheater((s) => s.captureStatus);
  const captureLabel = useTheater((s) => s.captureLabel);
  const captureError = useTheater((s) => s.captureError);
  const pllLock = useTheater((s) => s.pllLock);
  const deckLive = useTheater((s) => s.deckLive);
  const padConnected = useTheater((s) => s.padConnected);
  const padName = useTheater((s) => s.padName);
  const ticketLive = useTheater((s) => s.ticketLive);

  const tally = tallyState(meter, { advancing: rate == null ? null : rate > 0 });
  const age = meter.ageS;
  const ageLit = age == null || !meter.hasFrame ? 0 : AGE_STEPS.filter((t) => age <= t).length;
  const ageTone = tally === "live" ? "ok" : tally === "stall" ? "fault" : tally === "hold" ? "hold" : "dark";
  const fps = meter.fpsMeas ?? (tally === "live" ? rate : null);
  const seqTone = meter.sameSeq == null ? "dark" : meter.sameSeq ? "ok" : "hold";
  const card = meter.card || (captureStatus === "live" ? captureLabel : "");

  return (
    <div className={cn("meter-strip", compact && "meter-strip-compact")} role="group" aria-label="Signal health">
      <Meter
        label="Card"
        tone={meter.leaseOk ? "ok" : captureError ? "fault" : "dark"}
        data-capture={captureStatus}
        className="meter-card"
      >
        <span className="truncate" title={captureError || undefined}>{card || "—"}</span>
        <small>{meter.leaseOk ? "lease" : "no lease"}</small>
      </Meter>
      <Meter label="Frames++" tone={rate != null && rate > 0 ? "ok" : meter.at ? "hold" : "dark"} data-frames={meter.pushes ?? meter.frames ?? ""}>
        {rate != null ? `+${Math.round(rate)}/s` : "—"}
        <small>{fmtCount(meter.pushes ?? meter.frames)}</small>
      </Meter>
      <Meter label="Age" tone={ageTone} data-age={age ?? ""}>
        {fmtAge(meter.hasFrame ? age : null)}
        <span className="meter-bar" aria-hidden>
          {AGE_STEPS.map((t, i) => (
            <i key={t} className={cn(i < ageLit && "on")} />
          ))}
        </span>
      </Meter>
      <Meter label="FPS" tone={fps != null && fps > 0 ? "ok" : "dark"}>
        {fps != null ? fps.toFixed(fps >= 10 ? 0 : 1) : "—"}
        <small>{meter.targetFps ? `/${Math.round(meter.targetFps)}` : ""}</small>
      </Meter>
      <Meter label="PLL" tone={pllLock && tally === "live" ? "ok" : "dark"} data-pll={pllLock ? "lock" : "open"}>
        {pllLock ? "Lock" : "Open"}
      </Meter>
      <Meter label="Same seq" tone={seqTone} data-same-seq={meter.sameSeq == null ? "unknown" : meter.sameSeq ? "same" : "skew"}>
        {meter.sameSeq == null ? "—" : meter.sameSeq ? "Same" : "Skew"}
        <small>{meter.liveSeq ? `#${meter.liveSeq}` : ""}</small>
      </Meter>
      <Meter label="Paint" tone={meter.paint ? "ok" : meter.at ? "hold" : "dark"} data-paint={meter.paint ? "on" : "off"}>
        {meter.paint ? "On" : "Off"}
        <small>{meter.paintReason || ""}</small>
      </Meter>
      <Meter label="Join" tone={syncLabel === "UNBOUND" ? "dark" : "ok"} data-sync={syncLabel === "UNBOUND" ? "unbound" : "lock"}>
        {syncLabel}
      </Meter>
      <Meter label="Pad" tone={padConnected ? (ticketLive ? "ok" : "hold") : "dark"} data-pad={padConnected ? "live" : "off"}>
        <span className="truncate">{padConnected ? padName : "Off"}</span>
      </Meter>
      <Meter label="Deck" tone={deckLive ? "ok" : "dark"} data-monitor={deckLive ? "live" : "wait"}>
        {deckLive ? "Up" : "Wait"}
      </Meter>
      <Meter label="Local" tone="idle" className="meter-clock">
        <BroadcastClock />
      </Meter>
    </div>
  );
}
