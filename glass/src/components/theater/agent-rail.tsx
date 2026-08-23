import { Badge } from "@/components/ui/badge";
import { ROLE_LABEL, visibleAgentReceipts, type AgentReceipt } from "@/lib/coupling/agents";
import { actuatorChips } from "@/lib/coupling/actuators.ts";
import { clipHref } from "@/lib/coupling/clip";
import { AGENT_COMPANION, companionDutyLine } from "@/lib/coupling/companion.ts";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

export function AgentRail() {
  const agents = useTheater((s) => s.agents);
  const actuators = useTheater((s) => s.actuators);
  const ticketLive = useTheater((s) => s.ticketLive);
  const heatVetoed = useTheater((s) => s.heatVetoed);
  const plane = useTheater((s) => s.agentPlane);
  const qsLive = useTheater((s) => s.qsLive);
  const companion = useTheater((s) => s.companion);
  const lastClipUrl = useTheater((s) => s.lastClipUrl);
  const clipOpen = companion.lastClip?.url
    ? clipHref(companion.lastClip.url)
    : lastClipUrl
      ? clipHref(lastClipUrl)
      : "";

  const armed = plane.clutchbot || plane.society || qsLive || companion.autoClip;
  const badge = heatVetoed
    ? "heat veto"
    : companion.armed
      ? "clip armed"
      : ticketLive
        ? "ticket live"
        : qsLive || plane.a2a
          ? "Quicksilver live"
          : "Quicksilver wait";

  return (
    <section className="holo-plate flex flex-col gap-3 rounded-xl p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Receipt
        </h2>
        <Badge variant={companion.armed || ticketLive || armed ? "live" : heatVetoed ? "veto" : "ticket"}>
          {badge}
        </Badge>
      </div>
      <p
        data-agent-companion={AGENT_COMPANION}
        data-auto-clip={companion.autoClip ? "on" : "off"}
        data-clip-armed={companion.armed ? "on" : "off"}
        className={cn(
          "font-mono text-[11px] tracking-wide",
          companion.armed ? "text-live" : "text-subtle-foreground",
        )}
      >
        {clipOpen ? (
          <button
            type="button"
            data-clip-href={clipOpen}
            className="text-left text-live hover:underline"
            onClick={() => useTheater.getState().playClip(clipOpen, companion.lastClip?.name)}
          >
            {companionDutyLine(companion)}
          </button>
        ) : (
          companionDutyLine(companion)
        )}
      </p>
      {companion.why || companion.phase ? (
        <p className="font-mono text-[10px] tracking-wide text-muted-foreground">
          Drive {companion.phase || "—"}
          {companion.climax != null ? ` · climax ${companion.climax.toFixed(2)}` : ""}
          {companion.matchRate != null ? ` · match ${companion.matchRate.toFixed(2)}` : ""}
          {companion.why ? ` · ${companion.why}` : ""}
        </p>
      ) : null}
      {companion.coach ? (
        <p className="text-xs leading-relaxed text-fg">{companion.coach}</p>
      ) : null}
      {companion.cut ? (
        <div className="flex items-start justify-between gap-2 rounded-lg bg-bg/60 px-3 py-2">
          <p className="min-w-0 text-xs text-muted-foreground">
            Ghost cut · {companion.cut.title || companion.cut.text}
          </p>
          <button
            type="button"
            data-action="export-ghost-cut"
            className="shrink-0 font-mono text-[10px] tracking-wide text-live uppercase"
            onClick={() => void useTheater.getState().requestClip()}
          >
            Export
          </button>
        </div>
      ) : null}
      <p className="font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
        {ticketLive ? "ticket live" : "ticket none"}
        {plane.vlmLocked ? " · board locked" : ""}
      </p>
      <p className="text-xs text-muted-foreground">
        Chat only with a ticket. Digits only after a board lock. Society is opt-in.
      </p>
      {actuatorChips(actuators).length ? (
        <ul className="flex flex-wrap gap-1.5">
          {actuatorChips(actuators).map((a) => (
            <li
              key={a.actuator}
              data-actuator={a.actuator}
              data-actuator-kind={a.kind}
              className="font-mono text-[10px] tracking-wide text-muted-foreground uppercase"
            >
              {a.actuator} {a.kind}
            </li>
          ))}
        </ul>
      ) : null}
      <ul className="flex flex-col gap-2">
        {visibleAgentReceipts(agents).map((a) => (
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
