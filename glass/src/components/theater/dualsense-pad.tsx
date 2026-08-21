import { cn } from "@/lib/utils";

type Props = {
  r2: number;
  left: number;
  live: boolean;
  r2Frame?: number;
  leftFrame?: number;
};

export function DualSensePad({ r2, left, live, r2Frame, leftFrame }: Props) {
  const frame = r2Frame ?? r2;
  const stick = Math.min(6, (leftFrame ?? left) * 8);
  const usbOn = r2 > 0.08;
  const frameOn = frame > 0.08;
  return (
    <svg
      viewBox="0 0 220 92"
      className={cn(
        "h-14 w-32 shrink-0 text-fg sm:h-16 sm:w-40",
        live ? "opacity-100" : "opacity-70",
      )}
      aria-hidden
    >
      <rect
        x="18"
        y="28"
        width="184"
        height="48"
        rx="24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        opacity="0.4"
      />
      <path
        d="M48 30 C48 16 72 12 110 12 C148 12 172 16 172 30"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        opacity="0.35"
      />
      <circle
        cx={62 + stick}
        cy={52}
        r="11"
        className="fill-subtle"
        stroke="currentColor"
        strokeWidth="1.2"
        opacity="0.8"
      />
      <circle cx={62 + stick} cy={52} r="3" fill="currentColor" opacity="0.85" />
      <rect x="86" y="48" width="14" height="4" rx="1" fill="currentColor" opacity="0.35" />
      <rect x="91" y="43" width="4" height="14" rx="1" fill="currentColor" opacity="0.35" />
      <circle cx="148" cy="46" r="3.2" fill="currentColor" opacity="0.4" />
      <circle cx="158" cy="54" r="3.2" fill="currentColor" opacity="0.4" />
      <circle cx="138" cy="54" r="3.2" fill="currentColor" opacity="0.4" />
      <circle cx="148" cy="62" r="3.2" fill="currentColor" opacity="0.4" />
      <circle
        cx="176"
        cy="58"
        r="8"
        className="fill-subtle"
        stroke="currentColor"
        strokeWidth="1.2"
        opacity="0.7"
      />
      {usbOn ? (
        <rect x="152" y={8 - r2 * 4} width="26" height="12" rx="3" className="fill-sync" opacity="0.35" />
      ) : null}
      <rect
        x="154"
        y={10 - frame * 4}
        width="22"
        height="10"
        rx="3"
        className={frameOn ? "fill-live" : "fill-fg"}
        opacity={frameOn ? 1 : 0.25}
      />
      <text
        x="165"
        y="18"
        textAnchor="middle"
        className={frameOn ? "fill-primary-foreground" : "fill-fg"}
        fontSize="7"
        fontFamily="ui-monospace, monospace"
        opacity="0.9"
      >
        R2
      </text>
    </svg>
  );
}