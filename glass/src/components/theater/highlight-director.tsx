import { useEffect, useState } from "react";
import { CLIP_HOLD_MS, directorBrief, directorReasons } from "@/lib/coupling/director";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

const MODE_LABEL = {
  watch: "Watch",
  prime: "Prime",
  armed: "Armed",
  hold: "Hold",
  encode: "Encode",
} as const;

/** Next-take switcher — ARM punches a 30s HDMI clip, HOLD silences auto-clip, KILL clears hold. */
export function HighlightDirector() {
  const [now, setNow] = useState(() => Date.now());
  const clutch = useTheater((s) => s.clutch);
  const companion = useTheater((s) => s.companion);
  const clipBusy = useTheater((s) => s.clipBusy);
  const holdUntil = useTheater((s) => s.clipHoldUntil);
  const stemProgram = useTheater((s) => s.stemProgram);
  const moments = useTheater((s) => s.moments);
  const lastClipError = useTheater((s) => s.lastClipError);
  const armTake = useTheater((s) => s.armTake);
  const holdClip = useTheater((s) => s.holdClip);
  const killTake = useTheater((s) => s.killTake);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const local = directorBrief({
    now,
    holdUntil,
    clipBusy,
    companionArmed: companion.armed,
    redZone: companion.redZone,
    late: companion.late,
    close: companion.close,
    clutchScore: clutch.score,
    clutchKind: clutch.kind,
    clutchLabel: clutch.label,
    clutchWhy: clutch.why,
    companionWhy: companion.why,
    clipWorth: companion.coupling || clutch.score,
  });
  const brief =
    clipBusy || holdUntil > now
      ? local
      : stemProgram
        ? { mode: stemProgram.mode, why: stemProgram.why, armHot: stemProgram.armHot }
        : local;
  const ticker = directorReasons(moments);
  const holdLeft = Math.max(0, Math.ceil((holdUntil - now) / 1000));

  return (
    <section className="holo-plate flex flex-col gap-3 rounded-xl p-4" data-director={brief.mode}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Director
        </h2>
        <span
          className={cn(
            "font-mono text-[10px] tracking-[0.16em] uppercase",
            brief.mode === "watch" || brief.mode === "hold"
              ? "text-subtle-foreground"
              : "text-live",
          )}
        >
          {MODE_LABEL[brief.mode]}
          {brief.mode === "hold" && holdLeft > 0 ? ` ${holdLeft}s` : ""}
        </span>
      </div>

      <p data-director-why={brief.why} className="font-display text-xl font-extrabold leading-snug tracking-tight text-fg">
        {brief.why}
      </p>

      {lastClipError ? (
        <p className="font-mono text-[10px] tracking-wide text-veto uppercase">{lastClipError}</p>
      ) : null}

      <div className="grid grid-cols-3 gap-1.5">
        <button
          type="button"
          data-action="director-arm"
          disabled={clipBusy}
          className={cn(
            "stream-key inline-flex h-11 items-center justify-center font-mono text-[11px] font-extrabold tracking-[0.14em]",
            brief.armHot && !clipBusy ? "stream-key-live" : "text-muted-foreground",
          )}
          onClick={() => armTake()}
        >
          ARM
        </button>
        <button
          type="button"
          data-action="director-hold"
          className={cn(
            "stream-key inline-flex h-11 items-center justify-center font-mono text-[11px] font-extrabold tracking-[0.14em]",
            brief.mode === "hold" ? "stream-key-clip" : "text-muted-foreground",
          )}
          onClick={() => holdClip()}
        >
          HOLD
        </button>
        <button
          type="button"
          data-action="director-kill"
          className="stream-key inline-flex h-11 items-center justify-center font-mono text-[11px] font-extrabold tracking-[0.14em] text-muted-foreground"
          onClick={() => killTake()}
        >
          KILL
        </button>
      </div>

      <p className="font-mono text-[10px] tracking-[0.12em] text-subtle-foreground uppercase">
        Hold lasts {Math.round(CLIP_HOLD_MS / 1000)}s · ARM cuts a 30s ISO
      </p>

      {ticker.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {ticker.map((line) => (
            <li key={line} className="truncate font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
              {line}
            </li>
          ))}
        </ul>
      ) : (
        <p className="font-mono text-[10px] tracking-wide text-subtle-foreground uppercase">
          No takes yet — clutch lines land here
        </p>
      )}
    </section>
  );
}
