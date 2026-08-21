import type { ReactNode } from "react";
import { PHRASES } from "@/lib/coupling/engine";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";
import { DualSensePad } from "./dualsense-pad";

export function LensOverlay({ variant }: { variant: "deck" | "lens" }) {
  const hdmi = useTheater((s) => s.hdmi);
  const pllLock = useTheater((s) => s.pllLock);
  const phrase = useTheater((s) => s.phrase);
  const ticket = useTheater((s) => s.ticket);
  const ticketLive = useTheater((s) => s.ticketLive);
  const coupling = useTheater((s) => s.coupling);
  const motion = useTheater((s) => s.motion);
  const heatLine = useTheater((s) => s.heatLine);
  const heatVetoed = useTheater((s) => s.heatVetoed);
  const throwAttempt = useTheater((s) => s.throwAttempt);
  const r2 = useTheater((s) => s.r2);
  const left = useTheater((s) => s.left);
  const r2Frame = useTheater((s) => s.r2Frame);
  const leftFrame = useTheater((s) => s.leftFrame);
  const confirm = useTheater((s) => s.confirm);
  const boardLine = useTheater((s) => s.boardLine);
  const situation = useTheater((s) => s.situation);
  const clutch = useTheater((s) => s.clutch);
  const padConnected = useTheater((s) => s.padConnected);
  const padName = useTheater((s) => s.padName);
  const captureStatus = useTheater((s) => s.captureStatus);
  const captureLabel = useTheater((s) => s.captureLabel);

  const hdmiLabel =
    captureStatus === "live"
      ? `HDMI ${captureLabel || "LIVE"}`
      : hdmi === "live"
        ? "HDMI WAIT"
        : hdmi === "menu"
          ? "MENU"
          : "STALE";
  const heatLabel = ticketLive ? "heat licensed" : heatVetoed ? "heat veto" : "quiet";
  const heatKey = ticketLive ? "licensed" : heatVetoed ? "veto" : "quiet";
  const pill = throwAttempt
    ? "THROW forbidden · authorship"
    : ticketLive && ticket
      ? `${phrase.phrase} · ticket ${ticket.ticketId.slice(0, 8)} · heat licensed`
      : `${phrase.phrase} · couple: none`;

  const board = situation || boardLine || (confirm ? `${confirm.homeScore}-${confirm.awayScore}` : null);
  const ribbonOpacity = 0.08 + Math.max(coupling, clutch.score) * 0.55;

  return (
    <div className="pointer-events-none absolute inset-0 flex flex-col">
      <div
        className="h-0.5 w-full bg-live shadow-[var(--shadow-live)]"
        style={{ opacity: ribbonOpacity }}
        aria-hidden
      />

      <div className="flex items-start justify-between gap-3 p-3 sm:p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Chip>{hdmiLabel}</Chip>
          <Chip hot={padConnected}>
            {padConnected ? `PAD ${padName}` : "PAD WAIT"}
          </Chip>
          <Chip hot={pllLock} cold={!pllLock}>
            {pllLock ? "PLL LOCK" : "PLL OPEN"}
          </Chip>
          {board && <Chip>{board}</Chip>}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Chip>
            c {coupling.toFixed(2)}
            <span className="mx-1.5 text-subtle-foreground">·</span>m {motion.toFixed(1)}
          </Chip>
          <Chip hot={ticketLive} cold={heatVetoed}>
            {heatLabel}
          </Chip>
        </div>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4">
        <p
          key={throwAttempt ? "throw" : phrase.phrase}
          data-phrase={phrase.phrase}
          className={cn(
            "font-display font-extrabold leading-none tracking-tight text-live",
            variant === "lens" ? "text-6xl sm:text-8xl" : "text-5xl sm:text-7xl",
            "transition-opacity duration-(--motion-fast) ease-(--ease-smooth-out)",
            phrase.live && ticketLive ? "opacity-100" : "opacity-50",
          )}
        >
          {throwAttempt ? "—" : clutch.kind === "climax" || clutch.kind === "score_play" || clutch.kind === "window" ? clutch.label : phrase.phrase}
        </p>
        {variant === "deck" && (
          <Lattice current={phrase.phrase} />
        )}
        {throwAttempt ? (
          <p className="font-mono text-xs tracking-wide text-veto">
            THROW forbidden · authorship
          </p>
        ) : clutch.kind !== "quiet" ? (
          <p className="max-w-md text-center text-sm text-fg">{clutch.why}</p>
        ) : heatLine ? (
          <p className="max-w-md text-center text-sm text-fg">{heatLine}</p>
        ) : heatVetoed ? (
          <p className="font-mono text-xs tracking-wide text-veto">
            heat stripped · no coupling ticket
          </p>
        ) : (
          <p className="font-mono text-xs tabular-nums tracking-wide text-muted-foreground">
            conf {phrase.confidence.toFixed(2)}
          </p>
        )}
      </div>

      <div className="flex items-end justify-between gap-3 p-3 sm:p-4">
        {variant === "deck" ? (
          <DualSensePad r2={r2} left={left} r2Frame={r2Frame} leftFrame={leftFrame} live={ticketLive} />
        ) : (
          <span className="font-mono text-[10px] tracking-[0.14em] text-subtle-foreground uppercase">
            Retina Lens
          </span>
        )}
        <div
          data-ticket={ticketLive ? "live" : "none"}
          data-heat={heatKey}
          className={cn(
            "max-w-[70%] truncate rounded-full px-3 py-2 font-mono text-xs tabular-nums tracking-wide shadow-[var(--shadow-border)]",
            ticketLive ? "bg-live/15 text-live" : heatVetoed ? "bg-veto/15 text-veto" : "bg-surface/80 text-muted-foreground",
          )}
        >
          {pill}
        </div>
      </div>
    </div>
  );
}

function Chip({
  children,
  hot,
  cold,
}: {
  children: ReactNode;
  hot?: boolean;
  cold?: boolean;
}) {
  return (
    <span
      className={cn(
        "rounded-full px-2.5 py-1 font-mono text-[10px] tracking-wide uppercase shadow-[var(--shadow-border)]",
        hot ? "bg-live/15 text-live" : cold ? "bg-veto/15 text-veto" : "bg-surface/80 text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}

function Lattice({ current }: { current: string }) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-1.5">
      {PHRASES.map((p) => (
        <span
          key={p}
          className={cn(
            "rounded-full px-2 py-0.5 font-mono text-[10px] tracking-wide",
            p === current ? "bg-primary text-primary-foreground" : "text-subtle-foreground",
          )}
        >
          {p}
        </span>
      ))}
    </div>
  );
}
