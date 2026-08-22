import { Link, useRouterState } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";
import { ClipBar } from "./clip-rack";
import { LockbugStrip } from "./lockbug-strip";

const GLASSES = [
  { href: "/", label: "Home" },
  { href: "/deck.html", label: "Theater" },
  { href: "/overlay.html", label: "Lens" },
  { href: "/studio.html", label: "Foundry" },
  { href: "/mobile.html", label: "Mobile" },
] as const;

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

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-surface/90 backdrop-blur-xl">
    <div className="flex flex-wrap items-center gap-3 px-4 py-3 sm:gap-4 sm:px-5">
      <div className="flex items-center gap-2.5">
        <span className="grid size-8 place-items-center rounded-lg border border-live/50 font-mono text-xs font-extrabold text-live shadow-[var(--shadow-live)]">
          Q
        </span>
        <div>
          <p className="font-display text-[15px] font-extrabold leading-none tracking-tight text-fg">Retina Deck</p>
          <p className="mt-1 font-mono text-[10px] tracking-[0.14em] text-subtle-foreground uppercase">
            observation plane
          </p>
        </div>
      </div>

      <nav className="flex flex-wrap rounded-full bg-bg p-1 shadow-[var(--shadow-border)]">
        {GLASSES.map((g) => {
          const on =
            g.href === "/"
              ? active === "/" || active === "home"
              : active === g.href || active === g.label.toLowerCase() || pathname === g.href;
          return (
            <Link
              key={g.href}
              to={g.href}
              className={cn(
                "inline-flex h-9 min-w-16 items-center justify-center rounded-full px-3 text-xs font-medium",
                on ? "bg-live text-primary-foreground shadow-[var(--shadow-live)]" : "text-muted-foreground",
              )}
            >
              {g.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center gap-2 font-mono text-[11px] tracking-wide text-muted-foreground uppercase">
          <span className={cn("size-1.5 shrink-0 rounded-full", dot)} />
          <span className="truncate" data-pll={pllLock ? "lock" : "open"}>
            {pllLock ? "PLL lock" : "PLL open"} · {status}
          </span>
          <span className="hidden items-center gap-2 sm:inline-flex">
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
      </div>

      {captureStatus !== "live" ? (
        <Button
          size="sm"
          data-action="arm-hdmi"
          onClick={() => void armCapture()}
          disabled={captureStatus === "arming"}
        >
          {captureStatus === "arming" ? "Arming…" : "Arm HDMI"}
        </Button>
      ) : null}
    </div>
    <ClipBar />
    </header>
  );
}
