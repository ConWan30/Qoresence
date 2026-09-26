import { useCallback, useEffect, useState, type RefObject } from "react";
import {
  addDeadSpan,
  clipStem,
  cutEffective,
  cutReady,
  cutRenderUrl,
  DEAD_KINDS,
  DEAD_LABEL,
  gateLine,
  receiptUrl,
  refereeNote,
  spanState,
  spanTitle,
  spanWhy,
  stripPieces,
  toPlayerT,
  toSourceT,
  type CutReceipt,
  type DeadKind,
  type DeadSpan,
  type GateStatus,
} from "@/lib/coupling/cut-receipt";
import { cn } from "@/lib/utils";

const PIECE: Record<string, string> = {
  keep: "bg-fast",
  cut: "bg-[repeating-linear-gradient(45deg,var(--color-subtle)_0_3px,transparent_3px_6px)]",
  suggest: "bg-[repeating-linear-gradient(45deg,var(--color-fast)_0_3px,transparent_3px_6px)]",
};

const btn = "stream-key h-7 shrink-0 px-2 font-mono text-[10px] uppercase text-fg disabled:opacity-40";

/**
 * Cut Receipt + pilot labels under the replay stage. The original clip is never
 * modified; labelling is blind (original picture only, receipt hidden).
 */
export function ReplayCutPanel({
  clipHref,
  videoRef,
  onSource,
  floating = false,
}: {
  clipHref: string;
  videoRef: RefObject<HTMLVideoElement | null>;
  onSource: (url: string, atSeconds: number) => void;
  floating?: boolean;
}) {
  const [receipt, setReceipt] = useState<CutReceipt | null>(null);
  const [edited, setEdited] = useState(false);
  const [note, setNote] = useState("");
  const [labelOn, setLabelOn] = useState(false);
  const [dead, setDead] = useState<DeadSpan[]>([]);
  const [markStart, setMarkStart] = useState<number | null>(null);
  const [labelNote, setLabelNote] = useState("");
  const [gate, setGate] = useState<GateStatus | null>(null);
  const stem = clipStem(clipHref);

  const now = () => Number(videoRef.current?.currentTime || 0);

  const show = useCallback(
    (r: CutReceipt | null, wantEdited: boolean, fromEdited: boolean) => {
      const src = toSourceT(r, now(), fromEdited);
      const url = wantEdited ? cutRenderUrl(clipHref, r) : "";
      const on = Boolean(url);
      setEdited(on);
      onSource(on ? `${url}?v=${Date.now()}` : clipHref, toPlayerT(r, src, on));
    },
    [clipHref, onSource],
  );

  const loadGate = useCallback(() => {
    fetch("/api/excise/gate", { cache: "no-store" })
      .then((r) => r.json())
      .then((g: GateStatus) => setGate(g))
      .catch(() => setGate(null));
  }, []);

  useEffect(() => {
    let dead = false;
    setReceipt(null);
    setEdited(false);
    setLabelOn(false);
    setMarkStart(null);
    setDead([]);
    setNote("");
    const url = receiptUrl(clipHref);
    if (!url) return;
    fetch(`${url}?v=${Date.now()}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((r: CutReceipt | null) => {
        if (dead || !r) return;
        setReceipt(r);
        if (cutReady(r)) show(r, true, false);
      })
      .catch(() => {});
    fetch(`/api/excise/labels/${encodeURIComponent(stem)}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => {
        if (dead) return;
        const got = (j?.labels?.dead || []) as DeadSpan[];
        setDead(got);
        setLabelNote(j?.labelled ? `labelled · ${got.length} dead span${got.length === 1 ? "" : "s"}` : "not labelled yet");
      })
      .catch(() => {});
    loadGate();
    return () => {
      dead = true;
    };
  }, [clipHref, stem, show, loadGate]);

  if (!receipt) return null;
  const spans = receipt.spans || [];

  const decide = (spanId: string, decision: "cut" | "keep") => {
    setNote("rendering…");
    fetch(`/api/clip/${encodeURIComponent(stem)}/cuts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ span_id: spanId, decision }),
    })
      .then((r) => r.json())
      .then(() => {
        let tries = 0;
        const poll = () => {
          fetch(`${receiptUrl(clipHref)}?v=${Date.now()}`, { cache: "no-store" })
            .then((r) => r.json())
            .then((r: CutReceipt) => {
              if (r.render?.state === "pending" && ++tries < 40) {
                window.setTimeout(poll, 700);
                return;
              }
              const was = edited;
              setReceipt(r);
              setNote("");
              show(r, was || decision === "cut", was);
            })
            .catch(() => setNote(""));
        };
        poll();
      })
      .catch(() => setNote("cut request failed"));
  };

  const toggleLabel = () => {
    const on = !labelOn;
    setLabelOn(on);
    setMarkStart(null);
    if (on && edited) show(receipt, false, true);
    if (on) setLabelNote("watch the original; mark each pause/menu/loading");
  };

  const endAs = (kind: DeadKind) => {
    const res = addDeadSpan(dead, markStart, now(), kind);
    if (res.error) {
      setLabelNote(res.error);
      return;
    }
    setDead(res.dead);
    setMarkStart(null);
    setLabelNote("unsaved");
  };

  const save = () => {
    fetch(`/api/excise/labels/${encodeURIComponent(stem)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dead }),
    })
      .then((r) => r.json())
      .then((j) => {
        setLabelNote(j?.ok ? `saved · ${dead.length} dead span${dead.length === 1 ? "" : "s"}` : `save failed: ${j?.error || ""}`);
        loadGate();
      })
      .catch(() => setLabelNote("save failed"));
  };

  const seek = (sourceT: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = toPlayerT(receipt, sourceT, edited);
  };

  const src = Number(receipt.source_duration_s || 0);
  const ed = Number(receipt.edited_duration_s || src);
  const ready = cutReady(receipt);

  return (
    <div
      data-cut-panel="replay"
      className={cn(
        "pointer-events-auto flex flex-col gap-1.5 bg-bg/85 px-2 py-1.5 font-mono text-[10px]",
        floating
          ? "absolute top-3 right-3 z-30 max-h-[calc(100%-5rem)] w-[min(30rem,calc(100%-6rem))] overflow-auto rounded-lg border border-border backdrop-blur-sm"
          : "relative z-10 border-t border-border",
      )}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <div className="flex items-center gap-2">
        <span className="shrink-0 tracking-[0.16em] text-live uppercase">Cut receipt</span>
        <button
          type="button"
          className={btn}
          data-action="cut-view"
          disabled={!ready || labelOn}
          onClick={() => show(receipt, !edited, edited)}
        >
          {ready
            ? edited
              ? `Edited ${ed.toFixed(1)}s · show original`
              : `Original ${src.toFixed(1)}s · show edited`
            : `Original ${src.toFixed(1)}s`}
        </button>
        <span className="truncate text-muted-foreground">{labelOn ? "" : note || refereeNote(receipt)}</span>
      </div>
      {spans.length && !labelOn ? (
        <>
          <div className="flex h-2 overflow-hidden rounded bg-subtle" aria-label="Kept and removed spans">
            {stripPieces(receipt).map((p, i) => (
              <span key={i} className={cn("h-full", PIECE[p.kind])} style={{ width: `${p.frac * 100}%` }} />
            ))}
          </div>
          <div className="flex max-h-28 flex-col gap-1 overflow-auto">
            {spans.map((s) => {
              const eff = cutEffective(s);
              const state = spanState(s);
              return (
                <div key={s.id} className="flex items-center gap-2 text-fg">
                  <button type="button" className="shrink-0 text-left" onClick={() => seek(s.t0_s)}>
                    {spanTitle(s)}
                  </button>
                  <span className="min-w-0 flex-1 truncate text-muted-foreground">{spanWhy(s)}</span>
                  {state === "suggested" ? (
                    <>
                      <button
                        type="button"
                        className={btn}
                        data-action="cut-accept"
                        onClick={() => decide(s.id, "cut")}
                      >
                        Accept
                      </button>
                      <button
                        type="button"
                        className={btn}
                        data-action="cut-reject"
                        onClick={() => decide(s.id, "keep")}
                      >
                        Reject
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className={btn}
                      data-action="cut-decide"
                      onClick={() => decide(s.id, eff === "cut" ? "keep" : "cut")}
                    >
                      {eff === "cut" ? "Keep" : "Cut"}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </>
      ) : null}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="shrink-0 tracking-[0.16em] text-live uppercase">Pilot labels</span>
        <button type="button" className={btn} data-action="label-toggle" onClick={toggleLabel}>
          {labelOn ? "Done labelling" : "Label this clip"}
        </button>
        {labelOn ? (
          <>
            <button type="button" className={btn} data-action="label-mark" onClick={() => {
              setMarkStart(now());
              setLabelNote(`start ${now().toFixed(1)}s · pick how it ends`);
            }}>
              Mark start
            </button>
            {DEAD_KINDS.map((k) => (
              <button key={k} type="button" className={btn} data-label-kind={k} onClick={() => endAs(k)}>
                End · {DEAD_LABEL[k]}
              </button>
            ))}
            <button type="button" className={btn} data-action="label-save" onClick={save}>
              Save labels
            </button>
          </>
        ) : null}
        <span className="truncate text-muted-foreground">{labelNote}</span>
      </div>
      {dead.length ? (
        <div className="flex flex-wrap gap-1.5">
          {dead.map((d, i) => (
            <span key={`${d[0]}-${i}`} className="flex items-center gap-1 text-fg">
              <button type="button" onClick={() => seek(d[0])}>
                {DEAD_LABEL[d[2]]} {d[0].toFixed(1)}–{d[1].toFixed(1)}s
              </button>
              {labelOn ? (
                <button
                  type="button"
                  className="text-veto"
                  aria-label="Remove label"
                  onClick={() => {
                    setDead(dead.filter((_, j) => j !== i));
                    setLabelNote("unsaved");
                  }}
                >
                  ×
                </button>
              ) : null}
            </span>
          ))}
        </div>
      ) : null}
      <span className="text-muted-foreground">{gateLine(gate)}</span>
    </div>
  );
}
