import { useEffect, useState } from "react";
import { fetchSessionView, type SessionViewEnvelope } from "@/lib/coupling/session-api";

/** Phosphor Shell §2 — Session Story (fail-closed empty when unlocked or empty). */
export function SessionStory() {
  const [envelope, setEnvelope] = useState<SessionViewEnvelope | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      const data = await fetchSessionView();
      if (mounted) {
        setEnvelope(data);
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
          Story
        </h2>
        <p className="font-mono text-sm text-subtle-foreground">Loading…</p>
      </section>
    );
  }

  const view = envelope?.view;
  const status = envelope?.status || "unavailable";

  // Fail-closed: if unlocked or empty, show empty copy (never unlicensed events)
  const licensed = view?.board_locked && view.events.length > 0;

  if (!licensed) {
    return (
      <section className="holo-plate rounded-xl p-5">
        <h2 className="mb-3 font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Story
        </h2>
        <div className="space-y-2">
          <h3 className="font-display text-xl font-bold tracking-tight text-fg">
            No licensed story yet
          </h3>
          <p className="font-mono text-sm text-subtle-foreground">
            Events land here after confirm.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="holo-plate rounded-xl p-5">
      <h2 className="mb-3 font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
        Story · {status}
      </h2>
      <div className="space-y-3">
        {view.events.map((ev) => (
          <article
            key={ev.event_id}
            className="rounded-lg border border-subtle-foreground/20 bg-surface/40 p-3"
          >
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="font-mono text-[10px] tracking-wide text-live uppercase">
                {ev.event_type.replace(/_/g, " ")}
              </span>
              <span className="font-mono text-[10px] tabular-nums tracking-wide text-subtle-foreground">
                {ev.timestamp}
              </span>
            </div>
            {ev.score && (
              <p className="font-mono text-sm text-fg">
                {ev.score.home}–{ev.score.away}
                {ev.yard_line != null && ` · YL ${ev.yard_line}`}
              </p>
            )}
            {ev.input?.button && (
              <p className="font-mono text-[10px] text-muted-foreground">
                {ev.input.button}
                {ev.input.count != null && ` × ${ev.input.count}`}
              </p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
