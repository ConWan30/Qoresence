import { Badge } from "@/components/ui/badge";
import { ROLE_LABEL, type AgentReceipt } from "@/lib/coupling/agents";
import { clipHref } from "@/lib/coupling/clip";
import { AGENT_COMPANION, companionDutyLine } from "@/lib/coupling/companion.ts";
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
    <section className="flex flex-col gap-3 rounded-xl bg-surface p-4 shadow-[var(--shadow-border)]">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Agents
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
          <a
            href={clipOpen}
            target="_blank"
            rel="noreferrer"
            data-clip-href={clipOpen}
            className="text-live no-underline hover:underline"
          >
            {companionDutyLine(companion)}
          </a>
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
      <div className="flex flex-wrap gap-2 font-mono text-[10px] tracking-wide uppercase">
        <span className={plane.clutchbot || companion.autoClip ? "text-live" : "text-subtle-foreground"}>
          {plane.clutchbot || companion.autoClip ? "ClutchBot live" : "ClutchBot wait"}
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
        ClutchBot still auto-clips clutch. Society coaches and proposes cuts — Export is the operator
        write. MCP never writes. Digits only after a Gemini board lock. Heat needs a coupling ticket.
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
