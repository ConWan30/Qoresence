import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useTheater } from "@/lib/coupling/store";

export function CouplingCard() {
  const widgetsOk = useTheater((s) => s.livePaint && s.sameSeq && !s.planeDim);
  const phrase = useTheater((s) => s.phrase);
  const ticket = useTheater((s) => s.ticket);
  const ticketLive = useTheater((s) => s.ticketLive);
  const heatVetoed = useTheater((s) => s.heatVetoed);
  const heatLine = useTheater((s) => s.heatLine);
  const scoreLine = useTheater((s) => s.scoreLine);
  const confirm = useTheater((s) => s.confirm);
  const why = useTheater((s) => s.why);
  const pllLock = useTheater((s) => s.pllLock);
  const coupling = useTheater((s) => s.coupling);

  const heat = ticketLive ? "licensed" : heatVetoed ? "veto" : "quiet";

  return (
    <section className={"holo-plate flex flex-col gap-3 rounded-xl p-4" + (widgetsOk ? "" : " opacity-0")}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Coupling
        </h2>
        <Badge variant={ticketLive ? "live" : heatVetoed ? "veto" : "default"}>
          {ticketLive ? "ticket live" : heatVetoed ? "heat veto" : "couple none"}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Kv label="Phrase" value="off" hot={false} />
        <Kv label="PLL" value={pllLock ? "lock" : "open"} hot={pllLock} bad={!pllLock} />
        <Kv
          label="Ticket"
          value={ticketLive && ticket ? ticket.ticketId.slice(0, 8) : "none"}
          hot={ticketLive}
        />
        <Kv label="Heat" value={heat} hot={heat === "licensed"} bad={heat === "veto"} />
      </div>

      <p className="font-mono text-[11px] tabular-nums text-muted-foreground">
        coupling {coupling.toFixed(2)}
        <span className="mx-1.5 text-subtle-foreground">·</span>
        conf {phrase.confidence.toFixed(2)}
      </p>

      <Separator />

      <div className="flex flex-col gap-1.5">
        <p className="font-mono text-[10px] tracking-[0.12em] text-subtle-foreground uppercase">
          Score speech
        </p>
        <p data-score={scoreLine} className="font-mono text-sm tabular-nums text-fg">
          {scoreLine}
        </p>
        <p className="text-xs text-muted-foreground">
          {confirm ? "Confirm ticket licenses digits." : "No confirm ticket — digits collapse to board."}
        </p>
      </div>

      <p
        data-why={why}
        data-heat={heat}
        data-ticket={ticketLive ? "live" : "none"}
        className="font-mono text-[10px] leading-relaxed break-all text-subtle-foreground"
      >
        {why}
      </p>

      {heatLine && (
        <p className="text-sm text-fg">{heatLine}</p>
      )}
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
