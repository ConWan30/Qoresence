import { Button } from "@/components/ui/button";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

export function ConnectCard() {
  const padConnected = useTheater((s) => s.padConnected);
  const padName = useTheater((s) => s.padName);
  const captureStatus = useTheater((s) => s.captureStatus);
  const captureLabel = useTheater((s) => s.captureLabel);
  const captureError = useTheater((s) => s.captureError);
  const captureDevices = useTheater((s) => s.captureDevices);
  const deckLive = useTheater((s) => s.deckLive);
  const armCapture = useTheater((s) => s.armCapture);
  const armShare = useTheater((s) => s.armShare);
  const wakePad = useTheater((s) => s.wakePad);
  const busy = captureStatus === "arming";

  return (
    <section className="holo-plate flex flex-col gap-3 rounded-xl p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Hardware
        </h2>
        <span
          className={cn(
            "font-mono text-[10px] tracking-wide uppercase",
            padConnected && (captureStatus === "live" || deckLive) ? "text-live" : "text-subtle-foreground",
          )}
        >
          {deckLive ? "monitor" : padConnected && captureStatus === "live" ? "bound" : "waiting"}
        </span>
      </div>

      <p className="text-xs text-muted-foreground">
        {deckLive
          ? "PS5 HDMI is on the laptop dongle. DualSense stays on the console. This glass watches the picture in real time."
          : "PS5 → capture card → laptop. Run --play --deck on the laptop. DualSense stays on the PS5. This glass monitors HDMI, not the pad."}
      </p>

      {captureError ? (
        <p
          data-hw-error={captureError}
          className={cn(
            "text-xs leading-relaxed",
            captureStatus === "live" ? "text-muted-foreground" : "text-veto",
          )}
        >
          {captureError}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-2">
        <Kv label="Pad" value={padConnected ? padName : "press a button"} hot={padConnected} />
        <Kv
          label="HDMI"
          value={captureStatus === "live" ? captureLabel : captureStatus}
          hot={captureStatus === "live"}
          bad={captureStatus === "blocked" || captureStatus === "busy" || captureStatus === "framed"}
        />
      </div>

      {captureDevices.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {captureDevices.map((d) => (
            <li key={d.id}>
              <button
                type="button"
                disabled={busy || !d.allowed}
                onClick={() => void armCapture(d.id)}
                className={cn(
                  "flex min-h-11 w-full items-center justify-between gap-2 rounded-md px-3 text-left text-xs shadow-[var(--shadow-border)]",
                  d.label === captureLabel && captureStatus === "live"
                    ? "bg-subtle text-fg"
                    : !d.allowed
                      ? "text-subtle-foreground opacity-50"
                      : "text-muted-foreground",
                )}
              >
                <span className="truncate">{d.label}</span>
                <span className="shrink-0 font-mono text-[10px] tracking-wide uppercase">
                  {!d.allowed ? "refused" : d.kind === "capture" ? "dongle" : "camera"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          disabled={busy}
          data-action="arm-hdmi"
          onClick={() => void armCapture()}
        >
          {busy ? "Arming…" : "Arm HDMI"}
        </Button>
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => void armShare()}>
          Share picture
        </Button>
        <Button size="sm" variant="ghost" onClick={() => void wakePad()}>
          Wake pad
        </Button>
      </div>
    </section>
  );
}

function Kv({
  label,
  value,
  hot,
  bad,
}: {
  label: string;
  value: string;
  hot?: boolean;
  bad?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="font-mono text-[10px] tracking-[0.12em] text-subtle-foreground uppercase">
        {label}
      </span>
      <span
        className={
          hot
            ? "truncate font-mono text-sm text-live"
            : bad
              ? "truncate font-mono text-sm text-veto"
              : "truncate font-mono text-sm text-fg"
        }
      >
        {value}
      </span>
    </div>
  );
}
