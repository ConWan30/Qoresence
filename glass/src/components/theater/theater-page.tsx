import { useCallback, type PointerEvent } from "react";
import { CommandBar } from "@/components/theater/command-bar";
import { HdmiStage } from "@/components/theater/hdmi-stage";
import { ObservatoryHUD } from "@/components/theater/observatory-hud";
import { IntelligenceChamber } from "@/components/theater/intelligence-chamber";
import { GhostStickOverlay } from "@/components/theater/ghost-stick";
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

      {/* HDMI stage: fills leftover viewport, no scroll */}
      <div className="relative flex flex-1 flex-col overflow-hidden px-4 pb-3 sm:px-5 sm:pb-4">
        <div className="relative h-full w-full">
          <HdmiStage variant="observatory" />
          <ObservatoryHUD />
          <GhostStickOverlay />
        </div>
      </div>

      {/* Intelligence chamber: drawer from right */}
      <IntelligenceChamber />
    </main>
  );
}
