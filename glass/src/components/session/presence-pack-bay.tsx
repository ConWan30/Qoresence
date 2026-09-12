import { useState } from "react";
import {
  copyText,
  downloadJson,
  downloadPresenceZip,
  fetchPresencePack,
  type PresencePackExport,
} from "@/lib/coupling/clock-notary-api";

/** Session Pack tab. Draft listing + zip. Seal / WMP are not on this glass. */
export function PresencePackBay() {
  const [pack, setPack] = useState<PresencePackExport | null>(null);
  const [status, setStatus] = useState("pack idle");

  async function onAssemble() {
    const body = await fetchPresencePack();
    setPack(body);
    if (body.ok && body.manifest) {
      setStatus(`assembled · ${body.manifest.clock_commitment}`);
    } else {
      setStatus(`assemble refused · ${body.error || "no session"}`);
    }
  }

  async function onZip() {
    const ok = await downloadPresenceZip();
    setStatus(ok ? "zip downloaded" : "zip refused");
  }

  const manifest = pack?.manifest;
  const listing = pack?.listing;

  return (
    <section className="holo-plate rounded-xl p-5">
      <h2 className="mb-3 font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
        Pack
      </h2>
      <p className="font-mono text-sm text-subtle-foreground">
        Observation envelope + clock. Listing stays draft. Sealing is not on this glass.
      </p>
      <p className="mt-2 font-mono text-[11px] text-fg">
        {manifest?.clock_commitment || "clock —"}
      </p>
      <p className="mt-1 font-mono text-[10px] tracking-wide text-subtle-foreground uppercase">
        {manifest ? `out_edge ${manifest.out_edge}` : "out_edge —"} ·{" "}
        {listing?.status || "draft"} · {manifest?.notary || "UNSEALED"}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="stream-key" data-action="pack-assemble" onClick={() => void onAssemble()}>
          Assemble pack
        </button>
        <button type="button" className="stream-key" data-action="pack-zip" onClick={() => void onZip()}>
          Download zip
        </button>
        <button
          type="button"
          className="stream-key"
          data-action="pack-copy-hash"
          disabled={!manifest?.clock_commitment}
          onClick={() => void copyText(manifest?.clock_commitment || "")}
        >
          Copy hash
        </button>
        <button
          type="button"
          className="stream-key"
          data-action="pack-copy-listing"
          disabled={!listing}
          onClick={() => {
            if (listing) downloadJson("listing-draft.json", listing);
          }}
        >
          Copy listing
        </button>
      </div>
      <p className="mt-3 font-mono text-[11px] text-subtle-foreground">
        Price is for the clock. WMP is not this SKU.
      </p>
      <pre className="mt-3 whitespace-pre-wrap font-mono text-[11px] text-subtle-foreground">{status}</pre>
    </section>
  );
}
