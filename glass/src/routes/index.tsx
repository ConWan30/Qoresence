import { createFileRoute } from "@tanstack/react-router";
import { TheaterPage } from "@/components/theater/theater-page";

export const Route = createFileRoute("/")({ component: TheaterPage });
