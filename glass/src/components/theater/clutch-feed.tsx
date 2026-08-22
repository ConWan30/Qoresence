import { momentPlayHref } from "@/lib/coupling/clip";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

/** Clutch / chat moments. Clicking a clip only asks the HDMI stage to replay. */
export function ClutchFeed() {
  const clutch = useTheater((s) => s.clutch);
  const moments = useTheater((s) => s.moments);
  const lastClipUrl = useTheater((s) => s.lastClipUrl);
  const playClip = useTheater((s) => s.playClip);
  const live = clutch.kind !== "quiet";

  return (
    <section className="flex flex-col gap-2 rounded-xl bg-surface p-3 shadow-[var(--shadow-border)] sm:p-4">
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
      {moments.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Fast chat and score locks land here. Clip chips replay on the HDMI stage — LIVE kills the player.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {moments.slice(0, 8).map((e) => {
            const href = momentPlayHref(e, lastClipUrl);
            const className = cn(
              "flex min-h-14 w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left shadow-[var(--shadow-border)]",
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
                data-clip-href={href}
                className={className}
                onPointerDown={(ev) => ev.stopPropagation()}
                onClick={() => playClip(href, e.name)}
              >
                {inner}
              </button>
            ) : (
              <article key={e.key} data-clutch-path={e.path || "none"} className={className}>
                {inner}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
