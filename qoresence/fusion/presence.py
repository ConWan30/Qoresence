"""
Qoresence Presence Fusion Engine — Phase 6

Consumes events from RetinaEventBus, produces PresenceReport with
presence_sync_ok and weighted verdict across all lobes.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from qoresence.core import (
    RetinaEventBus,
    SourceLobe,
    EventType,
    clock_ns,
    FusionWeights,
    RetinaUnifiedConfig,
)

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class LobeContribution:
    """Contribution from a single lobe to the fused verdict."""
    lobe: SourceLobe
    weight: float
    score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    last_event_ns: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Anomaly:
    """Cross-lobe anomaly detection result."""
    type: str  # "temporal_desync" | "spatial_mismatch" | "missing_lobe" | "contradiction"
    severity: str  # "low" | "medium" | "high"
    description: str
    lobes_involved: list[SourceLobe]
    timestamp_ns: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PresenceReport:
    """Fused presence report output."""
    session_id: str
    clock_ns: int
    session_head_ns: int
    presence_sync_ok: bool
    weighted_verdict: str  # "present" | "likely_present" | "uncertain" | "absent"
    lobe_contributions: dict[str, float]  # lobe -> contribution score
    anomalies: list[Anomaly]
    confidence: float  # Overall confidence 0.0-1.0
    fusion_weights: dict[str, float]  # lobe -> weight used
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSONL/WebSocket."""
        return {
            "session_id": self.session_id,
            "clock_ns": self.clock_ns,
            "session_head_ns": self.session_head_ns,
            "presence_sync_ok": self.presence_sync_ok,
            "weighted_verdict": self.weighted_verdict,
            "lobe_contributions": self.lobe_contributions,
            "anomalies": [
                {
                    "type": a.type,
                    "severity": a.severity,
                    "description": a.description,
                    "lobes_involved": [l.value for l in a.lobes_involved],
                    "timestamp_ns": a.timestamp_ns,
                    "details": a.details,
                }
                for a in self.anomalies
            ],
            "confidence": self.confidence,
            "fusion_weights": self.fusion_weights,
            "details": self.details,
        }


# ──────────────────────────────────────────────────────────────────────────────
# FUSION ENGINE
# ──────────────────────────────────────────────────────────────────────────────

class PresenceFusionEngine:
    """
    Fuses multi-lobe events into a unified presence verdict.

    Subscribes to RetinaEventBus, maintains per-lobe state,
    computes weighted verdict, detects anomalies.
    """

    def __init__(
        self,
        config: RetinaUnifiedConfig,
        bus: RetinaEventBus,
    ):
        self.config = config
        self.bus = bus
        self.session_id = config.session_id
        self.session_head_ns = config.session_head_ns

        # Fusion weights from config
        self.weights = {
            SourceLobe.STREAMER: config.fusion_weights.streamer_presence_sync,
            SourceLobe.CONTROLLER: config.fusion_weights.controller_causal_density,
            SourceLobe.SCREEN: config.fusion_weights.screen_coupling_score,
            SourceLobe.OUTCOME: config.fusion_weights.outcome_coherence,
            SourceLobe.VISUAL: config.fusion_weights.visual_confirmation,
        }

        # Per-lobe state
        self._lobe_state: dict[SourceLobe, dict[str, Any]] = defaultdict(dict)
        self._lobe_last_event_ns: dict[SourceLobe, int] = {}
        self._lobe_event_counts: dict[SourceLobe, int] = defaultdict(int)

        # Presence sync (from streamer)
        self._presence_sync_ok = False
        self._last_controller_sync_ns = 0

        # Anomalies
        self._anomalies: list[Anomaly] = []
        self._max_anomalies = 100

        # Thread safety
        self._lock = threading.RLock()

        # Subscribe to bus
        self._unsubscribe = bus.subscribe(self._on_event)

        # Report callback (optional)
        self._report_callback: Optional[Callable[[PresenceReport], None]] = None

        # Emit session_start
        self._emit_report(force=True)

    def set_report_callback(self, callback: Callable[[PresenceReport], None]) -> None:
        """Set callback for when new report is generated."""
        self._report_callback = callback

    def stop(self) -> None:
        """Stop fusion engine."""
        self._unsubscribe()

    # ──────────────────────────────────────────────────────────────────────────
    # EVENT HANDLER
    # ──────────────────────────────────────────────────────────────────────────

    def _on_event(self, event) -> None:
        """Process incoming event from bus."""
        with self._lock:
            # Ignore our own presence_report emissions to prevent recursion
            if event.type == "presence_report":
                return

            lobe = event.source_lobe
            now_ns = event.clock_ns

            # Track event timing
            self._lobe_last_event_ns[lobe] = now_ns
            self._lobe_event_counts[lobe] += 1

            # Update per-lobe state based on event type
            self._update_lobe_state(lobe, event)

            # Check for anomalies
            self._check_anomalies(now_ns)

            # Emit updated report
            self._emit_report()

    def _update_lobe_state(self, lobe: SourceLobe, event) -> None:
        """Update lobe state from event."""
        state = self._lobe_state[lobe]
        payload = event.payload

        if lobe == SourceLobe.STREAMER:
            if event.type == EventType.ACTIVITY:
                state["activity_level"] = payload.get("level", "idle")
                state["motion"] = payload.get("motion", 0.0)
                state["presence_sync_ok"] = payload.get("presence_sync_ok", False)
                state["last_controller_s_ago"] = payload.get("last_controller_s_ago")
                self._presence_sync_ok = payload.get("presence_sync_ok", False)
                if payload.get("last_controller_s_ago") is not None:
                    self._last_controller_sync_ns = event.clock_ns - int(payload["last_controller_s_ago"] * 1e9)

            elif event.type == EventType.FRAME_STATS:
                state["fps"] = payload.get("fps_meas", 0.0)
                state["frames"] = payload.get("n", 0)
                state["presence_sync_ok"] = payload.get("presence_sync_ok", False)

            elif event.type == EventType.ZONE:
                zone_id = payload.get("zone_id")
                if zone_id:
                    state[f"zone_{zone_id}"] = {
                        "state": payload.get("state"),
                        "delta": payload.get("delta"),
                        "presence_sync_ok": payload.get("presence_sync_ok", False),
                    }

        elif lobe == SourceLobe.CONTROLLER:
            if event.type == EventType.TRIGGER_ONSET:
                state.setdefault("trigger_onsets", []).append({
                    "trigger": payload.get("trigger"),
                    "amplitude": payload.get("amplitude"),
                    "ts": event.clock_ns,
                })
                state["causal_density"] = len(state["trigger_onsets"])

            elif event.type == EventType.STICK_MOTION:
                state.setdefault("stick_motions", []).append({
                    "stick": payload.get("stick"),
                    "x": payload.get("x"),
                    "y": payload.get("y"),
                    "ts": event.clock_ns,
                })

            elif event.type == EventType.TREMOR_SAMPLE:
                state.setdefault("tremor_samples", []).append({
                    "gyro": payload.get("gyro"),
                    "accel": payload.get("accel"),
                    "ts": event.clock_ns,
                })

            elif event.type == EventType.CONTROLLER_EVENT:
                if "causal_parent_ns" in payload:
                    state["last_causal_parent_ns"] = payload["causal_parent_ns"]

        elif lobe == SourceLobe.SCREEN:
            if event.type == EventType.COUPLING_SCORE:
                state["coupling_score"] = payload.get("coupling_score", 0.0)
                state["negative_control"] = payload.get("negative_control", 0.0)
                state["best_lag_ms"] = payload.get("best_lag_ms", 0.0)

            elif event.type == EventType.CV_MOTION:
                state["cv_motion"] = payload.get("motion", 0.0)

            elif event.type == EventType.OCR_HUD:
                state["ocr_hud"] = payload.get("text", "")

        elif lobe == SourceLobe.OUTCOME:
            if event.type == EventType.OUTCOME_EVENT:
                state.setdefault("outcome_events", []).append({
                    "event_name": payload.get("event_name"),
                    "confidence": payload.get("confidence"),
                    "fields": payload.get("fields", {}),
                    "ts": event.clock_ns,
                })
                state["outcome_coherence"] = min(1.0, len(state["outcome_events"]) * 0.1)

        elif lobe == SourceLobe.VISUAL:
            if event.type == EventType.VISUAL_CONTEXT:
                state["game_state"] = payload.get("game_state")
                state["confidence"] = payload.get("confidence", 0.0)
                state["game_category"] = payload.get("game_category")

            elif event.type == EventType.CROSS_MODAL_VERDICT:
                state["cross_modal_verdict"] = payload.get("verdict")
                state["cross_modal_confidence"] = payload.get("confidence", 0.0)

    # ──────────────────────────────────────────────────────────────────────────
    # ANOMALY DETECTION
    # ──────────────────────────────────────────────────────────────────────────

    def _check_anomalies(self, now_ns: int) -> None:
        """Detect cross-lobe anomalies."""
        anomalies = []

        # 1. Temporal desync - lobes not emitting recently
        for lobe, weight in self.weights.items():
            if weight > 0 and lobe in self._lobe_last_event_ns:
                age_ns = now_ns - self._lobe_last_event_ns[lobe]
                if age_ns > 5_000_000_000:  # 5 seconds
                    anomalies.append(Anomaly(
                        type="temporal_desync",
                        severity="medium" if age_ns < 30_000_000_000 else "high",
                        description=f"Lobe {lobe.value} silent for {age_ns / 1e9:.1f}s",
                        lobes_involved=[lobe],
                        timestamp_ns=now_ns,
                        details={"age_ns": age_ns, "weight": weight},
                    ))

        # 2. Presence sync mismatch - streamer says synced but controller stale
        if (SourceLobe.STREAMER in self._lobe_state and
            SourceLobe.CONTROLLER in self._lobe_last_event_ns):

            streamer_state = self._lobe_state[SourceLobe.STREAMER]
            if streamer_state.get("presence_sync_ok") is True:
                last_ctrl = self._lobe_last_event_ns[SourceLobe.CONTROLLER]
                age_ns = now_ns - last_ctrl
                if age_ns > 10_000_000_000:  # 10 seconds
                    anomalies.append(Anomaly(
                        type="contradiction",
                        severity="high",
                        description="Streamer reports presence_sync but controller inactive >10s",
                        lobes_involved=[SourceLobe.STREAMER, SourceLobe.CONTROLLER],
                        timestamp_ns=now_ns,
                        details={"controller_age_ns": age_ns},
                    ))

        # 3. Missing enabled lobes
        if self.config.streamer.enabled and SourceLobe.STREAMER not in self._lobe_last_event_ns:
            anomalies.append(Anomaly(
                type="missing_lobe",
                severity="high",
                description="Streamer lobe enabled but no events received",
                lobes_involved=[SourceLobe.STREAMER],
                timestamp_ns=now_ns,
            ))

        if self.config.controller.enabled and SourceLobe.CONTROLLER not in self._lobe_last_event_ns:
            anomalies.append(Anomaly(
                type="missing_lobe",
                severity="high",
                description="Controller lobe enabled but no events received",
                lobes_involved=[SourceLobe.CONTROLLER],
                timestamp_ns=now_ns,
            ))

        # 4. Outcome without controller (for games requiring input)
        if (self.config.outcome.enabled and
            self.config.controller.enabled and
            SourceLobe.OUTCOME in self._lobe_state and
            SourceLobe.CONTROLLER in self._lobe_last_event_ns):

            outcome_state = self._lobe_state[SourceLobe.OUTCOME]
            last_ctrl = self._lobe_last_event_ns[SourceLobe.CONTROLLER]
            if outcome_state.get("outcome_events") and (now_ns - last_ctrl) > 5_000_000_000:
                anomalies.append(Anomaly(
                    type="spatial_mismatch",
                    severity="medium",
                    description="Outcome events detected but no recent controller input",
                    lobes_involved=[SourceLobe.OUTCOME, SourceLobe.CONTROLLER],
                    timestamp_ns=now_ns,
                ))

        # Add new anomalies (avoid duplicates)
        for anomaly in anomalies:
            if not self._anomaly_exists(anomaly):
                self._anomalies.append(anomaly)
                log.warning(f"Anomaly detected: {anomaly.type} - {anomaly.description}")

        # Trim old anomalies
        if len(self._anomalies) > self._max_anomalies:
            self._anomalies = self._anomalies[-self._max_anomalies:]

    def _anomaly_exists(self, new_anomaly: Anomaly) -> bool:
        """Check if similar anomaly already exists recently."""
        for existing in self._anomalies:
            if (existing.type == new_anomaly.type and
                existing.lobes_involved == new_anomaly.lobes_involved and
                new_anomaly.timestamp_ns - existing.timestamp_ns < 10_000_000_000):
                return True
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # REPORT GENERATION
    # ──────────────────────────────────────────────────────────────────────────

    def _compute_lobe_scores(self) -> dict[SourceLobe, LobeContribution]:
        """Compute score for each lobe."""
        contributions = {}

        for lobe, weight in self.weights.items():
            if weight == 0:
                contributions[lobe] = LobeContribution(
                    lobe=lobe, weight=weight, score=0.0, confidence=0.0,
                    last_event_ns=0, details={}
                )
                continue

            state = self._lobe_state.get(lobe, {})
            last_ns = self._lobe_last_event_ns.get(lobe, 0)

            if lobe == SourceLobe.STREAMER:
                # Streamer: based on presence_sync_ok and activity
                presence = state.get("presence_sync_ok", False)
                activity = state.get("activity_level", "idle")
                score = 1.0 if presence else (0.5 if activity in ("low", "high") else 0.0)
                confidence = 0.9 if presence else 0.5

            elif lobe == SourceLobe.CONTROLLER:
                # Controller: based on causal density (trigger onsets, stick motions)
                causal = state.get("causal_density", 0)
                tremor_count = len(state.get("tremor_samples", []))
                stick_count = len(state.get("stick_motions", []))
                score = min(1.0, (causal * 0.2) + (tremor_count * 0.01) + (stick_count * 0.01))
                confidence = min(1.0, (causal + tremor_count + stick_count) * 0.05)

            elif lobe == SourceLobe.SCREEN:
                # Screen: based on coupling score
                coupling = state.get("coupling_score", 0.0)
                score = max(0.0, min(1.0, coupling))
                confidence = 0.7 if coupling > 0.5 else 0.3

            elif lobe == SourceLobe.OUTCOME:
                # Outcome: based on outcome coherence
                coherence = state.get("outcome_coherence", 0.0)
                score = coherence
                confidence = 0.8 if coherence > 0.5 else 0.4

            elif lobe == SourceLobe.VISUAL:
                # Visual: based on cross-modal verdict
                verdict = state.get("cross_modal_verdict")
                v_conf = state.get("cross_modal_confidence", 0.0)
                score = v_conf if verdict else 0.0
                confidence = v_conf

            else:
                score = 0.0
                confidence = 0.0

            contributions[lobe] = LobeContribution(
                lobe=lobe,
                weight=weight,
                score=score,
                confidence=confidence,
                last_event_ns=last_ns,
                details=state,
            )

        return contributions

    def _compute_weighted_verdict(self, contributions: dict[SourceLobe, LobeContribution]) -> tuple[str, float]:
        """Compute weighted verdict from lobe contributions."""
        total_weight = 0.0
        weighted_sum = 0.0
        total_confidence = 0.0

        for contrib in contributions.values():
            if contrib.weight > 0:
                total_weight += contrib.weight
                weighted_sum += contrib.score * contrib.weight
                total_confidence += contrib.confidence * contrib.weight

        if total_weight == 0:
            return "uncertain", 0.0

        final_score = weighted_sum / total_weight
        overall_confidence = total_confidence / total_weight if total_weight > 0 else 0.0

        # Map score to verdict
        if final_score >= 0.8:
            verdict = "present"
        elif final_score >= 0.5:
            verdict = "likely_present"
        elif final_score >= 0.2:
            verdict = "uncertain"
        else:
            verdict = "absent"

        return verdict, overall_confidence

    def _emit_report(self, force: bool = False) -> None:
        """Generate and emit presence report."""
        with self._lock:
            now_ns = clock_ns()
            contributions = self._compute_lobe_scores()
            verdict, confidence = self._compute_weighted_verdict(contributions)

            # Presence sync ok if streamer reports it
            presence_sync = self._presence_sync_ok

            # Build lobe contributions dict
            lobe_contribs = {lobe.value: round(c.score, 3) for lobe, c in contributions.items()}

            report = PresenceReport(
                session_id=self.session_id,
                clock_ns=now_ns,
                session_head_ns=self.session_head_ns,
                presence_sync_ok=presence_sync,
                weighted_verdict=verdict,
                lobe_contributions=lobe_contribs,
                anomalies=list(self._anomalies),
                confidence=round(confidence, 3),
                fusion_weights={lobe.value: weight for lobe, weight in self.weights.items()},
                details={
                    "lobe_event_counts": dict(self._lobe_event_counts),
                    "anomaly_count": len(self._anomalies),
                },
            )

            # Emit to bus
            self.bus.emit_raw(
                source_lobe=SourceLobe.STREAMER,  # Fusion uses streamer as primary
                event_type="presence_report",
                payload=report.to_dict(),
                clock_ns_override=now_ns,
                session_head_ns=self.session_head_ns,
            )

            # Callback
            if self._report_callback:
                try:
                    self._report_callback(report)
                except Exception as e:
                    log.error(f"Report callback error: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC QUERY METHODS
    # ──────────────────────────────────────────────────────────────────────────

    def get_current_report(self) -> PresenceReport:
        """Get current presence report (generates fresh)."""
        with self._lock:
            now_ns = clock_ns()
            contributions = self._compute_lobe_scores()
            verdict, confidence = self._compute_weighted_verdict(contributions)

            return PresenceReport(
                session_id=self.session_id,
                clock_ns=now_ns,
                session_head_ns=self.session_head_ns,
                presence_sync_ok=self._presence_sync_ok,
                weighted_verdict=verdict,
                lobe_contributions={lobe.value: round(c.score, 3) for lobe, c in contributions.items()},
                anomalies=list(self._anomalies),
                confidence=round(confidence, 3),
                fusion_weights={lobe.value: weight for lobe, weight in self.weights.items()},
                details={
                    "lobe_event_counts": dict(self._lobe_event_counts),
                    "anomaly_count": len(self._anomalies),
                },
            )

    def get_anomalies(self) -> list[Anomaly]:
        """Get current anomalies."""
        with self._lock:
            return list(self._anomalies)

    def get_lobe_stats(self) -> dict[str, Any]:
        """Get per-lobe statistics."""
        with self._lock:
            return {
                "event_counts": dict(self._lobe_event_counts),
                "last_event_age_ns": {
                    lobe.value: clock_ns() - ns
                    for lobe, ns in self._lobe_last_event_ns.items()
                },
                "weights": {lobe.value: weight for lobe, weight in self.weights.items()},
            }


# ──────────────────────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTION
# ──────────────────────────────────────────────────────────────────────────────

def create_fusion_engine(
    config: RetinaUnifiedConfig,
    bus: RetinaEventBus,
) -> PresenceFusionEngine:
    """Create and start fusion engine."""
    return PresenceFusionEngine(config, bus)