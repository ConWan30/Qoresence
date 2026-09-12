import { createFileRoute } from "@tanstack/react-router";
import { AgentRail } from "@/components/theater/agent-rail";
import { ClipRack } from "@/components/theater/clip-rack";
import { CommandBar } from "@/components/theater/command-bar";
import { useTheaterLoop } from "@/lib/coupling/loop";

export const Route = createFileRoute("/studio.html")({ component: StudioPage });

function StudioPage() {
  useTheaterLoop();
  const showOps =
    typeof window !== "undefined" && new URLSearchParams(window.location.search).get("ops") === "1";

  return (
    <main className="flex h-dvh min-h-0 flex-col overflow-hidden bg-bg text-fg">
      <CommandBar />
      <div className="min-h-0 flex-1 overflow-hidden">
        <div className="mx-auto flex h-full min-h-0 max-w-5xl flex-col px-4 py-5">
          <ClipRack />
          {showOps ? (
            <div className="mt-4 shrink-0">
              <AgentRail />
            </div>
          ) : null}
        </div>
      </div>
    </main>
  );
}
