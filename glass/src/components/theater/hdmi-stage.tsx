import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { getCaptureVideo } from "@/lib/coupling/hardware";
import { deckLiveJpgUrl, HDMI_LIVE_FEED } from "@/lib/coupling/qoresence-deck";
import { HDMI_JPEG_KEEP, hdmiPictureVisible } from "@/lib/coupling/hdmi-picture";
import { clipHref } from "@/lib/coupling/clip";
import { scoreLiveHealth } from "@/lib/coupling/live-health";
import { useTheater } from "@/lib/coupling/store";
import { GhostStickOverlay } from "./ghost-stick";
import { LensOverlay } from "./lens-overlay";
import { LiveHealthGlyph } from "./live-health-glyph";
import { StageClipDock } from "./clip-rack";

export function HdmiStage({ variant }: { variant: "deck" | "lens" }) {
  const imgRef = useRef<HTMLImageElement>(null);
  const videoHostRef = useRef<HTMLDivElement>(null);
  const prevRef = useRef({ frames: 0, pushes: 0 });
  const [jpgOk, setJpgOk] = useState(false);
  const [ageMs, setAgeMs] = useState(0);

  const stageMode = useTheater((s) => s.stageMode);

  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    let timer = 0;
    let lastOk = 0;
    let stopped = false;
    let inFlight = false;

    if (stageMode === "replay") {
      return () => {
        stopped = true;
        window.clearTimeout(timer);
      };
    }

    const pumpJpeg = () => {
      if (stopped || !img || inFlight) return;
      inFlight = true;
      img.onload = () => {
        inFlight = false;
        lastOk = performance.now();
        setJpgOk(true);
        setAgeMs(0);
        timer = window.setTimeout(pumpJpeg, 80);
      };
      img.onerror = () => {
        inFlight = false;
        const age = lastOk ? performance.now() - lastOk : 9999;
        setAgeMs(Math.round(age));
        if (age > 2000) setJpgOk(false);
        timer = window.setTimeout(pumpJpeg, 200);
      };
      img.src = deckLiveJpgUrl();
    };

    pumpJpeg();

    const ageWatch = window.setInterval(() => {
      if (stopped) return;
      if (lastOk) setAgeMs(Math.round(performance.now() - lastOk));
    }, 400);

    return () => {
      stopped = true;
      window.clearTimeout(timer);
      window.clearInterval(ageWatch);
    };
  }, [stageMode]);

  useEffect(() => {
    const host = videoHostRef.current;
    if (!host) return;
    const id = window.setInterval(() => {
      const src = getCaptureVideo();
      if (!src) return;
      if (src.parentElement !== host) {
        src.className = "absolute inset-0 h-full w-full object-contain bg-bg";
        src.muted = true;
        src.playsInline = true;
        host.appendChild(src);
        void src.play().catch(() => undefined);
      }
    }, 250);
    return () => window.clearInterval(id);
  }, []);

  const lastClipUrl = useTheater((s) => s.lastClipUrl);
  const lastClipName = useTheater((s) => s.lastClipName);
  const videoAgeS = useTheater((s) => s.videoAgeS);
  const videoFrames = useTheater((s) => s.videoFrames);
  const videoPushes = useTheater((s) => s.videoPushes);
  const goLive = useTheater((s) => s.goLive);
  const replaySrc = stageMode === "replay" ? clipHref(lastClipUrl) : "";
  const showLive = hdmiPictureVisible(jpgOk) && !replaySrc;
  const health = scoreLiveHealth({
    ageS: videoAgeS,
    frames: videoFrames,
    pushes: videoPushes,
    prevFrames: prevRef.current.frames,
    prevPushes: prevRef.current.pushes,
    jpgOk,
    jpgAgeMs: ageMs,
    stageMode,
  });
  prevRef.current = { frames: videoFrames, pushes: videoPushes };

  return (
    <section
      data-stage-mode={stageMode}
      data-clip-owner="hdmi-stage"
      className={cn(
        "relative bg-surface",
        variant === "lens"
          ? "h-full min-h-0 w-full"
          : "rounded-xl shadow-[var(--shadow-border),var(--shadow-sync)]",
      )}
      onPointerDown={() => void useTheater.getState().ensureCapture()}
    >
      <div
        className={cn(
          "relative w-full overflow-hidden bg-bg",
          variant === "lens" ? "h-full" : "aspect-video rounded-[calc(var(--radius-xl)-1px)]",
        )}
      >
        <div ref={videoHostRef} className={cn("absolute inset-0", jpgOk ? "opacity-0" : "")} />
        <img
          ref={imgRef}
          alt=""
          decoding="async"
          data-hdmi-keep={HDMI_JPEG_KEEP}
          data-hdmi-feed={HDMI_LIVE_FEED}
          data-hdmi-picture={showLive ? "on" : "off"}
          className={cn(
            "absolute inset-0 h-full w-full object-contain bg-bg",
            showLive ? "opacity-100" : "opacity-0",
          )}
        />
        {replaySrc ? (
          <video
            key={replaySrc}
            src={`${replaySrc}${replaySrc.includes("?") ? "&" : "?"}v=${encodeURIComponent(lastClipName || "clip")}`}
            controls
            playsInline
            autoPlay
            preload="auto"
            data-clip-player="stage"
            data-clip-href={replaySrc}
            className="absolute inset-0 z-10 h-full w-full bg-black object-contain"
          />
        ) : null}
        {replaySrc ? (
          <button
            type="button"
            data-action="stage-live"
            className="absolute top-3 left-3 z-30 rounded-full bg-live px-3 py-1.5 font-mono text-[10px] font-extrabold text-primary-foreground uppercase"
            onClick={(e) => {
              e.stopPropagation();
              goLive();
            }}
          >
            LIVE
          </button>
        ) : null}
        <LiveHealthGlyph health={health} />
        <GhostStickOverlay />
        <LensOverlay variant={variant} />
      </div>
      {variant === "deck" ? <StageClipDock /> : null}
    </section>
  );
}
