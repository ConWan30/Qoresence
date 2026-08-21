/** Port of qoresence.lobes.streamer.resolve_capture_device.
 *  Binds by DirectShow/UVC name, not camera index. */

export type DshowDevice = {
  index: number;
  id: string;
  name: string;
  allowed: boolean;
};

const PHYSICAL_CARD_HINTS = [
  "usb3.0 video",
  "usb 3.0 video",
  "usb video",
  "elgato",
  "avermedia",
  "capture",
  "hdmi",
  "game capture",
  "live gamer",
] as const;

const DISALLOWED = [
  "720p hd camera",
  "hd camera",
  "webcam",
  "integrated",
  "laptop",
  "facetime",
  "built-in",
] as const;

export const DEFAULT_PREFER_NAME = "USB3.0 Video";

export function isObsVirtualCameraName(name: string | null | undefined): boolean {
  if (!name) return false;
  const n = name.toLowerCase();
  return n.includes("obs virtual") || n.trim() === "obs-camera" || n.trim() === "obs camera";
}

export function isAllowedCaptureName(name: string | null | undefined): boolean {
  if (!name) return false;
  const n = name.toLowerCase();
  if (DISALLOWED.some((bad) => n.includes(bad))) {
    return ["usb3.0 video", "obs virtual"].some((good) => n.includes(good));
  }
  if (
    [
      "usb3.0 video",
      "obs virtual",
      "capture",
      "hdmi",
      "elgato",
      "avermedia",
      "usb video",
    ].some((good) => n.includes(good))
  ) {
    return true;
  }
  if (n.includes("camera")) return false;
  return true;
}

export function isPhysicalCardName(name: string | null | undefined): boolean {
  if (!name || !isAllowedCaptureName(name)) return false;
  if (isObsVirtualCameraName(name)) return false;
  const n = name.toLowerCase();
  if (PHYSICAL_CARD_HINTS.some((h) => n.includes(h))) return true;
  return !n.includes("camera");
}

export function resolveCaptureDevice(
  devices: DshowDevice[],
  opts: {
    requestedIndex?: number | null;
    preferName?: string | null;
    allowObsVcam?: boolean;
  } = {},
): DshowDevice | null {
  if (!devices.length) return null;
  const preferName = opts.preferName ?? null;
  const allowObsVcam = Boolean(opts.allowObsVcam);
  const requestedIndex = opts.requestedIndex ?? null;

  if (preferName) {
    const pn = preferName.trim().toLowerCase();
    for (const d of devices) {
      if (!d.allowed) continue;
      const nl = d.name.toLowerCase();
      if (nl === pn || nl.includes(pn) || pn.includes(nl)) return d;
    }
  }

  const physical = devices.filter((d) => d.allowed && isPhysicalCardName(d.name));
  if (physical.length) {
    const usb3 = physical.find(
      (d) => d.name.toLowerCase().includes("usb3.0") || d.name.toLowerCase().includes("usb 3.0"),
    );
    return usb3 ?? physical[0];
  }

  if (requestedIndex != null && requestedIndex >= 0) {
    for (const d of devices) {
      if (d.index === requestedIndex && d.allowed) {
        if (allowObsVcam || !isObsVirtualCameraName(d.name)) return d;
      }
    }
  }

  if (allowObsVcam) {
    const vcam = devices.find((d) => d.allowed && isObsVirtualCameraName(d.name));
    if (vcam) return vcam;
  }

  return null;
}
