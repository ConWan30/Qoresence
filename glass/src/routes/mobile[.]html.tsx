import { createFileRoute } from "@tanstack/react-router";
import { CommandBar } from "@/components/theater/command-bar";
import { ConnectCard } from "@/components/theater/connect-card";
import { HdmiStage } from "@/components/theater/hdmi-stage";
import { useTheaterLoop } from "@/lib/coupling/loop";

export const Route = createFileRoute("/mobile.html")({ component: MobilePage });

function MobilePage() {
  useTheaterLoop();
  return (
    <main className="flex min-h-dvh flex-col bg-bg text-fg">
      <CommandBar />
      <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
        <HdmiStage variant="lens" />
        <ConnectCard />
      </div>
    </main>
  );
}
