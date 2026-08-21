import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useTheater, type DrillId, type HdmiMode } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

const DRILLS: { id: DrillId; label: string; hint: string }[] = [
  { id: "idle", label: "Menu idle", hint: "R2 on menu → IDLE, no ticket" },
  { id: "sprint", label: "Sprint", hint: "Live R2 + PLL lock → ticket" },
  { id: "veto", label: "Heat veto", hint: "PLL open → heat stripped" },
  { id: "score", label: "Score confirm", hint: "Digits need a confirm ticket" },
];

export function Controls() {
  const r2 = useTheater((s) => s.r2);
  const left = useTheater((s) => s.left);
  const hdmi = useTheater((s) => s.hdmi);
  const pllLock = useTheater((s) => s.pllLock);
  const drill = useTheater((s) => s.drill);
  const confirm = useTheater((s) => s.confirm);
  const setR2 = useTheater((s) => s.setR2);
  const setLeft = useTheater((s) => s.setLeft);
  const setHdmi = useTheater((s) => s.setHdmi);
  const setPllLock = useTheater((s) => s.setPllLock);
  const runDrill = useTheater((s) => s.runDrill);
  const mintConfirm = useTheater((s) => s.mintConfirm);
  const clearConfirm = useTheater((s) => s.clearConfirm);
  const tryThrow = useTheater((s) => s.tryThrow);
  const padConnected = useTheater((s) => s.padConnected);

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <HoldControl
          label={padConnected ? "R2 · DualSense" : "R2"}
          value={r2}
          locked={padConnected && drill === null}
          onHold={(v) => {
            runDrill(null);
            setR2(v);
          }}
        />
        <StickControl
          label={padConnected ? "Stick · DualSense" : "Left stick"}
          value={left}
          locked={padConnected && drill === null}
          onChange={(v) => {
            runDrill(null);
            setLeft(v);
          }}
        />
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Switch checked={pllLock} onCheckedChange={setPllLock} />
          PLL lock
        </label>
        <HdmiToggle value={hdmi} onChange={setHdmi} />
        <Button variant="ghost" size="sm" onClick={tryThrow}>
          Claim THROW
        </Button>
        {confirm ? (
          <Button variant="ghost" size="sm" onClick={clearConfirm}>
            Drop confirm
          </Button>
        ) : (
          <Button variant="secondary" size="sm" data-action="mint-confirm" onClick={mintConfirm}>
            Mint confirm 21-14
          </Button>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium tracking-wide text-muted-foreground">Drills</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {DRILLS.map((d) => (
            <button
              key={d.id}
              type="button"
              data-drill={d.id}
              onClick={() => runDrill(drill === d.id ? null : d.id)}
              className={cn(
                "flex min-h-11 flex-col items-start rounded-md px-3 py-2 text-left shadow-[var(--shadow-border)] transition-[box-shadow,background-color] duration-(--motion-quick) ease-(--ease-out) hover:shadow-[var(--shadow-border-hover)]",
                drill === d.id ? "bg-subtle text-fg" : "bg-transparent text-muted-foreground",
              )}
            >
              <span className="text-sm font-medium text-fg">{d.label}</span>
              <span className="text-xs text-muted-foreground">{d.hint}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function HoldControl({
  label,
  value,
  locked,
  onHold,
}: {
  label: string;
  value: number;
  locked?: boolean;
  onHold: (v: number) => void;
}) {
  return (
    <div className="rounded-lg bg-bg p-4 shadow-[var(--shadow-border)]">
      <div className="mb-3 flex items-baseline justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="font-mono text-xs tabular-nums text-fg">{value.toFixed(2)}</span>
      </div>
      <button
        type="button"
        disabled={locked}
        className="flex h-12 w-full items-center justify-center rounded-md bg-subtle text-sm font-medium text-fg active:scale-[0.98] disabled:opacity-50"
        onPointerDown={(e) => {
          if (locked) return;
          e.preventDefault();
          e.currentTarget.setPointerCapture(e.pointerId);
          onHold(1);
        }}
        onPointerUp={() => onHold(0)}
        onPointerLeave={() => onHold(0)}
        onPointerCancel={() => onHold(0)}
      >
        {locked ? "Live" : "Hold"}
      </button>
    </div>
  );
}

function StickControl({
  label,
  value,
  locked,
  onChange,
}: {
  label: string;
  value: number;
  locked?: boolean;
  onChange: (v: number) => void;
}) {
  return (
    <div className="rounded-lg bg-bg p-4 shadow-[var(--shadow-border)]">
      <div className="mb-3 flex items-baseline justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="font-mono text-xs tabular-nums text-fg">{value.toFixed(2)}</span>
      </div>
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={value}
        disabled={locked}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-12 w-full accent-primary disabled:opacity-50"
        aria-label={label}
      />
    </div>
  );
}

function HdmiToggle({
  value,
  onChange,
}: {
  value: HdmiMode;
  onChange: (m: HdmiMode) => void;
}) {
  const modes: HdmiMode[] = ["live", "menu", "stale"];
  return (
    <div className="flex rounded-full bg-surface p-1 shadow-[var(--shadow-border)]">
      {modes.map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => onChange(m)}
          className={cn(
            "h-9 min-w-14 rounded-full px-3 text-xs font-medium capitalize",
            value === m ? "bg-subtle text-fg" : "text-muted-foreground",
          )}
        >
          {m}
        </button>
      ))}
    </div>
  );
}
