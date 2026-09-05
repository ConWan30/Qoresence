import { couplingMeter } from "@/lib/coupling/coupling-meter";
import { useTheater } from "@/lib/coupling/store";

/** Pad↔picture co-occurrence histogram. Theater only. Not Lens. Not X public. */
export function CouplingMeter() {
  const pllLock = useTheater((s) => s.pllLock);
  const sameSeq = useTheater((s) => s.sameSeq);
  const syncLagMs = useTheater((s) => s.syncLagMs);
  const ghost = useTheater((s) => s.ghostStick);
  const lag = ghost.lagMs || syncLagMs;
  const meter = couplingMeter({
    lagMs: pllLock ? lag : null,
    pllLock,
    sameSeq,
  });

  return (
    <div data-coupling-meter={meter.label} className="pointer-events-none rounded-sm bg-bg/75 px-2 py-1 font-mono text-[10px] tracking-wide text-photon uppercase backdrop-blur-sm">
      pad↔picture {meter.label}
      {meter.skewMs != null ? ` · ${Math.round(meter.skewMs)}ms` : ""}
      <span className="ml-2 inline-flex gap-0.5 align-middle">
        {meter.bins.map((b) => (
          <i
            key={b.ms}
            data-bin={b.ms}
            className="inline-block w-1 bg-live/80"
            style={{ height: 4 + b.n * 8 }}
          />
        ))}
      </span>
    </div>
  );
}
