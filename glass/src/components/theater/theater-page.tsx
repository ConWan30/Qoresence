import { useCallback, type PointerEvent } from "react";
import { AgentRail } from "@/components/theater/agent-rail";
import { ClutchFeed } from "@/components/theater/clutch-feed";
import { CommandBar } from "@/components/theater/command-bar";
import { ConnectCard } from "@/components/theater/connect-card";
import { SituationCard } from "@/components/theater/situation-card";
import { CouplingCard } from "@/components/theater/coupling-card";
import { HighlightDirector } from "@/components/theater/highlight-director";
import { PadSyncCard } from "@/components/theater/pad-sync-card";
import { HdmiStage } from "@/components/theater/hdmi-stage";
import { useTheaterLoop } from "@/lib/coupling/loop";

export function TheaterPage() {
  useTheaterLoop();

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
    <main className="holo-deck flex h-dvh min-h-0 flex-col overflow-hidden bg-bg text-fg" onPointerMove={onPrism}>
      <CommandBar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="mx-auto flex h-full max-w-[88rem] flex-1 flex-col overflow-y-auto px-4 py-3 sm:px-5 sm:py-3">
          <div className="grid items-start gap-3 min-[640px]:grid-cols-[minmax(0,1fr)_minmax(17.5rem,21rem)] min-[640px]:gap-4">
            <HdmiStage variant="deck" />
            <aside className="flex flex-col gap-3" data-ops-strip="director-receipt">
              <HighlightDirector />
              <AgentRail />
            </aside>
          </div>
          <div className="mt-4 grid items-start gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)] lg:gap-5">
            <ClutchFeed />
            <aside className="flex flex-col gap-4">
              <ConnectCard />
              <PadSyncCard />
              <SituationCard />
              <CouplingCard />
            </aside>
          </div>
        </div>
      </div>
    </main>
  );
}
