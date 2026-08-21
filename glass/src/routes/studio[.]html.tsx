import { createFileRoute } from "@tanstack/react-router";
import { AgentRail } from "@/components/theater/agent-rail";
import { ClutchFeed } from "@/components/theater/clutch-feed";
import { CommandBar } from "@/components/theater/command-bar";
import { CouplingCard } from "@/components/theater/coupling-card";
import { useTheaterLoop } from "@/lib/coupling/loop";

export const Route = createFileRoute("/studio.html")({ component: StudioPage });

function StudioPage() {
  useTheaterLoop();
  return (
    <main className="min-h-dvh bg-bg text-fg">
      <CommandBar />
      <div className="mx-auto grid max-w-5xl gap-4 px-4 py-5 lg:grid-cols-2">
        <CouplingCard />
        <AgentRail />
        <div className="lg:col-span-2">
          <ClutchFeed />
        </div>
      </div>
    </main>
  );
}
