"""Build a local observation envelope and its clock commitment."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .sanitize import strip_truth_leaks


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


@dataclass(frozen=True)
class Tick:
    clock_ns: int
    frame_seq: int
    ticket_id: str | None
    ticket_kind: str | None
    hid_edge: str | None
    score_digits: str | None
    score_vlm_locked: bool = False

    def as_commit_triple(self) -> dict:
        digits = self.score_digits if self.score_vlm_locked else None
        return {
            "clock_ns": int(self.clock_ns),
            "frame_seq": int(self.frame_seq),
            "ticket_id": self.ticket_id,
            "ticket_kind": self.ticket_kind,
            "hid_edge": self.hid_edge,
            "score_digits": digits,
        }


@dataclass
class ObservationEnvelope:
    schema: str
    session_id: str
    plane: str
    title_plane: str
    hid_on_console: bool
    ticks: list[dict]
    sidecar_hashes: dict[str, str]
    clock_commitment: str
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        body = {
            "schema": self.schema,
            "session_id": self.session_id,
            "plane": self.plane,
            "title_plane": self.title_plane,
            "hid_on_console": self.hid_on_console,
            "ticks": self.ticks,
            "sidecar_hashes": self.sidecar_hashes,
            "clock_commitment": self.clock_commitment,
        }
        if self.extras:
            body["extras"] = self.extras
        return body


SCHEMA = "qoresence.observation-envelope.v0"


def clock_commitment(session_id: str, ticks: list[dict], sidecar_hashes: dict[str, str]) -> str:
    material = {"session_id": session_id, "sidecar_hashes": sidecar_hashes, "ticks": ticks}
    digest = hashlib.sha256(_canonical(material)).hexdigest()
    return f"sha256:{digest}"


def _hash_sidecar_bytes(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def build_envelope(
    *,
    session_id: str,
    ticks: list[Tick],
    sidecars: dict[str, bytes] | None = None,
    title_plane: str = "observation",
    hid_on_console: bool = True,
    extras: dict | None = None,
) -> ObservationEnvelope:
    if not session_id:
        raise ValueError("session_id required")
    if title_plane != "observation":
        raise ValueError("envelope title_plane must stay observation")
    clean_ticks = [strip_truth_leaks(tick.as_commit_triple()) for tick in ticks]
    sidecar_hashes = {name: _hash_sidecar_bytes(raw) for name, raw in (sidecars or {}).items()}
    extras_clean = strip_truth_leaks(extras or {})
    commit = clock_commitment(session_id, clean_ticks, sidecar_hashes)
    return ObservationEnvelope(
        schema=SCHEMA,
        session_id=session_id,
        plane="observation",
        title_plane=title_plane,
        hid_on_console=hid_on_console,
        ticks=clean_ticks,
        sidecar_hashes=sidecar_hashes,
        clock_commitment=commit,
        extras=extras_clean,
    )


def envelope_from_recap(recap: dict) -> ObservationEnvelope:
    recap = strip_truth_leaks(recap)
    session_id = recap.get("session_id") or recap.get("id")
    if not session_id:
        raise ValueError("recap missing session_id")
    ticks: list[Tick] = []
    for raw in recap.get("ticks") or recap.get("civif") or []:
        locked = bool(raw.get("score_vlm_locked") or raw.get("board_locked"))
        kind = raw.get("ticket_kind")
        if kind not in ("coupling", "confirm", None):
            kind = None
        ticks.append(
            Tick(
                clock_ns=int(raw.get("clock_ns") or 0),
                frame_seq=int(raw.get("frame_seq") or raw.get("seq") or 0),
                ticket_id=raw.get("ticket_id"),
                ticket_kind=kind,
                hid_edge=raw.get("hid_edge") or raw.get("button"),
                score_digits=raw.get("score_digits") or raw.get("score"),
                score_vlm_locked=locked,
            )
        )
    sidecars = {}
    for key in ("buttons", "coupling", "otel", "clip"):
        block = recap.get(f"{key}_sha256") or recap.get(key)
        if isinstance(block, (bytes, bytearray)):
            sidecars[key] = bytes(block)
    prehashed = {}
    for key in ("buttons", "coupling", "otel", "clip"):
        digest = recap.get(f"{key}_sha256")
        if isinstance(digest, str):
            prehashed[key] = digest if digest.startswith("sha256:") else f"sha256:{digest}"
    env = build_envelope(
        session_id=str(session_id),
        ticks=ticks,
        sidecars=sidecars or None,
        hid_on_console=bool(recap.get("hid_on_console", True)),
        extras={"prehashed_sidecars": prehashed} if prehashed else None,
    )
    if prehashed:
        merged = dict(env.sidecar_hashes)
        merged.update(prehashed)
        env.sidecar_hashes = merged
        env.clock_commitment = clock_commitment(env.session_id, env.ticks, merged)
    return env
