import { downDistanceLabel, scorebugPair } from "@/lib/coupling/board";
import { readTicks } from "@/lib/coupling/signal-meter";
import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";
import { ApertureIris } from "./aperture-iris";

/** Scorebug read board. LOCKED (gold) only when the board is licensed —
 *  ConfirmTicket + score_vlm_locked + Same-Seq + paint. Otherwise DARK: blank
 *  cells, never a last-good score. Read ticks and counters are the local
 *  reader's own /health numbers (local_scorebug). */
export function SituationCard() {
  const situation = useTheater((s) => s.situation);
  const gameTitle = useTheater((s) => s.gameTitle);
  const boardLine = useTheater((s) => s.boardLine);
  const hdmi = useTheater((s) => s.hdmi);
  const planeDim = useTheater((s) => s.planeDim);
  const sameSeq = useTheater((s) => s.sameSeq);
  const livePaint = useTheater((s) => s.livePaint);
  const boardLocked = useTheater((s) => s.boardLocked);
  const witnessKind = useTheater((s) => s.frameWitnessKind);
  const witnessSource = useTheater((s) => s.frameWitnessSource);
  const homeScore = useTheater((s) => s.homeScore);
  const awayScore = useTheater((s) => s.awayScore);
  const homeTeam = useTheater((s) => s.homeTeam);
  const awayTeam = useTheater((s) => s.awayTeam);
  const homeLeft = useTheater((s) => s.homeLeft);
  const leftTeam = useTheater((s) => s.leftTeam);
  const rightTeam = useTheater((s) => s.rightTeam);
  const leftScore = useTheater((s) => s.leftScore);
  const rightScore = useTheater((s) => s.rightScore);
  const down = useTheater((s) => s.down);
  const distance = useTheater((s) => s.distance);
  const confirm = useTheater((s) => s.confirm);
  const paintBlocked = useTheater((s) => s.honesty.paintBlocked);
  const sb = useTheater((s) => s.meter.scorebug);

  const widgetsOk = livePaint && sameSeq && !planeDim;
  const licensed =
    widgetsOk &&
    boardLocked &&
    !paintBlocked &&
    homeScore != null &&
    awayScore != null &&
    (confirm != null || boardLocked);
  const witnessOn =
    (witnessSource === "optical" || witnessSource === "noul") &&
    (witnessKind === "play" ||
      witnessKind === "pause" ||
      witnessKind === "menu" ||
      witnessKind === "loading");
  const line = licensed ? situation || boardLine : "";

  // Fail-closed: unlocked shows □–□ · — & —
  const fallback = licensed
    ? ""
    : `${scorebugPair({ homeScore: null, awayScore: null, dash: "–" }) || "□–□"} · ${downDistanceLabel(null, null)}`;

  const score = licensed
    ? scorebugPair({ homeScore, awayScore, homeTeam, awayTeam, homeLeft, leftTeam, rightTeam, leftScore, rightScore, dash: "–" })
    : "";
  // "0–0" or "SMU 0–0 LOUISVILLE" (named left→right as cropped).
  const pair = score.match(/^(.*?)\s*(\d+)–(\d+)\s*(.*)$/);
  const meta = licensed
    ? String(line || "").replace(/^\s*[^·]*\d+\s*[-–]\s*\d+[^·]*·\s*/, "") || downDistanceLabel(down, distance)
    : "— · — & —";
  const ticks = readTicks(sb);
  const tone = licensed ? "locked" : ticks.tone === "reading" || ticks.tone === "recheck" ? ticks.tone : "dark";
  const stateLabel = licensed ? "Locked" : tone === "reading" ? "Reading" : tone === "recheck" ? "Recheck" : "Dark";
  // Sure board = nothing blanked it; otherwise the reader's own last reason.
  const lastFrame = sb.lastFrameReason && sb.lastFrameReason !== "ok" ? sb.lastFrameReason : "";
  const blankWhy = sb.sure ? "none" : lastFrame || (sb.reason && sb.reason !== "agreeing" ? sb.reason : "") || "none";

  return (
    <section className={cn("holo-plate read-board", `is-${tone}`)} data-read={tone}>
      <div className="read-board-head">
        <h2 className="plate-label">Scorebug</h2>
        <span className="read-board-witness">
          {witnessOn ? witnessKind : boardLocked ? "scorebug lock" : hdmi === "menu" ? "menu" : "read"}
        </span>
      </div>

      <div className="read-board-body">
        <ApertureIris open={licensed} className="read-board-iris" />
        <div className="min-w-0 flex-1">
          <div className="read-board-state">
            <span className={cn("state-glyph", `g-${tone}`)} aria-hidden />
            <span>{stateLabel}</span>
            <span className="read-board-stamp">{licensed ? "3/3" : ticks.label}</span>
          </div>
          <p
            data-situation={line || fallback}
            aria-label={line || fallback}
            className="read-board-score"
          >
            {pair ? (
              <>
                {pair[1] ? <small>{pair[1]}</small> : null}
                {pair[2]}
                <i>–</i>
                {pair[3]}
                {pair[4] ? <small>{pair[4]}</small> : null}
              </>
            ) : score ? (
              score
            ) : (
              <>
                <b className="blank-cell" />
                <i>–</i>
                <b className="blank-cell" />
              </>
            )}
          </p>
          <p className="read-board-meta">{meta}</p>
        </div>
      </div>

      <div className={cn("q-reads", ticks.need > 3 && "is-nine")} aria-label={`Reads ${licensed ? "3/3" : ticks.label}`}>
        {Array.from({ length: licensed ? 3 : ticks.need }, (_, i) => (
          <i key={i} className={cn(i < (licensed ? 3 : ticks.lit) && "on")} />
        ))}
        <span>{licensed ? "3 of 3 match" : ticks.label}</span>
      </div>

      <dl className="read-board-local" data-local-scorebug={sb.enabled ? (sb.sure ? "sure" : "blank") : "off"}>
        <div>
          <dt>Reads</dt>
          <dd>{sb.reads ?? "—"}</dd>
        </div>
        <div>
          <dt>Agreed</dt>
          <dd>{sb.agreed ?? "—"}</dd>
        </div>
        <div>
          <dt>Disagree</dt>
          <dd>{sb.disagree ?? "—"}</dd>
        </div>
        <div className="col-span-3">
          <dt>Last blank</dt>
          <dd className="truncate">{sb.readerError ? "reader error" : blankWhy}</dd>
        </div>
      </dl>

      <p className="read-board-foot">{gameTitle || "title-presence from HDMI"}</p>
    </section>
  );
}
