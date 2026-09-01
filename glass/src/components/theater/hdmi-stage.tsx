import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { getCaptureVideo } from "@/lib/coupling/hardware";
import { deckLiveJpgUrl, deckLiveWsUrl, HDMI_LIVE_FEED } from "@/lib/coupling/qoresence-deck";
import { apertureIdentOn } from "@/lib/coupling/aperture-ident";
import {
  HDMI_JPEG_KEEP,
  HDMI_JPEG_OVERLAP,
  HDMI_JPEG_PUMP_MS,
  HDMI_JPEG_PUSH,
  HDMI_JPEG_RETRY_MS,
  HDMI_LIVE_PAINT,
  hdmiPictureVisible,
} from "@/lib/coupling/hdmi-picture";
import { clipHref } from "@/lib/coupling/clip";
import { clutchPulse } from "@/lib/coupling/clutch-pulse";
import { scoreLiveHealth } from "@/lib/coupling/live-health";
import { useTheater } from "@/lib/coupling/store";
import { ApertureIdent } from "./aperture-ident";
import { GhostStickOverlay } from "./ghost-stick";
import { LensOverlay } from "./lens-overlay";
import { LiveHealthGlyph } from "./live-health-glyph";
import { SignalPrism } from "./signal-prism";
import { StageClipDock } from "./clip-rack";

export function HdmiStage({ variant }: { variant: "deck" | "lens" | "observatory" }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoHostRef = useRef<HTMLDivElement>(null);
  const prevRef = useRef({ frames: 0, pushes: 0, climbedAt: 0 });
  const jpgOkRef = useRef(false);
  const [jpgOk, setJpgOk] = useState(false);
  const [ageMs, setAgeMs] = useState(0);

  const stageMode = useTheater((s) => s.stageMode);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let timer = 0;
    let lastOk = 0;
    let stopped = false;
    let liveWs: WebSocket | null = null;

    if (stageMode === "replay") {
      return () => {
        stopped = true;
        window.clearTimeout(timer);
      };
    }

    const markOk = () => {
      if (!jpgOkRef.current) {
        jpgOkRef.current = true;
        setJpgOk(true);
      }
    };

    const pullBlob = () =>
      fetch(deckLiveJpgUrl(), { cache: "no-store" }).then((res) => {
        if (!res.ok) throw new Error("live.jpg");
        return res.blob();
      });

    const paintBlob = async (blob: Blob) => {
      const bmp = await createImageBitmap(blob);
      try {
        if (stopped) return;
        if (canvas.width !== bmp.width || canvas.height !== bmp.height) {
          canvas.width = bmp.width;
          canvas.height = bmp.height;
        }
        const ctx = canvas.getContext("2d", { alpha: false });
        if (!ctx) return;
        ctx.drawImage(bmp, 0, 0);
        lastOk = performance.now();
        markOk();
      } finally {
        bmp.close();
      }
    };

    let painting = false;
    let newest: Blob | null = null;
    let paintGate = Promise.resolve();
    const offerBlob = (blob: Blob) => {
      newest = blob;
      if (painting) return paintGate;
      painting = true;
      paintGate = (async () => {
        while (newest && !stopped) {
          const next = newest;
          newest = null;
          try {
            await paintBlob(next);
          } catch {
            /* decode miss — keep last good still */
          }
        }
        painting = false;
      })();
      return paintGate;
    };

    const pumpJpegPull = async () => {
      let pending = HDMI_JPEG_OVERLAP ? pullBlob() : null;
      while (!stopped) {
        try {
          const blob = pending ? await pending : await pullBlob();
          if (stopped) return;
          pending = HDMI_JPEG_OVERLAP ? pullBlob() : null;
          await offerBlob(blob);
          if (HDMI_JPEG_PUMP_MS > 0) {
            await new Promise((r) => {
              timer = window.setTimeout(r, HDMI_JPEG_PUMP_MS);
            });
          }
        } catch {
          if (stopped) return;
          pending = null;
          const age = lastOk ? performance.now() - lastOk : 9999;
          if (age > 2000) {
            jpgOkRef.current = false;
            setJpgOk(false);
          }
          await new Promise((r) => {
            timer = window.setTimeout(r, HDMI_JPEG_RETRY_MS);
          });
        }
      }
    };

    const pumpJpegPush = () =>
      new Promise<boolean>((resolve) => {
        let opened = false;
        let ws: WebSocket;
        try {
          ws = new WebSocket(deckLiveWsUrl());
        } catch {
          resolve(false);
          return;
        }
        liveWs = ws;
        ws.binaryType = "arraybuffer";
        const failTimer = window.setTimeout(() => {
          if (!opened) {
            try {
              ws.close();
            } catch {
              /* ignore */
            }
            resolve(false);
          }
        }, 1500);
        ws.onopen = () => {
          opened = true;
          window.clearTimeout(failTimer);
        };
        ws.onmessage = (ev) => {
          if (stopped) return;
          const data = ev.data;
          const blob = data instanceof Blob ? data : new Blob([data], { type: "image/jpeg" });
          offerBlob(blob);
        };
        ws.onerror = () => {
          window.clearTimeout(failTimer);
          try {
            ws.close();
          } catch {
            /* ignore */
          }
        };
        ws.onclose = () => {
          window.clearTimeout(failTimer);
          if (liveWs === ws) liveWs = null;
          resolve(opened);
        };
      });

    const run = async () => {
      while (!stopped) {
        if (HDMI_JPEG_PUSH) {
          const opened = await pumpJpegPush();
          if (stopped) return;
          if (opened) {
            await new Promise((r) => {
              timer = window.setTimeout(r, HDMI_JPEG_RETRY_MS);
            });
            continue;
          }
        }
        await pumpJpegPull();
        return;
      }
    };
    void run();

    const ageWatch = window.setInterval(() => {
      if (stopped) return;
      if (!lastOk) return;
      const next = Math.round(performance.now() - lastOk);
      setAgeMs((prev) => (Math.abs(prev - next) < 250 ? prev : next));
    }, 400);

    return () => {
      stopped = true;
      window.clearTimeout(timer);
      window.clearInterval(ageWatch);
      if (liveWs) {
        try {
          liveWs.close();
        } catch {
          /* ignore */
        }
        liveWs = null;
      }
    };
  }, [stageMode]);

  useEffect(() => {
    const host = videoHostRef.current;
    if (!host) return;
    const id = window.setInterval(() => {
      const src = getCaptureVideo();
      if (!src) return;
      if (stageMode === "replay") {
        if (src.parentElement === host) host.removeChild(src);
        return;
      }
      if (src.parentElement !== host) {
        src.className = "absolute inset-0 h-full w-full object-contain bg-bg";
        src.muted = true;
        src.playsInline = true;
        host.appendChild(src);
        void src.play().catch(() => undefined);
      }
    }, 250);
    return () => window.clearInterval(id);
  }, [stageMode]);

  const lastClipUrl = useTheater((s) => s.lastClipUrl);
  const lastClipName = useTheater((s) => s.lastClipName);
  const videoAgeS = useTheater((s) => s.videoAgeS);
  const videoFrames = useTheater((s) => s.videoFrames);
  const videoPushes = useTheater((s) => s.videoPushes);
  const clutch = useTheater((s) => s.clutch);
  const companion = useTheater((s) => s.companion);
  const goLive = useTheater((s) => s.goLive);
  const replaySrc = stageMode === "replay" ? clipHref(lastClipUrl) : "";
  const showLive = hdmiPictureVisible(jpgOk) && !replaySrc;
  const identOn = apertureIdentOn(jpgOk, Boolean(replaySrc));
  const climbed = videoFrames > prevRef.current.frames || videoPushes > prevRef.current.pushes;
  if (climbed) {
    prevRef.current = { frames: videoFrames, pushes: videoPushes, climbedAt: performance.now() };
  } else if (videoFrames > 0 || videoPushes > 0) {
    prevRef.current = { ...prevRef.current, frames: videoFrames, pushes: videoPushes };
  }
  const health = scoreLiveHealth({
    ageS: videoAgeS,
    frames: videoFrames,
    pushes: videoPushes,
    prevFrames: prevRef.current.frames,
    prevPushes: prevRef.current.pushes,
    climbAgeMs: prevRef.current.climbedAt ? performance.now() - prevRef.current.climbedAt : 99999,
    jpgOk,
    jpgAgeMs: ageMs,
    stageMode,
  });
  const pulse =
    variant === "deck" && stageMode !== "replay"
      ? clutchPulse({
          kind: clutch.kind,
          score: clutch.score,
          armed: companion.armed,
          companionPhase: companion.phase,
          companionClimax: companion.climax,
        })
      : "off";

  return (
    <section
      data-stage-mode={stageMode}
      data-clip-owner="hdmi-stage"
      data-clutch={variant === "deck" || variant === "observatory" ? pulse : undefined}
      className={cn(
        "relative isolate",
        variant === "lens"
          ? "h-full min-h-0 w-full"
          : variant === "observatory"
            ? "holo-plinth h-full w-full overflow-hidden rounded-xl"
            : "holo-plinth overflow-hidden rounded-xl",
      )}
      data-holo-tone={variant === "deck" || variant === "observatory" ? health.tone : undefined}
      onPointerDown={() => void useTheater.getState().ensureCapture()}
    >
      <div
        className={cn(
          "holo-plinth-well relative isolate z-0 overflow-hidden",
          variant === "lens"
            ? "h-full w-full"
            : variant === "observatory"
              ? "h-full w-full rounded-[calc(var(--radius-xl)-1px)]"
              : "mx-auto aspect-video max-h-[calc(100dvh-13.5rem)] w-full max-w-[min(100%,calc((100dvh-13.5rem)*16/9))] rounded-[calc(var(--radius-xl)-1px)] md:max-h-[calc(100dvh-11.5rem)] md:max-w-[min(100%,calc((100dvh-11.5rem)*16/9))]",
        )}
      >
        <div
          ref={videoHostRef}
          className={cn("absolute inset-0 z-0", jpgOk || replaySrc || identOn ? "opacity-0" : "")}
        />
        <canvas
          ref={canvasRef}
          data-hdmi-keep={HDMI_JPEG_KEEP}
          data-hdmi-feed={HDMI_LIVE_FEED}
          data-hdmi-paint={HDMI_LIVE_PAINT}
          data-hdmi-picture={showLive ? "on" : "off"}
          className={cn(
            "hdmi-picture pointer-events-none absolute inset-0 z-0 h-full w-full bg-bg object-contain",
            identOn ? "opacity-0" : "",
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
            className="hdmi-picture absolute inset-0 z-10 h-full w-full bg-black object-contain"
          />
        ) : null}
        {replaySrc ? (
          <button
            type="button"
            data-action="stage-live"
            className="stream-key stream-key-live absolute top-3 left-3 z-30 px-3 py-1.5 font-mono text-[10px] font-extrabold uppercase"
            onClick={(e) => {
              e.stopPropagation();
              goLive();
            }}
          >
            PGM
          </button>
        ) : variant === "deck" || variant === "observatory" ? (
          <span className="pointer-events-none absolute top-3 left-3 z-20 rounded-sm bg-bg/75 px-2 py-1 font-mono text-[10px] tracking-[0.2em] text-photon uppercase backdrop-blur-sm">
            {identOn ? "HOLD" : "PGM"}
          </span>
        ) : null}
        {identOn ? <ApertureIdent /> : null}
        {!replaySrc && !identOn ? <LiveHealthGlyph health={health} /> : null}
        {!replaySrc && !identOn ? <GhostStickOverlay /> : null}
        {!replaySrc && !identOn && variant !== "observatory" ? <LensOverlay variant={variant} /> : null}
      </div>
      {variant === "deck" || variant === "observatory" ? <SignalPrism ageS={videoAgeS} tone={health.tone} /> : null}
      {variant === "deck" || variant === "observatory" ? <StageClipDock /> : null}
    </section>
  );
}
