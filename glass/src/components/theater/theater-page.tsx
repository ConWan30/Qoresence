import { useCallback, type PointerEvent } from "react";
import { CommandBar } from "@/components/theater/command-bar";
import { HdmiStage } from "@/components/theater/hdmi-stage";
import { ObservatoryHUD } from "@/components/theater/observatory-hud";
import { IntelligenceChamber } from "@/components/theater/intelligence-chamber";
import { SituationCard } from "@/components/theater/situation-card";
import { ClutchFeed } from "@/components/theater/clutch-feed";
import { ConnectCard } from "@/components/theater/connect-card";
import { PadSyncCard } from "@/components/theater/pad-sync-card";
import { CouplingCard } from "@/components/theater/coupling-card";
import { AgentRail } from "@/components/theater/agent-rail";
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
    <main
      className="holo-deck flex h-dvh flex-col overflow-hidden bg-bg text-fg"
      onPointerMove={onPrism}
    >
      {/* Command bar: intrinsic height, no shrink */}
      <CommandBar />

      {/* Split layout: HDMI stage (left) + Intelligence column (right) */}
      <div className="mx-auto flex w-full max-w-[88rem] min-h-0 flex-1 flex-row gap-4 overflow-hidden px-4 pb-3 sm:px-5 sm:pb-4">
        {/* LEFT: HDMI stage container with ObservatoryHUD overlay */}
        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <div className="relative h-full w-full">
            <HdmiStage variant="observatory" />
            <ObservatoryHUD />
          </div>
        </div>

        {/* RIGHT: Intelligence column - always visible, scrollable */}
        <aside className="flex min-h-0 w-full min-w-[18rem] max-w-[21rem] flex-col gap-3 overflow-y-auto sm:gap-4">
          <SituationCard />
          <ClutchFeed />
          <ConnectCard />
          <PadSyncCard />
          <CouplingCard />
          <AgentRail />
        </aside>
      </div>

      {/* Intelligence chamber: optional drawer for extra access */}
      <IntelligenceChamber />
    </main>
  );
}
