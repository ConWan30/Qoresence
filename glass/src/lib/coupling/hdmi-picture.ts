/** HDMI picture gate — JPEG arriving wins.

livePaint / Same-Seq / Plane Dim ghost widgets only. A stale SPA that
opacity-0s the ``<img>`` on paint flicker blacks Theater while /live.jpg
is 200. Hygiene marker ``hdmiJpegKeep`` must survive Vite minify.
*/

export const HDMI_JPEG_KEEP = "hdmiJpegKeep";
/** After a good /live.jpg, fetch the next one immediately. An 80ms pause
 *  made Theater sit a frame behind HDMI (serial fetch + decode + wait). */
export const HDMI_JPEG_PUMP_MS = 0;
export const HDMI_JPEG_RETRY_MS = 200;
/** Start the next /live.jpg fetch while the current blob is decoding. */
export const HDMI_JPEG_OVERLAP = true;
/** Prefer ws://…/live JPEG push. Per-frame GET /live.jpg queued on the GIL. */
export const HDMI_JPEG_PUSH = true;

export function hdmiPictureVisible(jpgOk: boolean, _livePaint?: boolean): boolean {
  return Boolean(jpgOk);
}

/** Theater JPEG swap. Opacity 0/1 flashed the dark stage between frames. */
export const HDMI_PICTURE_SWAP = "stack";
/** Paint LIVE into one canvas. Swapping <img> src still flickered. */
export const HDMI_LIVE_PAINT = "canvas";

export function hdmiStackLayers(frontIsA: boolean): {
  a: { opacity: string; zIndex: string };
  b: { opacity: string; zIndex: string };
} {
  if (frontIsA) {
    return {
      a: { opacity: "1", zIndex: "2" },
      b: { opacity: "1", zIndex: "1" },
    };
  }
  return {
    a: { opacity: "1", zIndex: "1" },
    b: { opacity: "1", zIndex: "2" },
  };
}
