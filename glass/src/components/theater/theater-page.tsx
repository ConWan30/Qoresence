import { CommandBar } from "@/components/theater/command-bar";
import { HdmiStage } from "@/components/theater/hdmi-stage";
import { ObservatoryHUD } from "@/components/theater/observatory-hud";
import { IntelligenceChamber } from "@/components/theater/intelligence-chamber";
import { ClutchFeed } from "@/components/theater/clutch-feed";
import { SituationCard } from "@/components/theater/situation-card";
import { useTheaterLoop } from "@/lib/coupling/loop";

export function TheaterPage() {
  useTheaterLoop();

  return (
    <main className="flex h-dvh flex-col overflow-hidden bg-bg text-fg">
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

        {/* RIGHT: Situation scorebug plate + ClutchFeed. No page scroll. */}
        <aside className="flex min-h-0 w-full min-w-[18rem] max-w-[21rem] flex-col gap-3 sm:gap-4">
          <div className="shrink-0">
            <SituationCard />
          </div>
          <div className="flex min-h-0 flex-1 flex-col">
            <ClutchFeed />
          </div>
        </aside>
      </div>

      {/* Intelligence chamber: optional drawer for extra access */}
      <IntelligenceChamber />
    </main>
  );
}
