import { TALLY_LABEL, type TallyState } from "@/lib/coupling/signal-meter";
import { cn } from "@/lib/utils";

/** Broadcast tally lamp. LIVE only when Deck /health says the picture is
 *  painting (see tallyState). HOLD / STALL / DARK otherwise — never a fake LIVE. */
export function HoloTally({ state, title }: { state: TallyState; title?: string }) {
  return (
    <div
      data-tally={state}
      role="status"
      aria-live="polite"
      title={title}
      className={cn("holo-tally", `holo-tally-${state}`)}
    >
      <span className="holo-tally-lamp" aria-hidden />
      <span className="holo-tally-label">{TALLY_LABEL[state]}</span>
    </div>
  );
}
