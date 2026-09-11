import { useState } from "react";
import {
  copyText,
  downloadJson,
  exportClockEnvelope,
  type ClockNotaryExport,
} from "@/lib/coupling/clock-notary-api";

/** Recap export only. Seal / Discord notary lives on QorTroller — not Deck. */
export function SealDoor() {
  const [env, setEnv] = useState<ClockNotaryExport | null>(null);
  const [status, setStatus] = useState("export idle");

  async function onExport() {
    const body = await exportClockEnvelope();
    setEnv(body);
    if (body.ok) {
      setStatus(`exported · ${body.clock_commitment}`);
      downloadJson("observation-envelope.json", body);
    } else {
      setStatus(`export refused · ${body.error || "no session"}`);
    }
  }

  return (
    <section className="recap-export mt-4 rounded-lg border border-subtle-foreground/20 p-4">
      <h3 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
        Export
      </h3>
      <p className="mt-2 font-mono text-xs text-subtle-foreground">
        Download the observation envelope. Sealing is not on this glass.
      </p>
      <p className="mt-2 font-mono text-[11px] text-fg">{env?.clock_commitment || "clock —"}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="stream-key" data-action="recap-export" onClick={() => void onExport()}>
          Export recap
        </button>
        <button
          type="button"
          className="stream-key"
          data-action="recap-copy-hash"
          disabled={!env?.clock_commitment}
          onClick={() => void copyText(env?.clock_commitment || "")}
        >
          Copy hash
        </button>
      </div>
      <pre className="mt-3 whitespace-pre-wrap font-mono text-[11px] text-subtle-foreground">{status}</pre>
    </section>
  );
}
