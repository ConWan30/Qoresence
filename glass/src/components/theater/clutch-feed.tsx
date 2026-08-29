import { useEffect, useRef, useState } from "react";
import { momentPlayHref } from "@/lib/coupling/clip";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

/** Clutch / chat moments. Clicking a clip only asks the HDMI stage to replay. */
export function ClutchFeed() {
  const clutch = useTheater((s) => s.clutch);
  const moments = useTheater((s) => s.moments);
  const lastClipUrl = useTheater((s) => s.lastClipUrl);
  const playClip = useTheater((s) => s.playClip);
  const note = useTheater((s) => s.matchAgent);
  const live = clutch.kind !== "quiet";

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
  const licensed =
    livePaint && sameSeq && !planeDim && boardLocked && homeScore != null && awayScore != null && (confirm != null || boardLocked);

  const seenRef = useRef<Set<string>>(new Set());
  const initRef = useRef(false);
  const [landKey, setLandKey] = useState<string | null>(null);
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
    // Only a licensed, path-tinted row lands; unlicensed / no-path stays iron.
    if (licensed && (top.path === "fast" || top.path === "confirm")) {
      const key = top.key;
      setLandKey(key);
      const id = window.setTimeout(() => setLandKey((k) => (k === key ? null : k)), 260);
      return () => window.clearTimeout(id);
    }
  }, [moments, licensed]);
  // Iron is instant: the moment the license drops, kill any in-flight row glow
  // so HOLD can never keep a bloom on the plate (do not wait out the one-shot).
  useEffect(() => {
    if (!licensed) setLandKey(null);
  }, [licensed]);

  return (
    <section className="holo-plate flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto rounded-xl p-3 sm:p-4">
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
      <div className="h-1 w-full overflow-hidden rounded-full bg-bg">
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
          <span className="min-w-0 truncate text-xs">{note.text}</span>
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
        <p className="text-xs text-muted-foreground">
          Fast chat and score locks land here. Clip chips replay on the HDMI stage — LIVE kills the player.
        </p>
      ) : null}
      {moments.length > 0 ? (
        <div className="flex flex-col gap-2">
          {moments.slice(0, 8).map((e) => {
            const href = momentPlayHref(e, lastClipUrl);
            const landAttr = licensed && e.key === landKey ? e.path || undefined : undefined;
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
                    {e.title}
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
                data-clip-href={href}
                className={className}
                onPointerDown={(ev) => ev.stopPropagation()}
                onClick={() => playClip(href, e.name)}
              >
                {inner}
              </button>
            ) : (
              <article key={e.key} data-clutch-path={e.path || "none"} data-land={landAttr} className={className}>
                {inner}
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
