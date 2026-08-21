import { Badge } from "@/components/ui/badge";
import { ROLE_LABEL, type AgentReceipt } from "@/lib/coupling/agents";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

export function AgentRail() {
  const agents = useTheater((s) => s.agents);
  const ticketLive = useTheater((s) => s.ticketLive);
  const heatVetoed = useTheater((s) => s.heatVetoed);
  const plane = useTheater((s) => s.agentPlane);
  const qsLive = useTheater((s) => s.qsLive);
  const qsModel = useTheater((s) => s.qsModel);
  const qsError = useTheater((s) => s.qsError);

  const armed = plane.clutchbot || plane.society || qsLive;
  const badge = heatVetoed
    ? "heat veto"
    : ticketLive
      ? "ticket live"
      : qsLive || plane.a2a
        ? "Quicksilver live"
        : "Quicksilver wait";

  return (
    <section className="flex flex-col gap-3 rounded-xl bg-surface p-4 shadow-[var(--shadow-border)]">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Agents
        </h2>
        <Badge variant={ticketLive || armed ? "live" : heatVetoed ? "veto" : "ticket"}>
          {badge}
        </Badge>
      </div>
      <div className="flex flex-wrap gap-2 font-mono text-[10px] tracking-wide uppercase">
        <span className={plane.clutchbot ? "text-live" : "text-subtle-foreground"}>
          {plane.clutchbot ? "ClutchBot live" : "ClutchBot wait"}
        </span>
        <span className="text-subtle-foreground">·</span>
        <span className={plane.society ? "text-live" : "text-subtle-foreground"}>
          {plane.society ? "Society live" : "Society wait"}
        </span>
        <span className="text-subtle-foreground">·</span>
        <span className={plane.vlmLocked || plane.geminiLive ? "text-live" : "text-subtle-foreground"}>
          {plane.vlmLocked
            ? `Gemini VLM lock${plane.vlmBoard ? ` ${plane.vlmBoard}` : ""}`
            : plane.geminiLive
              ? "Gemini VLM live"
              : "Gemini VLM wait"}
        </span>
        {plane.a2a ? (
          <>
            <span className="text-subtle-foreground">·</span>
            <span className="text-live">A2A</span>
          </>
        ) : null}
        <span className="text-subtle-foreground">·</span>
        <span className={qsLive || plane.a2a ? "text-live" : "text-subtle-foreground"}>
          {qsLive
            ? `QS ${qsModel || "nemotron-3.5-lightning"}`
            : plane.a2a
              ? "QS via Deck"
              : qsError || "QS wait"}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        ClutchBot speech is Quicksilver Pro (`nemotron-3.5-lightning`) or Deck A2A commits. Local templates stay unlabeled. Digits only after a Gemini board lock. Heat needs a coupling ticket.
      </p>
      <ul className="flex flex-col gap-2">
        {agents.map((a) => (
          <AgentRow key={a.role} agent={a} />
        ))}
      </ul>
    </section>
  );
}

function AgentRow({ agent }: { agent: AgentReceipt }) {
  const tone =
    agent.action === "veto"
      ? "text-veto"
      : agent.action === "chat" || agent.action === "allow"
        ? "text-live"
        : "text-muted-foreground";
  return (
    <li
      data-agent={agent.role}
      data-agent-action={agent.action}
      className="grid grid-cols-[5.5rem_minmax(0,1fr)] items-start gap-2"
    >
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-[11px] text-fg">{ROLE_LABEL[agent.role]}</span>
        <span className={cn("font-mono text-[10px] tracking-wide uppercase", tone)}>
          {agent.action}
        </span>
      </div>
      <p className="min-w-0 text-xs leading-relaxed text-muted-foreground">
        {agent.text || agent.reason}
        {agent.model === "quicksilver" && agent.action !== "quiet" && (
          <span className="mt-0.5 block font-mono text-[10px] tracking-wide text-subtle-foreground uppercase">
            {agent.model}
          </span>
        )}
      </p>
    </li>
  );
}