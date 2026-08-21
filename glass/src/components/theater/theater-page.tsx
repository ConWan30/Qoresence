import { AgentRail } from "@/components/theater/agent-rail";
import { ClutchFeed } from "@/components/theater/clutch-feed";
import { CommandBar } from "@/components/theater/command-bar";
import { ConnectCard } from "@/components/theater/connect-card";
import { SituationCard } from "@/components/theater/situation-card";
import { Controls } from "@/components/theater/controls";
import { CouplingCard } from "@/components/theater/coupling-card";
import { HdmiStage } from "@/components/theater/hdmi-stage";
import { useTheaterLoop } from "@/lib/coupling/loop";

export function TheaterPage() {
  useTheaterLoop();

  return (
    <main className="min-h-dvh bg-bg text-fg">
      <CommandBar />
      <div className="mx-auto grid max-w-7xl gap-4 px-4 py-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(18rem,0.7fr)] lg:items-start lg:gap-5 lg:px-5 lg:py-5">
        <div className="flex min-w-0 flex-col gap-4">
          <HdmiStage variant="deck" />
          <ClutchFeed />
        </div>
        <aside className="flex flex-col gap-4">
          <ConnectCard />
          <SituationCard />
          <CouplingCard />
          <AgentRail />
          <section className="rounded-xl bg-surface p-4 shadow-[var(--shadow-border)]">
            <h2 className="mb-1 font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
              Pad
            </h2>
            <p className="mb-4 text-xs text-muted-foreground">
              DualSense stays on the PS5. This laptop only sees HDMI through the capture card.
            </p>
            <Controls />
          </section>
        </aside>
      </div>
    </main>
  );
}
