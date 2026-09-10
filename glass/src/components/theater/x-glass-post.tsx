import { useCallback, useEffect, useState } from "react";
import { clipPublicPath } from "@/lib/coupling/clip";
import { useTheater } from "@/lib/coupling/store";
import {
  armPostReason,
  createXGlassDraft,
  fetchXGlassStatus,
  holdLabel,
  pickCaptionMode,
  postXGlassVod,
  type XGlassArmReason,
  type XGlassStatus,
} from "@/lib/coupling/x-glass";
import { cn } from "@/lib/utils";

type Phase = "idle" | "drafted" | "busy" | "done";

/** Sight Glass: Create→Post Timeline VOD while a Foundry ISO clip plays. Never flips lobe ON. */
export function XGlassPostControl({ compact }: { compact?: boolean }) {
  const stageMode = useTheater((s) => s.stageMode);
  const lastClipName = useTheater((s) => s.lastClipName);
  const lastClipUrl = useTheater((s) => s.lastClipUrl);
  const boardLocked = useTheater((s) => s.boardLocked);
  const hdmiClips = useTheater((s) => s.hdmiClips);

  const [status, setStatus] = useState<XGlassStatus>({
    enabled: false,
    grant: false,
    ready: false,
    last_reason: "lobe_off",
    draft: null,
  });
  const [phase, setPhase] = useState<Phase>("idle");
  const [apiHold, setApiHold] = useState("");
  const [flash, setFlash] = useState("");

  const clipName = String(lastClipName || "");
  const clipPath =
    clipPublicPath(lastClipUrl || "") ||
    hdmiClips.find((c) => c.name === clipName)?.url ||
    "";

  const refresh = useCallback(async () => {
    const st = await fetchXGlassStatus();
    setStatus(st);
    if (st.draft?.clip_name && st.draft.clip_name === clipName) {
      setPhase((p) => (p === "done" ? p : "drafted"));
    }
  }, [clipName]);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    setPhase("idle");
    setApiHold("");
    setFlash("");
  }, [clipName, stageMode]);

  const reason: XGlassArmReason = armPostReason({
    stageMode,
    clipName,
    enabled: status.enabled,
    boardLocked,
    busy: phase === "busy",
  });
  const captionMode = pickCaptionMode(boardLocked);
  const show = stageMode === "replay" && Boolean(clipName);
  if (!show) return null;

  const armed = reason === "ok" && phase !== "busy";
  const label =
    phase === "busy"
      ? "Posting…"
      : phase === "done"
        ? "Posted"
        : phase === "drafted" && armed
          ? "Post"
          : armed
            ? "Create"
            : holdLabel(reason, apiHold || status.last_reason);

  const onClick = async () => {
    if (!armed || !clipName) return;
    setApiHold("");
    setFlash("");
    setPhase("busy");
    try {
      if (phase !== "drafted") {
        const created = await createXGlassDraft({
          clipName,
          clipPath: clipPath || undefined,
          captionMode,
        });
        if (!created.ok) {
          setApiHold(created.error || "hold");
          setPhase("idle");
          await refresh();
          return;
        }
        setPhase("drafted");
        setFlash(created.caption ? "draft ready" : "draft · digit silent");
        await refresh();
        return;
      }
      const posted = await postXGlassVod({
        clipName,
        clipPath: clipPath || undefined,
        captionMode,
      });
      if (!posted.ok) {
        setApiHold(posted.error || "hold");
        setPhase(posted.error === "create_required" ? "idle" : "drafted");
        await refresh();
        return;
      }
      setPhase("done");
      setFlash(posted.tweet_id ? `posted · ${posted.tweet_id}` : "posted");
      await refresh();
    } catch {
      setApiHold("hold");
      setPhase("idle");
    }
  };

  return (
    <div
      data-x-glass-post="1"
      data-x-glass-enabled={status.enabled ? "on" : "off"}
      data-x-glass-phase={phase}
      data-x-glass-reason={reason}
      className={cn(
        "flex shrink-0 items-center gap-1.5",
        compact ? "" : "ml-auto",
      )}
    >
      <button
        type="button"
        data-action={phase === "drafted" ? "x-glass-post" : "x-glass-create"}
        disabled={!armed}
        title="Timeline VOD only · Create≠Post · never Live Studio"
        className={cn(
          "stream-key inline-flex h-8 items-center justify-center px-2.5 font-mono text-[10px] font-extrabold tracking-[0.12em] uppercase",
          armed ? "stream-key-live" : "text-muted-foreground opacity-80",
        )}
        onPointerDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          void onClick();
        }}
      >
        {label}
      </button>
      {flash ? (
        <span className="max-w-[10rem] truncate font-mono text-[10px] text-subtle-foreground">
          {flash}
        </span>
      ) : null}
    </div>
  );
}
