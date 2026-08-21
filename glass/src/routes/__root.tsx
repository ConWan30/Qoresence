import { Outlet, createRootRoute } from "@tanstack/react-router";
import { AppErrorComponent } from "@/lib/error-component";

export const Route = createRootRoute({
  component: () => <Outlet />,
  errorComponent: AppErrorComponent,
});
