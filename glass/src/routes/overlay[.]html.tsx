import { createFileRoute } from "@tanstack/react-router";
import { useEffect } from "react";
import { LensOverlay } from "@/components/theater/lens-overlay";
import { useTheaterLoop } from "@/lib/coupling/loop";

export const Route = createFileRoute("/overlay.html")({ component: OverlayPage });

function OverlayPage() {
  useTheaterLoop();
  useEffect(() => {
    document.documentElement.classList.add("obs-lens");
    document.body.classList.add("obs-lens");
    return () => {
      document.documentElement.classList.remove("obs-lens");
      document.body.classList.remove("obs-lens");
    };
  }, []);

  return (
    <main className="relative h-dvh w-full overflow-hidden bg-transparent text-fg">
      <LensOverlay variant="lens" />
    </main>
  );
}
