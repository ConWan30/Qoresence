import { useEffect, useState } from "react";

/** Switcher-style clock — local time, not a fake latency number. */
export function BroadcastClock() {
  const [now, setNow] = useState(() => formatClock(new Date()));

  useEffect(() => {
    const id = window.setInterval(() => setNow(formatClock(new Date())), 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <time className="font-mono text-[11px] tabular-nums tracking-[0.16em] text-photon" dateTime={now}>
      {now}
    </time>
  );
}

function formatClock(d: Date): string {
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}
