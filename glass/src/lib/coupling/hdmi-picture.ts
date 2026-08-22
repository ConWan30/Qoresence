/** HDMI picture gate — JPEG arriving wins.

livePaint / Same-Seq / Plane Dim ghost widgets only. A stale SPA that
opacity-0s the ``<img>`` on paint flicker blacks Theater while /live.jpg
is 200. Hygiene marker ``hdmiJpegKeep`` must survive Vite minify.
*/

export const HDMI_JPEG_KEEP = "hdmiJpegKeep";

export function hdmiPictureVisible(jpgOk: boolean, _livePaint?: boolean): boolean {
  return Boolean(jpgOk);
}
