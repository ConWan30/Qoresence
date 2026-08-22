import { createRouter } from "@tanstack/react-router";
import { AppErrorComponent } from "@/lib/error-component";
import { routeTree } from "./routeTree.gen";

const router = createRouter({
  routeTree,
  defaultErrorComponent: AppErrorComponent,
});

export function getRouter() {
  return router;
}

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
