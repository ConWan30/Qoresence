import { useEffect } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { pictureLagMs, syncChipText } from "@/lib/coupling/pad-sync";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";
import { HdmiMark } from "./hdmi-mark";
import { HoloTally } from "./holo-tally";
import { LockbugStrip } from "./lockbug-strip";
import { tallyState } from "@/lib/coupling/signal-meter";
import { SignalMeters } from "./signal-meters";

const GLASSES = [
  { href: "/", label: "Home" },
  { href: "/deck.html", label: "Theater" },
  { href: "/session.html", label: "Session", offApp: true },
  { href: "/overlay.html", label: "Lens" },
  { href: "/studio.html", label: "Foundry" },
  { href: "/mobile.html", label: "Mobile" },
] as const;

const GAMER_GLASSES = [
  { href: "/deck.html", label: "Theater" },
  { href: "/session.html", label: "Session", offApp: true },
] as const;

function glassOn(href: string, label: string, pathname: string) {
  if (href === "/") return pathname === "/" || pathname === "home";
  return pathname === href || pathname === label.toLowerCase();
}

function GlassNavLink({
  href,
  label,
  pathname,
  offApp,
}: {
  href: string;
  label: string;
  pathname: string;
  offApp?: boolean;
}) {
  const on = glassOn(href, label, pathname);
  const className = cn(on && "stream-key-live");
  if (offApp) {
    return (
      <a href={href} className={className} aria-current={on ? "page" : undefined}>
        {label}
      </a>
    );
  }
  return (
    <Link
      to={href as "/" | "/deck.html" | "/overlay.html" | "/studio.html" | "/mobile.html"}
      className={className}
      aria-current={on ? "page" : undefined}
    >
      {label}
    </Link>
  );
}

export function CommandBar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const isSessionRoute = pathname === "/session.html";
  const isGamerRoute = pathname === "/deck.html" || pathname === "/session.html";
  const hdmi = useTheater((s) => s.hdmi);
  const pllLock = useTheater((s) => s.pllLock);
  const boardLine = useTheater((s) => s.boardLine);
  const situation = useTheater((s) => s.situation);
  const gameTitle = useTheater((s) => s.gameTitle);
  const captureStatus = useTheater((s) => s.captureStatus);
  const captureError = useTheater((s) => s.captureError);
  const deckLive = useTheater((s) => s.deckLive);
  const syncLagMs = useTheater((s) => s.syncLagMs);
  const videoAgeS = useTheater((s) => s.videoAgeS);
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

  const livePaint = useTheater((s) => s.livePaint);
  const sameSeq = useTheater((s) => s.sameSeq);
  const planeDim = useTheater((s) => s.planeDim);
  const boardLocked = useTheater((s) => s.boardLocked);
  const homeScore = useTheater((s) => s.homeScore);
  const awayScore = useTheater((s) => s.awayScore);
  const confirm = useTheater((s) => s.confirm);
  const meter = useTheater((s) => s.meter);
  const meterRate = useTheater((s) => s.meterRate);
  const widgetsOk = livePaint && sameSeq && !planeDim;
  // Same gate as LockbugStrip: widgetsOk AND boardLocked AND scores present
  const licensed = widgetsOk && boardLocked && homeScore != null && awayScore != null && (confirm != null || boardLocked);
  // Never paint unlicensed situation/boardLine (tonight's local_hud 35-22 vs picture 0-0)
  const sit = licensed && (situation || boardLine)
    ? [gameTitle, situation || boardLine].filter(Boolean).join(" · ")
    : hdmi === "menu"
      ? "menu"
      : "";

  const syncLabel = syncChipText(pictureLagMs(videoAgeS, 0, pllLock && deckLive ? syncLagMs : 0));
  const joinLabel = licensed && bindKind && syncLabel !== "UNBOUND" ? `${syncLabel} · ${bindKind}` : syncLabel;

  const active = pathname;
  // Tally is the backend's word, not the browser's: /health video paint +
  // same_seq + fresh age + frames advancing. Replay is never LIVE.
  const tally =
    stageMode === "replay" ? "hold" : tallyState(meter, { advancing: meterRate == null ? null : meterRate > 0 });
  const tallyWhy =
    tally === "live"
      ? "Deck /health: frames advancing, paint on, same seq"
      : meter.paintReason
        ? `Deck /health: ${meter.paintReason}`
        : captureError || "Deck /health: no frame";
  const routeLabel =
    pathname === "/session.html"
      ? "Session"
      : pathname === "/studio.html"
        ? "Foundry"
        : pathname === "/mobile.html"
          ? "Mobile"
          : "Theater";

  return (
    <header className="holo-header deck-bar sticky top-0 z-50 isolate" data-route={routeLabel.toLowerCase()}>
      <a
        href="#hdmi-stage"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[60] focus:bg-surface focus:px-3 focus:py-2 focus:text-live"
      >
        Skip to picture
      </a>
      <div className="deck-bar-row">
        <div className="deck-brand">
          <HdmiMark size={30} className="size-[30px]" />
          <div className="min-w-0">
            <p className="deck-wordmark">Qoresence</p>
            <p className="deck-kicker">Sight Glass · {routeLabel}</p>
          </div>
        </div>

        <nav className="glass-nav min-w-0" aria-label="Glasses">
          {(isGamerRoute ? GAMER_GLASSES : GLASSES).map((g) => (
            <GlassNavLink
              key={g.href}
              href={g.href}
              label={g.label}
              pathname={active}
              offApp={"offApp" in g && g.offApp}
            />
          ))}
        </nav>

        {!isSessionRoute && (
          <div className="deck-tally">
            <HoloTally state={tally} title={tallyWhy} />
            <span className="deck-take" data-take={takeCount}>
              Take {String(takeCount).padStart(3, "0")}
            </span>
            <span className="deck-take hidden min-[1440px]:inline">{stageMode === "replay" ? "PVW clip" : "PGM hdmi"}</span>
          </div>
        )}

        {!isSessionRoute && (
          <div className="deck-keys" data-mode-bar="hdmi">
            <button
              type="button"
              data-action="stage-live"
              aria-pressed={stageMode === "live"}
              className={cn("stream-key deck-key", stageMode === "live" && "stream-key-live")}
              onClick={() => goLive()}
            >
              <span className="deck-key-n">01</span>
              Live
            </button>
            <button
              type="button"
              data-action="stage-replay"
              aria-pressed={stageMode === "replay"}
              disabled={!lastClipUrl}
              className={cn("stream-key deck-key", stageMode === "replay" && "stream-key-live")}
              onClick={() => goReplay()}
            >
              <span className="deck-key-n">02</span>
              Replay
            </button>
            <Button
              size="sm"
              data-action="make-hdmi-clip"
              className="stream-key stream-key-clip deck-key deck-key-clip"
              disabled={clipBusy}
              onClick={() => void requestHdmiClip()}
            >
              {clipBusy ? "Encoding…" : <><span className="deck-key-n">03</span>Clip 30s</>}
            </Button>
            {captureStatus !== "live" ? (
              <Button
                size="sm"
                data-action="arm-hdmi"
                className="stream-key deck-key"
                onClick={() => void armCapture()}
                disabled={captureStatus === "arming"}
              >
                {captureStatus === "arming" ? "Arming…" : "Arm HDMI"}
              </Button>
            ) : null}
          </div>
        )}
      </div>

      <div className="deck-bar-sub">
        <SignalMeters syncLabel={joinLabel} compact={isSessionRoute} />
        <div className="deck-board" data-hdmi={hdmi}>
          <span className="meter-label">Board</span>
          <LockbugStrip className="truncate" pulse />
          {sit ? <span className="deck-sit truncate">{sit}</span> : null}
        </div>
      </div>
    </header>
  );
}
