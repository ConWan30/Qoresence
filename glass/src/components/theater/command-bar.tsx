import { useEffect } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";
import { BroadcastClock } from "./broadcast-clock";
import { HoloTally } from "./holo-tally";
import { LockbugStrip } from "./lockbug-strip";

const GLASSES = [
  { href: "/", label: "Home" },
  { href: "/deck.html", label: "Theater" },
  { href: "/session.html", label: "Session", offApp: true },
  { href: "/overlay.html", label: "Lens" },
  { href: "/studio.html", label: "Foundry" },
  { href: "/mobile.html", label: "Mobile" },
] as const;

function glassOn(href: string, label: string, pathname: string) {
  if (href === "/") return pathname === "/" || pathname === "home";
  return pathname === href || pathname === label.toLowerCase();
}

function GlassNavLink({
  href,
  label,
  pathname,
  compact,
  offApp,
}: {
  href: string;
  label: string;
  pathname: string;
  compact?: boolean;
  offApp?: boolean;
}) {
  const on = glassOn(href, label, pathname);
  const className = cn(
    compact
      ? "stream-key inline-flex h-8 min-w-14 items-center justify-center px-2.5 text-xs font-medium"
      : "inline-flex h-9 min-w-16 items-center justify-center rounded-md px-3 text-xs font-medium",
    on ? "stream-key-live" : "text-muted-foreground",
  );
  if (offApp) {
    return (
      <a href={href} className={className}>
        {label}
      </a>
    );
  }
  return (
    <Link
      to={href as "/" | "/deck.html" | "/overlay.html" | "/studio.html" | "/mobile.html"}
      className={className}
    >
      {label}
    </Link>
  );
}

export function CommandBar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const hdmi = useTheater((s) => s.hdmi);
  const pllLock = useTheater((s) => s.pllLock);
  const ticketLive = useTheater((s) => s.ticketLive);
  const boardLine = useTheater((s) => s.boardLine);
  const situation = useTheater((s) => s.situation);
  const gameTitle = useTheater((s) => s.gameTitle);
  const vlmLocked = useTheater((s) => s.agentPlane.vlmLocked);
  const heatVetoed = useTheater((s) => s.heatVetoed);
  const padConnected = useTheater((s) => s.padConnected);
  const padName = useTheater((s) => s.padName);
  const captureStatus = useTheater((s) => s.captureStatus);
  const captureLabel = useTheater((s) => s.captureLabel);
  const captureError = useTheater((s) => s.captureError);
  const deckLive = useTheater((s) => s.deckLive);
  const syncLagMs = useTheater((s) => s.syncLagMs);
  const bindKind = useTheater((s) => s.bindKind);
  const armCapture = useTheater((s) => s.armCapture);
  const stageMode = useTheater((s) => s.stageMode);
  const lastClipUrl = useTheater((s) => s.lastClipUrl);
  const clipBusy = useTheater((s) => s.clipBusy);
  const goLive = useTheater((s) => s.goLive);
  const goReplay = useTheater((s) => s.goReplay);
  const requestHdmiClip = useTheater((s) => s.requestHdmiClip);
  const takeCount = useTheater((s) => s.takeCount);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (e.key === "1" || e.key === "l" || e.key === "L") {
        e.preventDefault();
        useTheater.getState().goLive();
      }
      if (e.key === "2" || e.key === "r" || e.key === "R") {
        e.preventDefault();
        useTheater.getState().goReplay();
      }
      if (e.key === "3" || e.key === "c" || e.key === "C") {
        e.preventDefault();
        if (!useTheater.getState().clipBusy) void useTheater.getState().requestHdmiClip();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const status = heatVetoed
    ? "heat veto"
    : ticketLive
      ? "ticket live"
      : "couple none";

  const livePaint = useTheater((s) => s.livePaint);
  const sameSeq = useTheater((s) => s.sameSeq);
  const planeDim = useTheater((s) => s.planeDim);
  const widgetsOk = livePaint && sameSeq && !planeDim;
  // Prefer LockbugStrip in chrome; never fall back to unlocked confirm pair.
  const sit = widgetsOk && (situation || boardLine)
    ? [gameTitle, situation || boardLine].filter(Boolean).join(" · ")
    : widgetsOk && vlmLocked
      ? "VLM lock · board"
      : hdmi === "menu"
        ? "menu"
        : "";

  const dot = heatVetoed ? "bg-veto" : ticketLive ? "bg-live" : pllLock ? "bg-sync" : "bg-muted-foreground";

  const padText = padConnected ? `PAD ${padName}` : "PAD WAIT";
  const hdmiText =
    captureStatus === "live"
      ? `HDMI ${captureLabel}`
      : captureStatus === "arming"
        ? "HDMI arming"
        : captureStatus === "blocked"
          ? "HDMI blocked"
          : captureStatus === "busy"
            ? "HDMI busy"
            : captureStatus === "framed"
              ? "HDMI framed"
              : "HDMI wait";

  const active = pathname;
  const tallyMode =
    stageMode === "replay"
      ? "standby"
      : captureStatus === "live" && deckLive
        ? "air"
        : captureStatus === "blocked" || captureStatus === "busy"
          ? "stall"
          : "standby";

  return (
    <header className="holo-header sticky top-0 z-50 isolate">
      <div className="flex flex-col gap-1.5 px-4 py-2 sm:px-5">
        <div className="flex items-center gap-3">
          <div className="flex shrink-0 items-center gap-2.5">
            <span className="holo-mark grid size-8 place-items-center rounded-md font-display text-sm font-extrabold">
              Q
            </span>
            <div>
              <p className="font-display text-[18px] font-extrabold leading-none tracking-tight text-fg">
                Retina Deck
              </p>
              <p className="mt-1 font-mono text-[10px] tracking-[0.2em] text-subtle-foreground uppercase">
                local switcher
              </p>
            </div>
          </div>
          <HoloTally mode={tallyMode} />
          <span
            className="hidden font-mono text-[10px] tracking-[0.18em] text-subtle-foreground uppercase sm:inline"
            data-take={takeCount}
          >
            Take {String(takeCount).padStart(3, "0")}
          </span>
          <span className="hidden font-mono text-[10px] tracking-[0.16em] text-photon uppercase lg:inline">
            {stageMode === "replay" ? "PVW clip" : "PGM hdmi"}
          </span>
          <BroadcastClock />

          <nav className="hidden min-w-0 rounded-lg bg-subtle/80 p-1 shadow-[var(--shadow-border)] md:flex">
            {GLASSES.map((g) => (
              <GlassNavLink
                key={g.href}
                href={g.href}
                label={g.label}
                pathname={active}
                offApp={"offApp" in g && g.offApp}
              />
            ))}
          </nav>

          <div className="ml-auto flex shrink-0 items-center gap-2">
            <div className="flex gap-1" data-mode-bar="hdmi">
              <button
                type="button"
                data-action="stage-live"
                aria-pressed={stageMode === "live"}
                className={cn(
                  "stream-key inline-flex h-10 min-w-16 items-center justify-center px-3 font-mono text-[11px] font-extrabold tracking-[0.14em]",
                  stageMode === "live" ? "stream-key-live" : "text-muted-foreground",
                )}
                onClick={() => goLive()}
              >
                <span className="mr-1 text-[9px] opacity-50">01</span>
                LIVE
              </button>
              <button
                type="button"
                data-action="stage-replay"
                aria-pressed={stageMode === "replay"}
                disabled={!lastClipUrl}
                className={cn(
                  "stream-key inline-flex h-10 min-w-16 items-center justify-center px-3 font-mono text-[11px] font-extrabold tracking-[0.14em]",
                  stageMode === "replay" ? "stream-key-live" : "text-muted-foreground",
                )}
                onClick={() => goReplay()}
              >
                <span className="mr-1 text-[9px] opacity-50">02</span>
                REPLAY
              </button>
            </div>
            <Button
              size="sm"
              data-action="make-hdmi-clip"
              className="stream-key stream-key-clip min-w-[11rem] font-mono text-[11px] font-extrabold tracking-[0.08em]"
              disabled={clipBusy}
              onClick={() => void requestHdmiClip()}
            >
              {clipBusy ? "Encoding…" : <><span className="mr-1 text-[9px] opacity-60">03</span>Clip 30s</>}
            </Button>
            {captureStatus !== "live" ? (
              <Button
                size="sm"
                data-action="arm-hdmi"
                className="stream-key font-mono text-[11px] font-extrabold tracking-[0.08em]"
                onClick={() => void armCapture()}
                disabled={captureStatus === "arming"}
              >
                {captureStatus === "arming" ? "Arming…" : "Arm HDMI"}
              </Button>
            ) : null}
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex items-center gap-2 font-mono text-[11px] tracking-wide text-muted-foreground uppercase">
            <span className={cn("size-1.5 shrink-0 rounded-full", dot)} />
            <span className="truncate" data-pll={pllLock ? "lock" : "open"}>
              {pllLock ? "PLL lock" : "PLL open"} · {status}
            </span>
            <span className="hidden min-w-0 items-center gap-2 sm:inline-flex">
              {sit ? <span className="truncate text-subtle-foreground">· {sit}</span> : null}
              <LockbugStrip className="truncate" />
            </span>
          </div>
          <div className="flex flex-wrap gap-x-3 font-mono text-[10px] tracking-wide text-subtle-foreground uppercase">
            <span data-pad={padConnected ? "live" : "wait"} className={padConnected ? "text-live" : ""}>
              {padText}
            </span>
            <span data-capture={captureStatus} className={captureStatus === "live" ? "text-live" : captureError ? "text-veto" : ""}>
              {hdmiText}
            </span>
            <span data-monitor={deckLive ? "live" : "wait"} className={deckLive ? "text-live" : ""}>
              {deckLive ? "MONITOR LIVE" : "MONITOR WAIT"}
            </span>
            <span data-vlm={vlmLocked ? "lock" : "wait"} className={vlmLocked ? "text-live" : ""}>
              {vlmLocked ? "VLM LOCK" : "VLM WAIT"}
            </span>
            <span data-sync={pllLock ? "lock" : "open"} className={pllLock ? "text-sync" : ""}>
              SYNC {syncLagMs}ms{bindKind ? ` · ${bindKind}` : ""}
            </span>
          </div>
          <nav className="flex flex-wrap gap-1 md:hidden">
            {GLASSES.map((g) => (
              <GlassNavLink
                key={g.href}
                href={g.href}
                label={g.label}
                pathname={active}
                compact
                offApp={"offApp" in g && g.offApp}
              />
            ))}
          </nav>
        </div>
      </div>
    </header>
  );
}
