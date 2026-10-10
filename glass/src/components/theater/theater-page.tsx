import { CommandBar } from "@/components/theater/command-bar";
import { HonestyStrip } from "@/components/theater/honesty-strip";
import { GamerDock } from "@/components/theater/gamer-dock";
import { HdmiStage } from "@/components/theater/hdmi-stage";
import { ClutchFeed } from "@/components/theater/clutch-feed";
import { SituationCard } from "@/components/theater/situation-card";
import { HighlightDirector } from "@/components/theater/highlight-director";
import { useTheaterLoop } from "@/lib/coupling/loop";
import { useTheater } from "@/lib/coupling/store";

export function TheaterPage() {
  useTheaterLoop();
  const clipArmed = useTheater((s) => s.companion.armed);

  return (
    <main className="deck-shell flex h-dvh flex-col overflow-hidden bg-bg text-fg">
      <CommandBar />
      <div className="deck-votes">
        <HonestyStrip />
        <GamerDock />
      </div>

      <div className="deck-floor mx-auto flex w-full max-w-[100rem] min-h-0 flex-1 flex-row gap-3 overflow-hidden px-3 pt-3 pb-3 sm:px-4 sm:pb-4">
        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <div className="relative h-full w-full">
            <HdmiStage variant="observatory" />
          </div>
        </div>

        {/* deck-rail scrolls on its own (styles.css) so Play-by-play is always reachable on short screens. */}
        <aside className="deck-rail flex min-h-0 w-full min-w-[17rem] max-w-[21rem] flex-col gap-2.5">
          <div className="shrink-0">
            <SituationCard />
          </div>
          {clipArmed ? (
            <div className="shrink-0">
              <HighlightDirector />
            </div>
          ) : (
            <section className="holo-plate foundry-plate shrink-0">
              <h2 className="plate-label">Foundry</h2>
              <p className="plate-title">
                Clips <em>&amp; highlights</em>
              </p>
              <a href="/studio.html" className="plate-link">
                Open Foundry →
              </a>
            </section>
          )}
          <div className="deck-rail-feed flex min-h-0 flex-1 flex-col overflow-hidden">
            <ClutchFeed />
          </div>
        </aside>
      </div>
    </main>
  );
}
