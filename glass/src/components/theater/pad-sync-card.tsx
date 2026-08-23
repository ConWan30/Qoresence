import { DualSensePad } from "@/components/theater/dualsense-pad";
import { scorePadSync } from "@/lib/coupling/pad-sync";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

function shortPad(name: string): string {
  const n = name.replace(/\s+vid=\S+/i, "").trim();
  return n || "DualSense";
}

/** Live HID vs HDMI clock — proves the pad is registering and locked to the picture. */
export function PadSyncCard() {
  const padConnected = useTheater((s) => s.padConnected);
  const padName = useTheater((s) => s.padName);
  const padHeld = useTheater((s) => s.padHeld);
  const padReports = useTheater((s) => s.padReports);
  const padReportsPrev = useTheater((s) => s.padReportsPrev);
  const padTransport = useTheater((s) => s.padTransport);
  const padEnergy = useTheater((s) => s.padEnergy);
  const padBinds = useTheater((s) => s.padBinds);
  const padJitterMs = useTheater((s) => s.padJitterMs);
  const padHidSeq = useTheater((s) => s.padHidSeq);
  const pllLock = useTheater((s) => s.pllLock);
  const syncLagMs = useTheater((s) => s.syncLagMs);
  const videoAgeS = useTheater((s) => s.videoAgeS);
  const videoFrames = useTheater((s) => s.videoFrames);
  const r2 = useTheater((s) => s.r2);
  const left = useTheater((s) => s.left);
  const r2Frame = useTheater((s) => s.r2Frame);
  const leftFrame = useTheater((s) => s.leftFrame);
  const ghost = useTheater((s) => s.ghostStick);
  const ticketLive = useTheater((s) => s.ticketLive);

  const score = scorePadSync({
    connected: padConnected,
    reports: padReports,
    prevReports: padReportsPrev,
    pllLock,
    binds: padBinds,
    lagMs: ghost.lagMs || syncLagMs,
    jitterMs: padJitterMs,
    videoAgeS,
    hidSeq: padHidSeq,
    videoSeq: ghost.frameSeq || videoFrames,
    energy: Math.max(padEnergy, ghost.r2, ghost.l2),
    held: padHeld,
  });

  return (
    <section className="holo-plate flex flex-col gap-3 rounded-xl p-4" data-pad-sync={score.lock}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Pad sync
        </h2>
        <span
          className={cn(
            "font-mono text-[10px] tracking-[0.16em] uppercase",
            score.lock === "lock" ? "text-live" : score.lock === "drift" ? "text-veto" : "text-subtle-foreground",
          )}
        >
          {score.hid === "live" ? "HID live" : "HID wait"} · {score.lock}
        </span>
      </div>

      <p data-pad-sync-why={score.why} className="font-display text-xl font-extrabold leading-snug tracking-tight text-fg">
        {score.why}
      </p>

      <p className="font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
        {padConnected ? shortPad(padName) : "no DualSense on this box"}
        {padTransport ? ` · ${padTransport}` : ""}
        {padReports ? ` · ${padReports} reports` : ""}
      </p>

      <DualSensePad
        r2={r2}
        left={left}
        live={score.registering}
        r2Frame={r2Frame}
        leftFrame={leftFrame}
      />

      <div className="grid grid-cols-2 gap-2 font-mono text-[10px] tracking-wide text-subtle-foreground uppercase">
        <span>
          R2 {ghost.r2.toFixed(2)}
          <span className="mx-1">·</span>
          L2 {ghost.l2.toFixed(2)}
        </span>
        <span>
          Stick {ghost.lx.toFixed(2)} {ghost.ly.toFixed(2)}
        </span>
        <span>HID seq {padHidSeq || "—"}</span>
        <span>VID seq {ghost.frameSeq || videoFrames || "—"}</span>
        <span>Lag {Math.round(ghost.lagMs || syncLagMs)}ms</span>
        <span>Jitter {Math.round(padJitterMs)}ms</span>
      </div>

      {padHeld.length ? (
        <p className="font-mono text-[10px] tracking-[0.14em] text-live uppercase">
          {padHeld.join(" · ")}
        </p>
      ) : (
        <p className="font-mono text-[10px] tracking-wide text-subtle-foreground uppercase">
          {score.registering
            ? ticketLive
              ? "ticket live · waiting for a face button"
              : "reports climbing · press in-game to see buttons"
            : "wake the pad — USB to this laptop, then press R2"}
        </p>
      )}
    </section>
  );
}
