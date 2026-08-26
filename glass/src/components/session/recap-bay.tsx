import type { SessionRecap } from "@/lib/coupling/session-api";

/** Phosphor Shell §2 — Recap Bay (fail-closed empty/not_persisted). */
export function RecapBay({ recap }: { recap: SessionRecap | null }) {
  const notPersisted = recap?.empty_reason === "not_persisted";
  const header = notPersisted ? "Recap · not persisted" : "Recap";
  const title = "No recap for this session";
  const sub = notPersisted ? "Nothing saved yet." : "No events recorded.";

  return (
    <section className="holo-plate rounded-xl p-5">
      <h2 className="mb-3 font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
        {header}
      </h2>
      <div className="space-y-2">
        <h3 className="font-display text-xl font-bold tracking-tight text-fg">
          {title}
        </h3>
        <p className="font-mono text-sm text-subtle-foreground">
          {sub}
        </p>
      </div>
    </section>
  );
}
