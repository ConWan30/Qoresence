# Theater LIVE rail — Situation scorebug + ClutchFeed

Operator asked for the situation scoreboard box back beside HDMI. #107 had stripped the rail to ClutchFeed only.

LIVE right aside now mounts:

1. `SituationCard` — fail-closed scorebug plate (`□–□` until confirm lock)
2. `ClutchFeed` — flex-1, internal `overflow-y-auto`

Receipt / AgentRail / Connect / PadSync / Coupling stay out of the LIVE page (chamber + `/health` only). `theater-page.tsx` still has no `overflow-y-auto`.
