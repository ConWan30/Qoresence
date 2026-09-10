import json
import unittest
from pathlib import Path

from qoresence.compose.clock_notary.envelope import Tick, build_envelope, envelope_from_recap
from qoresence.compose.clock_notary.locks import LockState, compose_locks
from qoresence.compose.clock_notary.sanitize import strip_truth_leaks
from qoresence.compose.clock_notary.wrap import ConsentRecord, wrap_notary
from qoresence.observation.clock_notary_export import export_from_recap

FIXTURES = (
    Path(__file__).resolve().parents[1]
    / "qoresence"
    / "compose"
    / "clock_notary"
    / "fixtures"
)
GAMER = "0x0Cf36dB57fc4680bcdfC65D1Aff96993C57a4692"


class SanitizeTests(unittest.TestCase):
    def test_strips_phi_and_poep(self):
        dirty = {
            "clock_ns": 1,
            "phi": 0.9,
            "poep_enabled": True,
            "rumble_imu": [1, 2, 3],
            "nested": {"imu_x": 4, "ticket_id": "t1"},
        }
        clean = strip_truth_leaks(dirty)
        self.assertNotIn("phi", clean)
        self.assertNotIn("poep_enabled", clean)
        self.assertNotIn("imu_x", clean["nested"])


class EnvelopeTests(unittest.TestCase):
    def test_unlocked_digits_do_not_serialize(self):
        env = build_envelope(
            session_id="sess-1",
            ticks=[Tick(10, 1, "c1", "coupling", None, "21-17", False)],
        )
        self.assertIsNone(env.ticks[0]["score_digits"])

    def test_export_does_not_seal(self):
        recap = json.loads((FIXTURES / "session-recap.json").read_text())
        body = export_from_recap(recap)
        self.assertEqual(body["notary"]["status"], "UNSEALED")
        self.assertEqual(body["locks"]["truth"]["glyph"], "\u25a1")
        self.assertEqual(body["plane"], "observation")


class WrapRailTests(unittest.TestCase):
    def test_observation_cannot_promote_truth(self):
        locks = compose_locks(
            coupling_ticket=True, same_seq=True, consent_granted=False, wrap_sealed=False
        )
        self.assertEqual(locks.truth, LockState.DARK)

    def test_bridge_consent_refused(self):
        recap = json.loads((FIXTURES / "session-recap.json").read_text())
        env = envelope_from_recap(recap)
        result = wrap_notary(
            env,
            ConsentRecord(gamer=GAMER, granted=True, purpose="portcert", signed_by="bridge"),
        )
        self.assertEqual(result.status, "REFUSED")
