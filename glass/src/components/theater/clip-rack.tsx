import { CLIP_RACK, clipHref } from "@/lib/coupling/clip";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

function clipStamp(name: string, mtime: number): string {
  const m = name.match(/hdmi_clip_(\d{8})_(\d{6})/i);
  if (m) {
    const t = m[2];
    return `${t.slice(0, 2)}:${t.slice(2, 4)}:${t.slice(4, 6)}`;
  }
  if (mtime > 0) {
    const d = new Date(mtime * 1000);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  return "";
}

/** Disk-backed HDMI clip rack — large play targets, not moment chips. */
export function ClipRack() {
  const clips = useTheater((s) => s.hdmiClips);
  const lastClipUrl = useTheater((s) => s.lastClipUrl);
  const lastClipName = useTheater((s) => s.lastClipName);
  const playClip = useTheater((s) => s.playClip);
  const playerSrc = lastClipUrl ? clipHref(lastClipUrl) : "";
  const active = lastClipName || (playerSrc.split("/").pop() ?? "");

  return (
    <section
      data-clip-rack={CLIP_RACK}
      className="relative z-20 flex min-h-0 flex-col gap-3 rounded-xl bg-surface p-3 shadow-[var(--shadow-border)] pointer-events-auto sm:p-4 xl:sticky xl:top-4 xl:max-h-[calc(100dvh-5.5rem)]"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          HDMI clips
        </h2>
        <span className="font-mono text-[10px] tabular-nums text-subtle-foreground">
          {String(clips.length).padStart(2, "0")} on disk
        </span>
      </div>

      {playerSrc ? (
        <video
          key={playerSrc}
          src={playerSrc}
          controls
          playsInline
          muted
          autoPlay
          preload="metadata"
          data-clip-player="rack"
          className="aspect-video w-full rounded-lg bg-black"
        />
      ) : (
        <div className="grid aspect-video w-full place-items-center rounded-lg bg-bg px-4 text-center text-sm text-muted-foreground">
          Clips land here as ClutchBot writes <span className="font-mono">hdmi_clip_*.mp4</span>
        </div>
      )}

      {playerSrc ? (
        <p className="font-mono text-[10px] tracking-wide text-live uppercase">
          playing · {active}
        </p>
      ) : null}

      {clips.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No files in <span className="font-mono">clips/</span> yet. Keep playing — the rack
          polls the Deck every second.
        </p>
      ) : (
        <ul className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
          {clips.slice(0, 16).map((c) => {
            const on = c.name === active;
            const stamp = clipStamp(c.name, c.mtime);
            return (
              <li key={c.name}>
                <button
                  type="button"
                  data-clip-href={c.href}
                  data-clip-name={c.name}
                  className={cn(
                    "flex min-h-16 w-full items-center gap-3 rounded-xl px-3 py-2 text-left shadow-[var(--shadow-border)]",
                    on
                      ? "bg-live text-primary-foreground shadow-[var(--shadow-live)]"
                      : "bg-bg text-fg hover:shadow-[var(--shadow-border-hover)]",
                  )}
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    playClip(c.href, c.name);
                  }}
                >
                  <span
                    className={cn(
                      "grid size-12 shrink-0 place-items-center rounded-lg font-display text-lg font-extrabold",
                      on ? "bg-primary-foreground text-primary" : "bg-live text-primary-foreground",
                    )}
                  >
                    ▶
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{c.name}</span>
                    <span
                      className={cn(
                        "block font-mono text-[10px] tracking-wide uppercase",
                        on ? "text-primary-foreground/70" : "text-subtle-foreground",
                      )}
                    >
                      {stamp ? `${stamp} · ` : ""}
                      play
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
