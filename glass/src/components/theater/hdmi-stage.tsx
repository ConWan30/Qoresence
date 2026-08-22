import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { getCaptureVideo } from "@/lib/coupling/hardware";
import { deckLiveJpgUrl } from "@/lib/coupling/qoresence-deck";
import { HDMI_JPEG_KEEP, hdmiPictureVisible } from "@/lib/coupling/hdmi-picture";
import { useTheater } from "@/lib/coupling/store";
import { GhostStickOverlay } from "./ghost-stick";
import { LensOverlay } from "./lens-overlay";

export function HdmiStage({ variant }: { variant: "deck" | "lens" }) {
  const imgRef = useRef<HTMLImageElement>(null);
  const videoHostRef = useRef<HTMLDivElement>(null);
  const [jpgOk, setJpgOk] = useState(false);
  const [ageMs, setAgeMs] = useState(0);

  useEffect(() => {
    let timer = 0;
    let lastOk = 0;
    const img = imgRef.current;
    if (!img) return;

    const tick = () => {
      if (!img) return;
      const url = deckLiveJpgUrl();
      img.onload = () => {
        lastOk = performance.now();
        setJpgOk(true);
        setAgeMs(0);
        timer = window.setTimeout(tick, 40);
      };
      img.onerror = () => {
        const age = lastOk ? performance.now() - lastOk : 9999;
        setAgeMs(Math.round(age));
        if (age > 2000) setJpgOk(false);
        timer = window.setTimeout(tick, 200);
      };
      img.src = url;
    };
    tick();
    const ageWatch = window.setInterval(() => {
      if (lastOk) setAgeMs(Math.round(performance.now() - lastOk));
    }, 400);
    return () => {
      window.clearTimeout(timer);
      window.clearInterval(ageWatch);
    };
  }, []);

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

  const frozen = jpgOk && ageMs > 3000;
  // JPEG arriving keeps HDMI up. livePaint flickers must not black the stage.
  const showLive = hdmiPictureVisible(jpgOk);

  return (
    <section
      className={cn(
        "relative overflow-hidden bg-surface",
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
          data-hdmi-picture={showLive ? "on" : "off"}
          className={cn(
            "absolute inset-0 h-full w-full object-contain bg-bg",
            showLive ? "opacity-100" : "opacity-0",
          )}
        />
        {frozen ? (
          <p className="absolute bottom-3 left-3 font-mono text-[10px] tracking-wide text-veto uppercase">
            HDMI freeze · pumping JPEG
          </p>
        ) : null}
        <GhostStickOverlay />
        <LensOverlay variant={variant} />
      </div>
    </section>
  );
}
