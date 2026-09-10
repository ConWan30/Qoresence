import { useState } from "react";
import {
  copyDiscordCard,
  exportClockEnvelope,
  sealClockEnvelope,
  verifyClockWrap,
  type ClockNotaryExport,
  type ClockNotarySeal,
} from "@/lib/coupling/clock-notary-api";

const PHRASE = "I am the gamer";

export function SealDoor() {
  const [gamer, setGamer] = useState("");
  const [purpose, setPurpose] = useState("portcert");
  const [wallet, setWallet] = useState("");
  const [phrase, setPhrase] = useState("");
  const [env, setEnv] = useState<ClockNotaryExport | null>(null);
  const [seal, setSeal] = useState<ClockNotarySeal | null>(null);
  const [status, setStatus] = useState("door closed");

  async function onExport() {
    const body = await exportClockEnvelope();
    setEnv(body);
    setStatus(body.ok ? `exported UNSEALED · ${body.clock_commitment}` : `export refused · ${body.error || "no session"}`);
  }

  async function onSeal() {
    const source = env && env.ok ? env : await exportClockEnvelope();
    setEnv(source);
    const body = await sealClockEnvelope({
      envelope: source,
      gamer,
      signed_by: gamer,
      purpose,
      wallet,
      phrase,
      granted: true,
    });
    setSeal(body);
    setStatus(body.ok ? body.discord_card || "SEALED" : `REFUSED · ${body.reason || ""} · ${body.hint || ""}`);
  }

  async function onVerify() {
    if (!env || !seal) {
      setStatus("export and seal first");
      return;
    }
    const body = await verifyClockWrap(seal, env);
    const lines = (body.checks || []).map((c) => `${c.ok ? "PASS" : "FAIL"} ${c.name}`);
    setStatus(`${body.ok ? "VERIFIED" : "UNTRUSTED"} ${body.passed}/${body.total}\n${lines.join("\n")}`);
  }

  return (
    <section className="notary-door mt-4 rounded-lg border border-subtle-foreground/20 p-4">
      <h3 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">Notary door</h3>
      <p className="mt-2 font-mono text-xs text-subtle-foreground">
        Eyes stay on this clock. Seal only after you say so. LIVE does not light TRUTH.
      </p>
      <p className="mt-2 font-mono text-[11px] text-fg">{env?.clock_commitment || "clock —"}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="stream-key" onClick={() => void onExport()}>
          Export recap
        </button>
        <button type="button" className="stream-key" onClick={() => void copyDiscordCard(env?.clock_commitment || "")}>
          Copy hash
        </button>
      </div>
      <label className="mt-3 block font-mono text-[10px] uppercase">
        Gamer handle
        <input className="mt-1 w-full bg-surface px-2 py-1" value={gamer} onChange={(e) => setGamer(e.target.value)} />
      </label>
      <label className="mt-2 block font-mono text-[10px] uppercase">
        Purpose
        <select className="mt-1 w-full bg-surface px-2 py-1" value={purpose} onChange={(e) => setPurpose(e.target.value)}>
          <option value="portcert">portcert</option>
          <option value="wmp">wmp</option>
          <option value="portcert+wmp">portcert+wmp</option>
        </select>
      </label>
      <label className="mt-2 block font-mono text-[10px] uppercase">
        Wallet optional
        <input className="mt-1 w-full bg-surface px-2 py-1" value={wallet} onChange={(e) => setWallet(e.target.value)} placeholder="0x… paused" />
      </label>
      <label className="mt-2 block font-mono text-[10px] uppercase">
        Type exactly: {PHRASE}
        <input className="mt-1 w-full bg-surface px-2 py-1" value={phrase} onChange={(e) => setPhrase(e.target.value)} />
      </label>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="stream-key" onClick={() => void onSeal()}>
          Seal this recap
        </button>
        <button type="button" className="stream-key" onClick={() => void copyDiscordCard(seal?.discord_card || "")}>
          Copy Discord card
        </button>
        <button type="button" className="stream-key" onClick={() => void onVerify()}>
          Verify without trusting us
        </button>
      </div>
      <pre className="mt-3 whitespace-pre-wrap font-mono text-[11px] text-subtle-foreground">{status}</pre>
    </section>
  );
}
