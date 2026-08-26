import { createFileRoute } from "@tanstack/react-router";
import { SessionTheater } from "@/components/session/session-theater";

export const Route = createFileRoute("/session.html")({ component: SessionTheater });
