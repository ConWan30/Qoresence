import { useCallback, useState, type PointerEvent } from "react";
import { CommandBar } from "@/components/theater/command-bar";
import { SessionNow } from "./session-now";
import { SessionStory } from "./session-story";
import { SessionRecap } from "./session-recap";
import { cn } from "@/lib/utils";

type SessionTab = "now" | "story" | "recap";

/** Phosphor Shell §2 — Session Theater (Now | Story | Recap). */
export function SessionTheater() {
  const [tab, setTab] = useState<SessionTab>("now");

  const onPrism = useCallback((e: PointerEvent<HTMLElement>) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / Math.max(1, r.width) - 0.5) * 2;
    const y = ((e.clientY - r.top) / Math.max(1, r.height) - 0.5) * 2;
    e.currentTarget.style.setProperty("--holo-x", x.toFixed(3));
    e.currentTarget.style.setProperty("--holo-y", y.toFixed(3));
    document.body.style.setProperty("--holo-x", x.toFixed(3));
    document.body.style.setProperty("--holo-y", y.toFixed(3));
  }, []);

  return (
    <main className="holo-deck min-h-dvh bg-bg text-fg" onPointerMove={onPrism}>
      <CommandBar />
      <div className="mx-auto max-w-[88rem] px-4 py-3 sm:px-5 sm:py-3">
        <div className="mb-4 flex items-center gap-3">
          <nav className="flex items-center gap-1.5 rounded-lg bg-surface/60 p-1 shadow-[var(--shadow-border)]">
            {(["now", "story", "recap"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={cn(
                  "rounded-md px-3 py-1.5 font-mono text-[10px] tracking-[0.14em] uppercase transition-colors",
                  tab === t
                    ? "bg-live/15 text-live"
                    : "text-muted-foreground hover:bg-surface hover:text-fg",
                )}
              >
                {t}
              </button>
            ))}
          </nav>
        </div>

        {tab === "now" && <SessionNow />}
        {tab === "story" && <SessionStory />}
        {tab === "recap" && <SessionRecap />}
      </div>
    </main>
  );
}
