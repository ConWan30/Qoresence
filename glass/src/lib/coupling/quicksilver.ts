import { createServerFn } from "@tanstack/react-start";
import type { EnhanceIn, EnhanceOut } from "./quicksilver.server";

export type { EnhanceIn, EnhanceOut };

export const qsProbe = createServerFn({ method: "GET" }).handler(async () => {
  const { probeQuicksilver } = await import("./quicksilver.server");
  return probeQuicksilver();
});

export const qsEnhance = createServerFn({ method: "POST" })
  .validator((d: EnhanceIn) => d)
  .handler(async ({ data }) => {
    const { enhanceClutch } = await import("./quicksilver.server");
    return enhanceClutch(data);
  });
