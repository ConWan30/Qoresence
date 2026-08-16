"""DriveGraph — time-DAG causal structure over a SessionTimeline drive.

Observation-plane only. Built from timeline events (shared clock_ns).
Edges: precedes, arms, confirms, cancels, boosts.
Supports climax score, fast↔confirm matching, chapter ranking.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_MAX_DRIVE_GRAPH_NODES = 48
HARD_CEILING_DRIVE_GRAPH_NODES = 96
MIN_DRIVE_GRAPH_NODES = 8
ENV_MAX_DRIVE_GRAPH_NODES = "QORESENCE_DRIVE_GRAPH_MAX_NODES"


def resolve_max_nodes(explicit: int | None = None) -> int:
    """Named O(n²) safety cap. Raisable, never unbounded."""
    if explicit is not None:
        try:
            n = int(explicit)
        except (TypeError, ValueError):
            n = DEFAULT_MAX_DRIVE_GRAPH_NODES
    else:
        raw = os.environ.get(ENV_MAX_DRIVE_GRAPH_NODES, "").strip()
        try:
            n = int(raw) if raw else DEFAULT_MAX_DRIVE_GRAPH_NODES
        except ValueError:
            n = DEFAULT_MAX_DRIVE_GRAPH_NODES
    return max(MIN_DRIVE_GRAPH_NODES, min(HARD_CEILING_DRIVE_GRAPH_NODES, n))

# Kind families
_FAST_KINDS = frozenset({"fast_chat", "fast_clip", "arm", "prediction_open"})
_CONFIRM_KINDS = frozenset(
    {"confirm_chat", "confirm_clip", "confirm_score", "prediction_resolve", "confirm"}
)
_CANCEL_KINDS = frozenset({"prediction_cancel"})
_ARM_KINDS = frozenset({"arm"})
_OPEN_KINDS = frozenset({"prediction_open"})
_RESOLVE_KINDS = frozenset({"prediction_resolve", "confirm_score"})
_SCORE_PLAY_KINDS = frozenset(
    {
        "touchdown",
        "field_goal",
        "safety",
        "two_point",
        "two_point_conversion",
        "score_changed",
        "confirm_score",
        "prediction_resolve",
    }
)
_BOARD_DUMP_KINDS = frozenset({"fast_chat", "video_ambient", "scene_tick"})
_SCORE_PLAY_HINTS = (
    "touchdown",
    " td",
    "td ",
    "field goal",
    "field-goal",
    " fg",
    "safety",
    "score update",
    "score_changed",
)

BOOST_WINDOW_NS = int(0.4 * 1e9)  # ~400ms heat → following act
DEFAULT_MATCH_LAG_MS = 8000
_T0_BOARD_NS = int(1.5 * 1e9)


def _is_score_play(n: GraphNode) -> bool:
    if n.kind in _SCORE_PLAY_KINDS:
        return True
    blob = f"{n.kind} {n.label}".lower()
    return any(h in blob for h in _SCORE_PLAY_HINTS)


def _is_t0_board(n: GraphNode, started_ns: int) -> bool:
    if n.clock_ns - int(started_ns or 0) > _T0_BOARD_NS:
        return False
    blob = n.label.lower()
    if n.kind in _BOARD_DUMP_KINDS:
        return True
    return "board" in blob or "live-board" in blob or blob.startswith("live ")


@dataclass
class GraphNode:
    node_id: str
    clock_ns: int
    kind: str
    path: str = ""
    message: str = ""
    reason: str = ""
    frame_seq: int | None = None
    coupling: float | None = None
    factual: bool | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    stale_after_rollback: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = {
            "node_id": self.node_id,
            "clock_ns": self.clock_ns,
            "kind": self.kind,
            "path": self.path,
            "message": self.message,
            "reason": self.reason,
        }
        if self.frame_seq is not None:
            d["frame_seq"] = self.frame_seq
        if self.coupling is not None:
            d["coupling"] = self.coupling
        if self.factual is not None:
            d["factual"] = self.factual
        if self.stale_after_rollback:
            d["stale_after_rollback"] = True
        return d

    @property
    def label(self) -> str:
        return (self.message or self.reason or self.kind or "?")[:80]

    @property
    def is_fast(self) -> bool:
        return self.path == "fast" or self.kind in _FAST_KINDS or self.kind.startswith("fast_")

    @property
    def is_confirm(self) -> bool:
        return (
            self.path == "confirm"
            or self.kind in _CONFIRM_KINDS
            or self.kind.startswith("confirm")
            or self.kind == "prediction_resolve"
        )


@dataclass
class GraphEdge:
    src: str
    dst: str
    rel: str  # precedes | arms | confirms | cancels | boosts
    lag_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"src": self.src, "dst": self.dst, "rel": self.rel, "lag_ms": round(self.lag_ms, 2)}


@dataclass
class MatchPair:
    fast_id: str
    confirm_id: str
    lag_ms: float
    fast_kind: str = ""
    confirm_kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DriveGraph:
    """Causal time-DAG for one drive segment."""

    drive_id: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    started_ns: int | None = None
    ended_ns: int | None = None
    node_cap: int = DEFAULT_MAX_DRIVE_GRAPH_NODES
    nodes_truncated: bool = False
    raw_node_count: int = 0

    # ── builders ──────────────────────────────────────────────────────────

    @classmethod
    def from_events(
        cls,
        drive_id: str,
        events: Iterable[Any],
        context: dict[str, Any] | None = None,
        *,
        started_ns: int | None = None,
        ended_ns: int | None = None,
        max_nodes: int | None = None,
    ) -> DriveGraph:
        nodes: list[GraphNode] = []
        for i, ev in enumerate(events or []):
            d = _as_event_dict(ev)
            if not d:
                continue
            cns = int(d.get("clock_ns") or 0)
            if cns <= 0:
                continue
            kind = str(d.get("kind") or "event")
            nodes.append(
                GraphNode(
                    node_id=f"{drive_id}:{i}:{kind}",
                    clock_ns=cns,
                    kind=kind,
                    path=str(d.get("path") or ""),
                    message=str(d.get("message") or "")[:120],
                    reason=str(d.get("reason") or "")[:120],
                    frame_seq=d.get("frame_seq"),
                    coupling=_opt_float(d.get("coupling")),
                    factual=d.get("factual"),
                    payload=dict(d.get("payload") or {})
                    if isinstance(d.get("payload"), dict)
                    else {},
                )
            )
        nodes.sort(key=lambda n: n.clock_ns)
        cap = resolve_max_nodes(max_nodes)
        raw_n = len(nodes)
        truncated = raw_n > cap
        if truncated:
            nodes = nodes[-cap:]
        g = cls(
            drive_id=str(drive_id or "drive"),
            nodes=nodes,
            context=dict(context or {}),
            started_ns=started_ns or (nodes[0].clock_ns if nodes else None),
            ended_ns=ended_ns or (nodes[-1].clock_ns if nodes else None),
            node_cap=cap,
            nodes_truncated=truncated,
            raw_node_count=raw_n,
        )
        g._build_edges()
        return g

    @classmethod
    def from_timeline_drive(cls, timeline: Any, drive: Any) -> DriveGraph | None:
        """Build graph from SessionTimeline + DriveSegment (or dict)."""
        if timeline is None or drive is None:
            return None
        try:
            if hasattr(drive, "drive_id"):
                did = drive.drive_id
                started = drive.started_ns
                ended = drive.ended_ns
                ctx = dict(getattr(drive, "context", None) or {})
            elif isinstance(drive, dict):
                did = drive.get("drive_id") or "drive"
                started = drive.get("started_ns")
                ended = drive.get("ended_ns")
                ctx = dict(drive.get("context") or {})
            else:
                return None

            # Bound the graph. recent(0) used to copy the entire 2000-event
            # log and O(n²) _build_edges froze Deck /health (live 2026-08-14).
            cap = resolve_max_nodes()
            events: list[Any] = []
            all_ev = list(timeline.recent(64)) if hasattr(timeline, "recent") else []
            if started is not None and hasattr(timeline, "events_in_window"):
                t1 = (
                    int(ended)
                    if ended is not None
                    else (all_ev[-1].clock_ns if all_ev else int(started))
                )
                events = list(timeline.events_in_window(int(started), int(t1)))[-cap:]
            if not events:
                events = all_ev[-cap:]

            return cls.from_events(
                str(did),
                events,
                context=ctx,
                started_ns=int(started) if started is not None else None,
                ended_ns=int(ended) if ended is not None else None,
                max_nodes=cap,
            )
        except Exception as e:
            log.debug("from_timeline_drive failed: %s", e)
            return None

    def _build_edges(self) -> None:
        """O(n²) fine for small drives; n typically < 50."""
        self.edges = []
        n = self.nodes
        for i, a in enumerate(n):
            # Temporal chain to next
            if i + 1 < len(n):
                b = n[i + 1]
                lag = (b.clock_ns - a.clock_ns) / 1e6
                self.edges.append(GraphEdge(a.node_id, b.node_id, "precedes", lag_ms=lag))

            # Semantic edges to later nodes
            for b in n[i + 1 :]:
                lag = (b.clock_ns - a.clock_ns) / 1e6
                if lag < 0:
                    continue
                # arms: arm → open or resolve
                if a.kind in _ARM_KINDS and b.kind in (
                    _OPEN_KINDS | _RESOLVE_KINDS | {"confirm_chat"}
                ):
                    if lag <= DEFAULT_MATCH_LAG_MS * 2:
                        self.edges.append(GraphEdge(a.node_id, b.node_id, "arms", lag_ms=lag))
                # confirms: any fast → later confirm within lag
                if a.is_fast and b.is_confirm and lag <= DEFAULT_MATCH_LAG_MS:
                    self.edges.append(GraphEdge(a.node_id, b.node_id, "confirms", lag_ms=lag))
                # cancels
                if a.kind in _ARM_KINDS | _OPEN_KINDS and b.kind in _CANCEL_KINDS:
                    self.edges.append(GraphEdge(a.node_id, b.node_id, "cancels", lag_ms=lag))
                # boosts: heat within 400ms before next act
                if (
                    a.is_fast
                    and (b.clock_ns - a.clock_ns) <= BOOST_WINDOW_NS
                    and a.node_id != b.node_id
                ):
                    if b.kind not in _CANCEL_KINDS:
                        self.edges.append(GraphEdge(a.node_id, b.node_id, "boosts", lag_ms=lag))

    # ── analytics ─────────────────────────────────────────────────────────

    def phase(self) -> str:
        """empty|pressure|armed|open|resolved|cancelled|active"""
        if not self.nodes:
            return "empty"
        kinds = {n.kind for n in self.nodes}
        if kinds & _RESOLVE_KINDS or any(n.kind == "prediction_resolve" for n in self.nodes):
            return "resolved"
        if kinds & _CANCEL_KINDS:
            # cancel without later resolve
            last = self.nodes[-1]
            if last.kind in _CANCEL_KINDS:
                return "cancelled"
        if kinds & _OPEN_KINDS:
            return "open"
        if kinds & _ARM_KINDS:
            return "armed"
        if any(n.is_fast for n in self.nodes):
            return "pressure"
        if any(n.is_confirm for n in self.nodes):
            return "active"
        return "active"

    def match_fast_confirm(self, max_lag_ms: float = DEFAULT_MATCH_LAG_MS) -> list[MatchPair]:
        """Greedy: each confirm takes nearest prior unmatched fast within lag."""
        fasts = [n for n in self.nodes if n.is_fast and n.kind not in _CANCEL_KINDS]
        confirms = [n for n in self.nodes if n.is_confirm]
        used_fast: set[str] = set()
        pairs: list[MatchPair] = []
        for c in confirms:
            best: GraphNode | None = None
            best_lag = float("inf")
            for f in fasts:
                if f.node_id in used_fast:
                    continue
                if f.clock_ns > c.clock_ns:
                    continue
                lag = (c.clock_ns - f.clock_ns) / 1e6
                if lag > max_lag_ms:
                    continue
                if lag < best_lag:
                    best_lag = lag
                    best = f
            if best is not None:
                used_fast.add(best.node_id)
                pairs.append(
                    MatchPair(
                        fast_id=best.node_id,
                        confirm_id=c.node_id,
                        lag_ms=round(best_lag, 2),
                        fast_kind=best.kind,
                        confirm_kind=c.kind,
                    )
                )
        return pairs

    def climax_score(self) -> dict[str, Any]:
        """Heuristic climax: fast+confirm match, coupling, resolve weight."""
        pairs = self.match_fast_confirm()
        has_fast = any(n.is_fast for n in self.nodes)
        has_confirm = any(n.is_confirm for n in self.nodes)
        has_cancel = any(n.kind in _CANCEL_KINDS for n in self.nodes)
        has_resolve = any(n.kind in _RESOLVE_KINDS for n in self.nodes)

        score = 0.0
        if has_fast:
            score += 0.15
        if has_confirm:
            score += 0.2
        if pairs:
            score += 0.35 * min(
                1.0, len(pairs) / max(1, sum(1 for n in self.nodes if n.is_confirm))
            )
        if has_resolve:
            score += 0.25
        if has_cancel and not has_resolve:
            score *= 0.35  # cancel-only drives score lower
        # coupling peak
        coups = [n.coupling for n in self.nodes if n.coupling is not None]
        if coups:
            score += 0.15 * min(1.0, max(coups))
        score = max(0.0, min(1.0, score))

        # best node: confirmed score-play > matched confirm > coupling > last
        self.mark_stale_after_rollback()
        live = [n for n in self.nodes if not n.stale_after_rollback]
        best: GraphNode | None = None
        plays = [n for n in live if _is_score_play(n)]
        if plays:
            best = plays[-1]
        if best is None and pairs:
            cid = pairs[-1].confirm_id
            best = next((n for n in live if n.node_id == cid), None)
        if best is None and coups:
            best = max(
                (n for n in live if n.coupling is not None),
                key=lambda n: float(n.coupling or 0),
            )
        if best is None and live:
            best = live[-1]
        if best is None and self.nodes:
            best = self.nodes[-1]

        match_rate = 0.0
        n_confirm = sum(1 for n in self.nodes if n.is_confirm)
        if n_confirm > 0:
            match_rate = len(pairs) / n_confirm
        elif pairs:
            match_rate = 1.0

        return {
            "score": round(score, 4),
            "best_node": best.node_id if best else None,
            "best_label": best.label if best else None,
            "best_kind": best.kind if best else None,
            "best_path": best.path if best else None,
            "has_fast_confirm": bool(pairs),
            "match_count": len(pairs),
            "match_rate": round(match_rate, 4),
            "has_resolve": has_resolve,
            "has_cancel_only": has_cancel and not has_resolve,
        }

    def mark_stale_after_rollback(self) -> None:
        """Demote t0 board / chat dumps that preceded a score rollback."""
        roll_ns: int | None = None
        for n in self.nodes:
            blob = f"{n.kind} {n.reason} {n.message}".lower()
            if "rollback" in blob or n.payload.get("rollback"):
                roll_ns = n.clock_ns if roll_ns is None else min(roll_ns, n.clock_ns)
        if roll_ns is None:
            return
        start = self.started_ns if self.started_ns is not None else (
            self.nodes[0].clock_ns if self.nodes else 0
        )
        for n in self.nodes:
            if n.clock_ns >= roll_ns:
                continue
            if _is_t0_board(n, start) or n.kind in _BOARD_DUMP_KINDS:
                n.stale_after_rollback = True

    def ranked_chapter_nodes(self, k: int = 8) -> list[GraphNode]:
        """Chapter candidates: confirmed score-plays beat t0 board dumps."""
        self.mark_stale_after_rollback()
        pairs = self.match_fast_confirm()
        pair_ids = {p.confirm_id for p in pairs} | {p.fast_id for p in pairs}
        start = self.started_ns if self.started_ns is not None else (
            self.nodes[0].clock_ns if self.nodes else 0
        )
        scored: list[tuple[float, GraphNode]] = []
        for n in self.nodes:
            w = 0.0
            if n.node_id in pair_ids:
                w += 3.0
            if n.kind in _RESOLVE_KINDS:
                w += 2.5
            if n.kind in _ARM_KINDS:
                w += 2.0
            if n.kind in ("fast_clip", "confirm_clip"):
                w += 2.0
            if n.kind in ("fast_chat", "confirm_chat"):
                w += 1.0
            if _is_score_play(n):
                w += 8.0
            if _is_t0_board(n, start):
                w -= 4.0
            if n.stale_after_rollback:
                w -= 6.0
            if n.coupling is not None:
                w += float(n.coupling)
            if w > 0:
                scored.append((w, n))
        scored.sort(key=lambda x: (-x[0], x[1].clock_ns))
        top = [n for _, n in scored[: max(1, int(k))]]
        top.sort(key=lambda n: n.clock_ns)
        return top

    def summary(self) -> dict[str, Any]:
        climax = self.climax_score()
        pairs = self.match_fast_confirm()
        ph = self.phase()
        return {
            "drive_id": self.drive_id,
            "phase": ph,
            "node_count": len(self.nodes),
            "node_cap": self.node_cap,
            "nodes_truncated": bool(self.nodes_truncated),
            "raw_node_count": self.raw_node_count,
            "edge_count": len(self.edges),
            "climax": climax,
            "match_rate": climax.get("match_rate", 0.0),
            "matches": [p.to_dict() for p in pairs[:12]],
            "started_ns": self.started_ns,
            "ended_ns": self.ended_ns,
            "context": self.context,
        }

    def to_dict(self, *, include_nodes: bool = False) -> dict[str, Any]:
        d = self.summary()
        if include_nodes:
            d["nodes"] = [n.to_dict() for n in self.nodes]
            d["edges"] = [e.to_dict() for e in self.edges[:80]]
        return d

    def why_line(self) -> str | None:
        """Prefer graph climax for Deck Why strip."""
        if not self.nodes:
            return None
        cl = self.climax_score()
        ph = self.phase()
        label = cl.get("best_label") or "—"
        path = cl.get("best_path") or "—"
        sc = cl.get("score", 0)
        return f"{ph} · climax {sc:.2f} · {label} · path={path}"


def active_drive_graph(timeline: Any = None) -> DriveGraph | None:
    """Helper: graph for active or last closed drive on process timeline."""
    try:
        if timeline is None:
            from qoresence.agents.session_timeline import get_session_timeline

            timeline = get_session_timeline()
        drive = timeline.active_drive() if hasattr(timeline, "active_drive") else None
        if drive is None:
            drives = timeline.drives() if hasattr(timeline, "drives") else []
            drive = drives[-1] if drives else None
        if drive is None:
            return None
        return DriveGraph.from_timeline_drive(timeline, drive)
    except Exception as e:
        log.debug("active_drive_graph failed: %s", e)
        return None


def _as_event_dict(ev: Any) -> dict[str, Any]:
    if ev is None:
        return {}
    if hasattr(ev, "to_dict"):
        try:
            return dict(ev.to_dict())
        except Exception:
            pass
    if isinstance(ev, dict):
        return ev
    # TimelineEvent-like
    out: dict[str, Any] = {}
    for k in (
        "clock_ns",
        "kind",
        "path",
        "message",
        "reason",
        "frame_seq",
        "coupling",
        "factual",
        "payload",
        "drive_id",
        "buttons",
    ):
        if hasattr(ev, k):
            out[k] = getattr(ev, k)
    return out


def _opt_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None
