import { clipHref } from "@/lib/coupling/clip";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

export function ClutchFeed() {
  const clutch = useTheater((s) => s.clutch);
  const moments = useTheater((s) => s.moments);
  const lastClipUrl = useTheater((s) => s.lastClipUrl);
  const lastClipName = useTheater((s) => s.lastClipName);
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
          Watching HDMI + DualSense + scorebug. Fast chat, score locks, and clips land here.
        </p>
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {moments.slice(0, 8).map((e) => {
            const href = e.url ? clipHref(e.url) : "";
            const className = cn(
              "flex min-h-16 w-56 shrink-0 flex-col justify-center rounded-lg px-3 py-2 shadow-[var(--shadow-border)]",
              href ? "cursor-pointer no-underline hover:opacity-90" : "",
              e.path === "confirm"
                ? "border border-live/40 bg-live/10 text-live"
                : e.path === "fast"
                  ? "border border-fast/45 bg-fast/10 text-fast"
                  : "bg-bg/50 text-fg",
            );
            const inner = (
              <>
                <p className="font-mono text-[10px] tracking-wide text-subtle-foreground uppercase">
                  {e.path ? `[${e.path}]` : "moment"} · {e.clock}
                </p>
                <p className="truncate text-xs">
                  {e.icon === "🎬" || href ? "🎬 " : ""}
                  {e.title}
                </p>
                {e.reason ? (
                  <p className="truncate font-mono text-[10px] text-subtle-foreground">{e.reason}</p>
                ) : null}
              </>
            );
            return href ? (
              <a
                key={e.key}
                href={href}
                target="_blank"
                rel="noreferrer"
                data-clutch-path={e.path || "none"}
                data-clip-href={href}
                className={className}
              >
                {inner}
              </a>
            ) : (
              <article key={e.key} data-clutch-path={e.path || "none"} className={className}>
                {inner}
              </article>
            );
          })}
        </div>
      )}
      {lastClipUrl ? (
        <a
          href={clipHref(lastClipUrl)}
          target="_blank"
          rel="noreferrer"
          data-clip-href={clipHref(lastClipUrl)}
          className="font-mono text-[10px] tracking-wide text-live uppercase"
        >
          last clip · {lastClipName || lastClipUrl.split("/").pop()}
        </a>
      ) : null}
    </section>
  );
}
