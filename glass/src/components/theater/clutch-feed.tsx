import { useEffect, useRef, useState } from "react";
import { useRouterState } from "@tanstack/react-router";
import { momentPlayHref } from "@/lib/coupling/clip";
import { silenceScorePair } from "@/lib/coupling/honesty-health";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

function isTheaterPath(pathname: string): boolean {
  return pathname === "/deck.html" || pathname.endsWith("/deck.html") || pathname === "deck.html";
}

/** Play-by-play tape. Newest at top; the list scrolls so nothing is cropped by the viewport. */
export function ClutchFeed() {
  const clutch = useTheater((s) => s.clutch);
  const moments = useTheater((s) => s.moments);
  const lastClipUrl = useTheater((s) => s.lastClipUrl);
  const playClip = useTheater((s) => s.playClip);
  const note = useTheater((s) => s.matchAgent);
  const live = clutch.kind !== "quiet";
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const theaterPeek = isTheaterPath(pathname);

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
    if (!initRef.current) {
      initRef.current = true;
      for (const m of moments) seenRef.current.add(m.key);
      return;
    }
    if (!top || seenRef.current.has(top.key)) return;
    for (const m of moments) seenRef.current.add(m.key);
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
  useEffect(() => {
    if (!landLicensed) {
      setLandKey(null);
    }
  }, [landLicensed]);

  const feedMode = theaterPeek ? "dock" : "rail";
  const landFlash = landLicensed && landKey && moments[0] && moments[0].key === landKey ? moments[0].path : undefined;
  const shown = moments.slice(0, 32);
  const heat = Math.round(Math.max(clutch.score, 0) * 100);

  return (
    <section
      data-feed={feedMode}
      data-land={landFlash || undefined}
      className="clutch-feed holo-plate flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl"
    >
      <header className="clutch-feed-head shrink-0 px-3 pt-3 pb-2 sm:px-3.5">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="font-mono text-[10px] tracking-[0.18em] text-muted-foreground uppercase">
            Play-by-play
          </h2>
          <span className="font-mono text-[10px] tabular-nums text-subtle-foreground">
            {String(moments.length).padStart(2, "0")}
            <span className="mx-1.5 text-border">/</span>
            <span className={live ? "text-live" : ""}>
              {live ? clutch.label : "quiet"}
            </span>
          </span>
        </div>
        <div className="clutch-feed-meter mt-2 h-[3px] w-full overflow-hidden bg-bg" aria-hidden>
          <div
            className={cn("h-full transition-[width] duration-300", live ? "bg-live" : "bg-fast/70")}
            style={{ width: `${heat}%` }}
          />
        </div>
      </header>

      {note ? (
        <article
          data-match-agent="licensed"
          data-path={note.path}
          className={cn(
            "clutch-now mx-3 mb-2 shrink-0 px-3 py-2 sm:mx-3.5",
            note.path === "confirm" ? "clutch-now-confirm" : "clutch-now-fast",
          )}
        >
          <span className="font-mono text-[9px] tracking-[0.16em] uppercase opacity-80">
            now · path={note.path}
          </span>
          <p className="mt-1 text-[13px] leading-snug text-fg">{silenceScorePair(note.text, paintBlocked)}</p>
        </article>
      ) : null}

      {moments.length === 0 && !note ? (
        <p className="clutch-feed-empty px-3 pb-3 text-[13px] leading-relaxed text-muted-foreground sm:px-3.5">
          Snap, score lock, and fast chat land here as a tape. Scroll the tape — nothing is cropped.
        </p>
      ) : null}

      {shown.length > 0 ? (
        <div
          ref={listRef}
          className="clutch-feed-tape min-h-0 flex-1 overflow-y-auto overscroll-y-contain px-2 pb-3 sm:px-2.5"
          tabIndex={0}
          aria-label="Play-by-play tape"
        >
          {shown.map((e) => {
            const href = momentPlayHref(e, lastClipUrl);
            const landAttr = landLicensed && e.key === landKey ? e.path || undefined : undefined;
            const title = silenceScorePair(e.title, paintBlocked);
            const path = e.path || "none";
            const className = cn("clutch-row clutch-beat", href ? "cursor-pointer" : "");
            const inner = (
              <>
                <span className="clutch-beat-tick" data-path={path} aria-hidden />
                <span className="clutch-beat-body">
                  <span className="clutch-beat-meta">
                    {e.path ? e.path : "moment"} · {e.clock}
                    {href ? " · on picture" : ""}
                  </span>
                  <span className="clutch-beat-title">
                    {e.icon === "🎬" || href ? "▶ " : ""}
                    {title}
                  </span>
                </span>
              </>
            );
            return href ? (
              <button
                key={e.key}
                type="button"
                data-clutch-path={path}
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
                data-clutch-path={path}
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
