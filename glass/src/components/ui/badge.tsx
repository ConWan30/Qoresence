import type { HTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 font-mono text-xs font-medium tabular-nums tracking-wide",
  {
    variants: {
      variant: {
        default: "bg-surface text-muted-foreground shadow-[var(--shadow-border)]",
        live: "bg-live/15 text-live",
        veto: "bg-veto/15 text-veto",
        ticket: "bg-primary/12 text-primary",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Badge({
  className,
  variant,
  ...props
}: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
