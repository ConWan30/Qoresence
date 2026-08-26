import { useState } from "react";
import { AgentRail } from "@/components/theater/agent-rail";
import { ClutchFeed } from "@/components/theater/clutch-feed";
import { ConnectCard } from "@/components/theater/connect-card";
import { SituationCard } from "@/components/theater/situation-card";
import { CouplingCard } from "@/components/theater/coupling-card";
import { HighlightDirector } from "@/components/theater/highlight-director";
import { PadSyncCard } from "@/components/theater/pad-sync-card";
import { cn } from "@/lib/utils";

export function IntelligenceChamber() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      {/* Chamber toggle button - thin ticker that peeks */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "fixed top-20 right-0 z-30 flex items-center gap-2 rounded-l-lg bg-surface/90 px-3 py-2 font-mono text-[10px] tracking-[0.14em] uppercase shadow-[var(--shadow-border)] backdrop-blur-sm transition-all",
        )}
        aria-label={isOpen ? "Close intelligence chamber" : "Open intelligence chamber"}
      >
        <span className={cn("transition-transform", isOpen ? "rotate-0" : "rotate-180")}>▶</span>
        Intel
      </button>

      {/* Chamber drawer - slides in from right */}
      <aside
        className={cn(
          "fixed top-0 right-0 z-20 h-full w-full max-w-md transform bg-bg shadow-2xl transition-transform duration-300 ease-out sm:max-w-lg",
          isOpen ? "translate-x-0" : "translate-x-full",
        )}
      >
        {/* Chamber header */}
        <div className="flex items-center justify-between border-b border-border bg-surface/50 px-4 py-3 backdrop-blur-sm">
          <h2 className="font-display text-lg font-extrabold tracking-tight text-fg">
            Intelligence Chamber
          </h2>
          <button
            type="button"
            onClick={() => setIsOpen(false)}
            className="rounded-lg px-2 py-1 font-mono text-xs text-muted-foreground hover:text-fg"
            aria-label="Close chamber"
          >
            ✕
          </button>
        </div>

        {/* Chamber content - THIS is the only place with overflow-y: auto */}
        <div className="h-[calc(100%-4rem)] overflow-y-auto px-4 py-4">
          <div className="flex flex-col gap-4">
            <HighlightDirector />
            <AgentRail />
            <ClutchFeed />
            <ConnectCard />
            <PadSyncCard />
            <SituationCard />
            <CouplingCard />
          </div>
        </div>
      </aside>

      {/* Backdrop overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-10 bg-black/50 backdrop-blur-sm"
          onClick={() => setIsOpen(false)}
          aria-hidden="true"
        />
      )}
    </>
  );
}
