import { cn } from "@/lib/utils";

export type TallyMode = "air" | "standby" | "stall";

/** Broadcast tally lamp — ON AIR when HDMI is painting, STALL when the hub ages out. */
export function HoloTally({ mode }: { mode: TallyMode }) {
  return (
    <div
      data-tally={mode}
      className={cn(
        "holo-tally inline-flex items-center gap-2 rounded-sm px-2.5 py-1 font-mono text-[10px] font-bold tracking-[0.2em] uppercase",
        mode === "air" && "holo-tally-air",
        mode === "standby" && "holo-tally-standby",
        mode === "stall" && "holo-tally-stall",
      )}
    >
      <span className="holo-tally-lamp" aria-hidden />
      {mode === "air" ? "On air" : mode === "stall" ? "Stall" : "Standby"}
    </div>
  );
}
