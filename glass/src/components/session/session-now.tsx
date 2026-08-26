import { GlanceGlyph } from "@/components/theater/glance-glyph";
import { LockbugStrip } from "@/components/theater/lockbug-strip";
import { DownPill } from "@/components/theater/down-pill";
import { useTheaterLoop } from "@/lib/coupling/loop";

/** Phosphor Shell §2 — Session Now (reuses Strip + Down Pill + Glyph + SYNC). */
export function SessionNow() {
  useTheaterLoop();

  return (
    <div className="space-y-4">
      <section className="holo-plate rounded-xl p-5">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
            Now
          </h2>
          <GlanceGlyph compact />
        </div>
        <div className="mb-4 flex items-center gap-3">
          <LockbugStrip />
          <DownPill />
        </div>
        <p className="font-mono text-[10px] tracking-wide text-subtle-foreground">
          Watching HDMI + DualSense + scorebug. Fast chat, score locks, and clips land here.
        </p>
      </section>

      <section className="holo-plate rounded-xl p-5">
        <h2 className="mb-2 font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Live Board
        </h2>
        <p className="font-mono text-sm text-muted-foreground">
          BOARD WAIT
        </p>
      </section>
    </div>
  );
}
