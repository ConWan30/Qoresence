import { CommandBar } from "@/components/theater/command-bar";
import { HonestyStrip } from "@/components/theater/honesty-strip";
import { HdmiStage } from "@/components/theater/hdmi-stage";
import { ObservatoryHUD } from "@/components/theater/observatory-hud";
import { ClutchFeed } from "@/components/theater/clutch-feed";
import { SituationCard } from "@/components/theater/situation-card";
import { HighlightDirector } from "@/components/theater/highlight-director";
import { useTheaterLoop } from "@/lib/coupling/loop";
import { useTheater } from "@/lib/coupling/store";

export function TheaterPage() {
  useTheaterLoop();
  const clipArmed = useTheater((s) => s.companion.armed);

  return (
    <main className="flex h-dvh flex-col overflow-hidden bg-bg text-fg">
      <CommandBar />
      <HonestyStrip />

      <div className="mx-auto flex w-full max-w-[88rem] min-h-0 flex-1 flex-row gap-4 overflow-hidden px-4 pb-3 sm:px-5 sm:pb-4">
        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <div className="relative h-full w-full">
            <HdmiStage variant="observatory" />
            <ObservatoryHUD />
          </div>
        </div>

        <aside className="flex min-h-0 w-full min-w-[18rem] max-w-[21rem] flex-col gap-3 overflow-hidden sm:gap-4">
          <div className="shrink-0">
            <SituationCard />
          </div>
          {clipArmed ? (
            <div className="shrink-0">
              <HighlightDirector />
            </div>
          ) : (
            <section className="holo-plate shrink-0 rounded-xl p-3.5">
              <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
                Foundry
              </h2>
              <p className="mt-2 font-display text-sm font-extrabold text-fg">Clips and highlights</p>
              <a
                href="/studio.html"
                className="mt-3 inline-flex font-mono text-[10px] tracking-[0.14em] text-live uppercase"
              >
                Open Foundry →
              </a>
            </section>
          )}
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <ClutchFeed />
          </div>
        </aside>
      </div>
    </main>
  );
}
