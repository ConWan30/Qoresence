import { gamerHonestyCopy } from "@/lib/coupling/honesty-lattice";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

/** Gamer Now / Theater honesty speech. Never mount on Lens / overlay.html. */
export function HonestyLine({ className }: { className?: string }) {
  const noulOn = useTheater((s) => s.agentPlane.noulEnabled);
  const band = useTheater((s) => s.agentPlane.honestyBand);
  const token = useTheater((s) => s.agentPlane.presenceToken);
  const identNow = useTheater((s) => s.agentPlane.identNow);
  const gamerLine = useTheater((s) => s.agentPlane.gamerLine);
  const gamerPresence = useTheater((s) => s.agentPlane.gamerPresence);
  if (!noulOn) return null;
  const copy = gamerHonestyCopy({
    enabled: true,
    honestyBand: band,
    presenceToken: token,
    identNow,
  });
  const line = gamerLine || copy.line;
  const presence = gamerPresence || copy.presence;
  if (!line && !presence) return null;
  return (
    <p
      data-honesty-line={identNow || copy.ident ? "ident" : band}
      className={cn(
        "font-mono text-[10px] tracking-wide text-subtle-foreground",
        (identNow || copy.ident) && "text-veto",
        className,
      )}
    >
      {line ? line : presence}
      {line && presence ? ` · ${presence}` : ""}
    </p>
  );
}
