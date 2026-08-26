import { useEffect, useState } from "react";
import { fetchSessionRecap, type SessionRecap as SessionRecapType } from "@/lib/coupling/session-api";
import { RecapBay } from "./recap-bay";

/** Phosphor Shell §2 — Session Recap (fail-closed empty bay). */
export function SessionRecap() {
  const [recap, setRecap] = useState<SessionRecapType | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      const data = await fetchSessionRecap();
      if (mounted) {
        setRecap(data);
        setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return (
      <section className="holo-plate rounded-xl p-5">
        <h2 className="mb-3 font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Recap
        </h2>
        <p className="font-mono text-sm text-subtle-foreground">Loading…</p>
      </section>
    );
  }

  // Fail-closed: show empty bay for empty/not_persisted
  if (!recap || recap.event_count === 0 || recap.empty_reason) {
    return <RecapBay recap={recap} />;
  }

  return (
    <section className="holo-plate rounded-xl p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Recap · {recap.status}
        </h2>
        <div className="flex items-center gap-3 font-mono text-[10px] tracking-wide text-subtle-foreground">
          <span>{recap.event_count} events</span>
          <span>{recap.confirmed_event_count} confirmed</span>
          {recap.duration_ms != null && (
            <span>{(recap.duration_ms / 1000).toFixed(1)}s</span>
          )}
        </div>
      </div>
      <div className="space-y-3">
        {recap.events.map((ev) => (
          <article
            key={ev.event_id}
            className="rounded-lg border border-subtle-foreground/20 bg-surface/40 p-3"
          >
            <div className="mb-1 flex items-center justify-between gap-2">
              <span
                className={
                  ev.qualification === "confirmed"
                    ? "font-mono text-[10px] tracking-wide text-live uppercase"
                    : "font-mono text-[10px] tracking-wide text-muted-foreground uppercase"
                }
              >
                {ev.event_type.replace(/_/g, " ")}
              </span>
              <span className="font-mono text-[10px] tabular-nums tracking-wide text-subtle-foreground">
                {ev.timestamp}
              </span>
            </div>
            {ev.qualification === "confirmed" && ev.score && (
              <p className="font-mono text-sm text-fg">
                {ev.score.home}–{ev.score.away}
                {ev.yard_line != null && ` · YL ${ev.yard_line}`}
              </p>
            )}
            {ev.clip.available && (
              <p className="font-mono text-[10px] text-sync">
                🎬 {ev.clip.clip_id}
              </p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
