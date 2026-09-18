import { useEffect, useRef, useState } from "react";
import { useRouterState } from "@tanstack/react-router";
import { momentPlayHref } from "@/lib/coupling/clip";
import { silenceScorePair } from "@/lib/coupling/honesty-health";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

function isTheaterPath(pathname: string): boolean {
  return pathname === "/deck.html" || pathname.endsWith("/deck.html") || pathname === "deck.html";
}

/** Clutch / chat moments. Clicking a clip only asks the HDMI stage to replay. */
export function ClutchFeed() {
  const clutch = useTheater((s) => s.clutch);
  const moments = useTheater((s) => s.moments);
  const lastClipUrl = useTheater((s) => s.lastClipUrl);
  const playClip = useTheater((s) => s.playClip);
  const note = useTheater((s) => s.matchAgent);
  const live = clutch.kind !== "quiet";
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const theaterPeek = isTheaterPath(pathname);

  // Chrome motion license (fail-closed): a freshly landed row may play the
  // one-shot brass/aperture land envelope only when the glass is licensed —
  // widgetsOk + board lock + real scores. HOLD / unlocked = iron, no motion.
  const livePaint = useTheater((s) => s.livePaint);
  const sameSeq = useTheater((s) => s.sameSeq);
  const planeDim = useTheater((s) => s.planeDim);
  const boardLocked = useTheater((s) => s.boardLocked);
  const homeScore = useTheater((s) => s.homeScore);
  const awayScore = useTheater((s) => s.awayScore);
  const confirm = useTheater((s) => s.confirm);
  const honesty = useTheater((s) => s.honesty);
  const paintBlocked = honesty.paintBlocked;
  const darkTheater = planeDim || !livePaint || !sameSeq || honesty.state === "dark";
  const licensed =
    livePaint &&
    sameSeq &&
    !planeDim &&
    boardLocked &&
    !paintBlocked &&
    homeScore != null &&
    awayScore != null &&
    (confirm != null || boardLocked);
  const landLicensed = licensed && !darkTheater;

  const seenRef = useRef<Set<string>>(new Set());
  const initRef = useRef(false);
  const [landKey, setLandKey] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const top = moments[0];
    // Do not animate rows already on the rail at first paint (page refresh).
    if (!initRef.current) {
      initRef.current = true;
      for (const m of moments) seenRef.current.add(m.key);
      return;
    }
    if (!top || seenRef.current.has(top.key)) return;
    for (const m of moments) seenRef.current.add(m.key);
    // Presence: always scroll newest into view so the dock is readable.
    // Glow/land flash stays fail-closed (licensed path only).
    listRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    if (landLicensed && (top.path === "fast" || top.path === "confirm")) {
      const key = top.key;
      setLandKey(key);
      const landId = window.setTimeout(() => setLandKey((k) => (k === key ? null : k)), 260);
      return () => {
        window.clearTimeout(landId);
      };
    }
  }, [moments, landLicensed]);
  // Iron is instant: the moment the license drops, kill any in-flight row glow
  // so HOLD can never keep a bloom on the plate (do not wait out the one-shot).
  useEffect(() => {
    if (!landLicensed) {
      setLandKey(null);
    }
  }, [landLicensed]);

  // Theater uses a readable dock (not a 48px slit). HOME keeps full rail.
  const feedMode = theaterPeek ? "dock" : "rail";
  const landFlash = landLicensed && landKey && moments[0] && moments[0].key === landKey ? moments[0].path : undefined;
  const shown = moments.slice(0, theaterPeek ? 6 : 8);

  return (
    <section
      data-feed={feedMode}
      data-land={landFlash || undefined}
      className="clutch-feed holo-plate flex min-h-0 flex-1 flex-col gap-2 overflow-hidden rounded-xl p-3 sm:p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Clutch feed
        </h2>
        <span className="font-mono text-[10px] tabular-nums text-subtle-foreground">
          {String(moments.length).padStart(2, "0")}
          <span className="mx-1.5">·</span>
          <span className={live ? "text-live" : ""}>
            {live ? clutch.label : "WATCHING"} · {clutch.score.toFixed(2)}
          </span>
        </span>
      </div>
      <div className="clutch-feed-meter h-1 w-full overflow-hidden rounded-full bg-bg">
        <div
          className="h-full bg-live transition-[width] duration-300"
          style={{ width: `${Math.round(Math.max(clutch.score, 0) * 100)}%` }}
        />
      </div>
      {note ? (
        <article
          data-match-agent="licensed"
          data-path={note.path}
          className={cn(
            "flex min-h-14 w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left shadow-[var(--shadow-border)]",
            note.path === "confirm"
              ? "border border-live/40 bg-live/10 text-live"
              : "border border-fast/45 bg-fast/10 text-fast",
          )}
        >
          <span className="min-w-0 truncate text-xs">{silenceScorePair(note.text, paintBlocked)}</span>
          <span
            data-path-chip={note.path}
            className={cn(
              "shrink-0 font-mono text-[10px] tracking-wide uppercase",
              note.path === "confirm" ? "text-live" : "text-fast",
            )}
          >
            path={note.path}
          </span>
        </article>
      ) : null}
      {moments.length === 0 && !note ? (
        <p className="clutch-feed-empty text-xs text-muted-foreground">
          Fast chat and score locks land here. Clip chips replay on the HDMI stage — LIVE kills the player.
        </p>
      ) : null}
      {shown.length > 0 ? (
        <div ref={listRef} className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-y-contain">
          {shown.map((e) => {
            const href = momentPlayHref(e, lastClipUrl);
            const landAttr = landLicensed && e.key === landKey ? e.path || undefined : undefined;
            const title = silenceScorePair(e.title, paintBlocked);
            const className = cn(
              "clutch-row flex min-h-14 w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left shadow-[var(--shadow-border)]",
              href ? "cursor-pointer hover:opacity-90" : "",
              e.path === "confirm"
                ? "border border-live/40 bg-live/10 text-live"
                : e.path === "fast"
                  ? "border border-fast/45 bg-fast/10 text-fast"
                  : "bg-bg/50 text-fg",
            );
            const inner = (
              <>
                <span className="min-w-0">
                  <span className="block font-mono text-[10px] tracking-wide text-subtle-foreground uppercase">
                    {e.path ? `[${e.path}]` : "moment"} · {e.clock}
                    {href ? " · play" : ""}
                  </span>
                  <span className="block truncate text-xs">
                    {e.icon === "🎬" || href ? "🎬 " : ""}
                    {title}
                  </span>
                </span>
                {href ? (
                  <span className="shrink-0 font-mono text-[10px] tracking-wide text-live uppercase">
                    on stage
                  </span>
                ) : null}
              </>
            );
            return href ? (
              <button
                key={e.key}
                type="button"
                data-clutch-path={e.path || "none"}
                data-land={landAttr}
                data-landed={landAttr ? "1" : undefined}
                data-clip-href={href}
                className={className}
                onPointerDown={(ev) => ev.stopPropagation()}
                onClick={() => playClip(href, e.name)}
              >
                {inner}
              </button>
            ) : (
              <article
                key={e.key}
                data-clutch-path={e.path || "none"}
                data-land={landAttr}
                data-landed={landAttr ? "1" : undefined}
                className={className}
              >
                {inner}
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
