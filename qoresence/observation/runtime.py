"""Opt-in observation worker. Capture callbacks enqueue; disk/encoding run elsewhere."""

from __future__ import annotations

import json
import threading
from collections import deque
from copy import deepcopy
from pathlib import Path
from queue import Empty, Full, Queue

from .lifecycle import POLICY, normalize_visual, reduce_observation
from .present import present_snapshot


class ObservationRuntime:
    def __init__(self, bus, journal: Path, *, export=None, queue_size=128):
        self.bus, self.journal, self.export = bus, Path(journal), export
        self.queue = Queue(maxsize=queue_size)
        self.clips = Queue(maxsize=4)
        self.records = {}
        self.revisions = deque(maxlen=128)
        self.current = None
        self.dropped = 0
        self.seen_dropped = 0
        self.completions = deque()
        self.persistence_error = None
        self.worker_error = None
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.unsubscribe = None
        self.worker = None
        self.clip_worker = None

    def start(self):
        self.unsubscribe = self.bus.subscribe(self._on_event)
        self.worker = threading.Thread(target=self._run, daemon=True, name="observations")
        self.clip_worker = threading.Thread(
            target=self._clips, daemon=True, name="observation-clips"
        )
        self.clip_worker.start()
        self.worker.start()
        return self

    def _on_event(self, event):
        event_type = getattr(event, "type", "")
        event_type = getattr(event_type, "value", event_type)
        if str(event_type) != "visual_context" or self.stopping.is_set():
            return
        try:
            self.queue.put_nowait(event)
        except Full:
            self.dropped += 1

    def snapshot(self, *, include_journal: bool = False):
        with self.lock:
            out = {
                "schema": "qoresence-observations-1",
                "enabled": True,
                "session_id": str(getattr(self.bus, "session_id", "") or ""),
                "records": deepcopy(list(self.records.values())[-32:]),
                "revisions": deepcopy(list(self.revisions)),
                "dropped": self.dropped,
                "persistence_error": self.persistence_error,
                "worker_error": self.worker_error,
            }
        if include_journal:
            try:
                out["journal"] = self._read_journal()
            except Exception as exc:
                out["persistence_error"] = out["persistence_error"] or type(exc).__name__
                out["journal"] = []
            return out
        return present_snapshot(out)

    def _read_journal(self) -> list[dict]:
        if not self.journal.exists():
            return []
        rows = []
        for line in self.journal.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("observation journal row is not an object")
            rows.append(row)
        return rows

    def stop(self):
        if self.unsubscribe:
            self.unsubscribe()
            self.unsubscribe = None
        self.stopping.set()
        if self.clip_worker is not None:
            self.clip_worker.join(timeout=5)
        if self.worker is not None:
            self.worker.join(timeout=5)

    def process(self, evidence):
        previous = (
            self.records.get(evidence.get("observation_id"))
            if evidence["kind"] == "clip"
            else self.current
        )
        record = reduce_observation(previous, evidence)
        if record is None or record == previous:
            return
        row = {
            "policy_version": POLICY,
            "evidence": deepcopy(evidence),
            "record": deepcopy(record),
        }
        try:
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            with self.journal.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                    + "\n"
                )
        except Exception as exc:
            with self.lock:
                self.persistence_error = type(exc).__name__
        with self.lock:
            observation_id = record["observation_id"]
            self.records[observation_id] = deepcopy(record)
            self.revisions.append(deepcopy(record))
            if evidence["kind"] != "clip" or (
                self.current and observation_id == self.current["observation_id"]
            ):
                self.current = deepcopy(record)
            while len(self.records) > 64:
                del self.records[next(iter(self.records))]
        from qoresence.core.types import SourceLobe

        self.bus.emit_raw(
            SourceLobe.AGENT,
            "observation_revision",
            record,
            clock_ns_override=evidence["tick"]["clock_ns"],
        )
        if record["end_ns"] is not None and (previous is None or previous["end_ns"] is None):
            if self.export is not None:
                try:
                    self.clips.put_nowait(deepcopy(record))
                except Full:
                    self._clip_result(record, "unavailable", reason="export_queue_full")
            else:
                self._clip_result(record, "unavailable", reason="export_disabled")

    def _clip_result(self, record, status, **extra):
        observation_id = record["observation_id"]
        revision = int(record["revision"])
        evidence_id = f"{observation_id}:clip:r{revision}"
        event = {
            "kind": "clip",
            "session_id": record["session_id"],
            "observation_id": observation_id,
            "evidence_id": evidence_id,
            "tick": {
                "clock_ns": int(record["last_clock_ns"]),
                "frame_seq": 0,
                "ticket_id": None,
                "ticket_kind": None,
                "hid_edge": None,
                "score_digits": None,
                "score_vlm_locked": False,
                "evidence_id": evidence_id,
            },
            "clip": {
                "status": status,
                "observation_id": observation_id,
                "revision": revision,
                **extra,
            },
        }
        self.completions.append(event)

    def _clips(self):
        while not self.stopping.is_set() or not self.clips.empty():
            try:
                record = self.clips.get(timeout=0.05)
            except Empty:
                continue
            try:
                result = self.export(record)
                if (
                    result
                    and Path(result.path).is_file()
                    and Path(result.path).suffix == ".mp4"
                    and Path(result.path).stat().st_size > 0
                ):
                    self._clip_result(record, "available", filename=Path(result.path).name)
                else:
                    self._clip_result(record, "unavailable", reason="interval_not_buffered")
            except Exception as exc:
                self._clip_result(record, "failed", reason=type(exc).__name__)
            finally:
                self.clips.task_done()

    def _run(self):
        while (
            not self.stopping.is_set()
            or not self.queue.empty()
            or self.clip_worker.is_alive()
            or self.completions
        ):
            try:
                while self.completions:
                    self.process(self.completions.popleft())
                event = self.queue.get(timeout=0.05)
            except Empty:
                continue
            try:
                evidence = normalize_visual(event.to_dict())
                if evidence:
                    if self.dropped != self.seen_dropped and self.current:
                        gap_id = evidence["evidence_id"] + ":gap"
                        gap_tick = deepcopy(evidence["tick"])
                        gap_tick["evidence_id"] = gap_id
                        self.process(dict(evidence, kind="gap", evidence_id=gap_id, tick=gap_tick))
                        self.seen_dropped = self.dropped
                    self.process(evidence)
            except Exception as exc:
                self.worker_error = type(exc).__name__
            finally:
                self.queue.task_done()


_runtime = None


def start_observations(bus, journal, *, export=None):
    global _runtime
    _runtime = ObservationRuntime(bus, journal, export=export)
    return _runtime.start()


def observations_snapshot():
    empty = {
        "schema": "qoresence-observations-1",
        "enabled": False,
        "session_id": "",
        "records": [],
        "revisions": [],
    }
    return present_snapshot(_runtime.snapshot() if _runtime else empty)


def observations_export_snapshot():
    """Return the live view plus the durable journal required for Recap hashing."""
    return (
        _runtime.snapshot(include_journal=True)
        if _runtime
        else {
            "schema": "qoresence-observations-1",
            "enabled": False,
            "session_id": "",
            "records": [],
            "revisions": [],
            "journal": [],
        }
    )
