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

/** Sticky chrome under the command bar — always on screen, disk-backed ▶ tiles. */
export function ClipBar() {
  const clips = useTheater((s) => s.hdmiClips);
  const lastClipUrl = useTheater((s) => s.lastClipUrl);
  const lastClipName = useTheater((s) => s.lastClipName);
  const playClip = useTheater((s) => s.playClip);
  const playerSrc = lastClipUrl ? clipHref(lastClipUrl) : "";
  const active = lastClipName || (playerSrc.split("/").pop() ?? "");

  return (
    <div
      id="hdmi-clips"
      data-clip-rack={CLIP_RACK}
      className="relative z-30 border-t border-border bg-bg/90 px-3 py-2 pointer-events-auto sm:px-5"
    >
      <div className="flex items-center gap-2 overflow-x-auto pb-1">
        <p className="shrink-0 font-mono text-[10px] tracking-[0.14em] text-live uppercase">
          HDMI clips · {String(clips.length).padStart(2, "0")}
        </p>
        {clips.length === 0 ? (
          <p className="shrink-0 text-xs text-muted-foreground">
            waiting for <span className="font-mono">hdmi_clip_*.mp4</span> in clips/
          </p>
        ) : (
          clips.slice(0, 16).map((c) => {
            const on = c.name === active;
            const stamp = clipStamp(c.name, c.mtime);
            return (
              <button
                key={c.name}
                type="button"
                data-clip-href={c.href}
                data-clip-name={c.name}
                className={cn(
                  "flex min-h-12 min-w-52 shrink-0 items-center gap-2 rounded-xl px-3 text-left shadow-[var(--shadow-border)]",
                  on
                    ? "bg-live text-primary-foreground shadow-[var(--shadow-live)]"
                    : "bg-surface text-fg hover:shadow-[var(--shadow-border-hover)]",
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
                    "grid size-9 shrink-0 place-items-center rounded-md font-display text-sm font-extrabold",
                    on ? "bg-primary-foreground text-primary" : "bg-live text-primary-foreground",
                  )}
                >
                  ▶
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-xs font-medium">{c.name}</span>
                  <span
                    className={cn(
                      "block font-mono text-[10px] uppercase",
                      on ? "text-primary-foreground/70" : "text-subtle-foreground",
                    )}
                  >
                    {stamp ? `${stamp} · ` : ""}
                    play
                  </span>
                </span>
              </button>
            );
          })
        )}
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
          data-clip-player="bar"
          className="mt-2 max-h-48 w-full max-w-2xl rounded-lg bg-black"
        />
      ) : null}
    </div>
  );
}

/** Foundry / tall column list — same disk source as ClipBar. */
export function ClipRack() {
  const clips = useTheater((s) => s.hdmiClips);
  const lastClipName = useTheater((s) => s.lastClipName);
  const playClip = useTheater((s) => s.playClip);

  return (
    <section
      data-clip-rack={CLIP_RACK}
      className="relative z-20 flex min-h-0 flex-col gap-2 rounded-xl bg-surface p-3 shadow-[var(--shadow-border)] pointer-events-auto sm:p-4"
    >
      <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
        HDMI clips · {String(clips.length).padStart(2, "0")}
      </h2>
      {clips.length === 0 ? (
        <p className="text-xs text-muted-foreground">No hdmi_clip_*.mp4 on disk yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {clips.slice(0, 16).map((c) => {
            const on = c.name === lastClipName;
            return (
              <li key={c.name}>
                <button
                  type="button"
                  data-clip-href={c.href}
                  className={cn(
                    "flex min-h-14 w-full items-center gap-3 rounded-xl px-3 text-left shadow-[var(--shadow-border)]",
                    on ? "bg-live text-primary-foreground" : "bg-bg text-fg",
                  )}
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    playClip(c.href, c.name);
                  }}
                >
                  <span className="grid size-10 place-items-center rounded-lg bg-live text-primary-foreground">▶</span>
                  <span className="truncate text-sm">{c.name}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
