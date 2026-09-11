import unittest

from qoresence.compose.clock_notary.envelope import Tick, build_envelope, envelope_from_recap
from qoresence.compose.clock_notary.from_session import recap_from_session_view
from qoresence.compose.clock_notary.io_ledger import (
    canonicalize_out_edge,
    ledger_checks,
    opcode_hash,
    out_edge_from_event,
)
from qoresence.compose.clock_notary.verify import verify_wrap


class IoLedgerTests(unittest.TestCase):
    def test_ps5_absence_is_success(self):
        env = build_envelope(
            session_id="sess-ps5",
            hid_on_console=True,
            ticks=[Tick(10, 1, "c1", "coupling", None, None, False, None)],
        )
        self.assertNotIn("out_edge", env.ticks[0])
        checks = {c["name"]: c for c in ledger_checks(env.to_dict())}
        self.assertTrue(checks["out_edge_honest"]["ok"])
        self.assertTrue(checks["ps5_empty_io_success"]["ok"])

    def test_does_not_invent_from_optical(self):
        self.assertIsNone(out_edge_from_event({"hid_edge": "cross", "score": "14-10"}))
        self.assertIsNone(out_edge_from_event({"output": {"hdmi": True, "opcode": "R1"}}))

    def test_real_output_hashes(self):
        edge = out_edge_from_event({"out_edge": {"kind": "trigger", "opcode": "L2:resist"}})
        self.assertIsNotNone(edge)
        self.assertTrue(edge["opcode_hash"].startswith("sha256:"))
        self.assertEqual(edge["kind"], "trigger")

    def test_waveform_dropped(self):
        self.assertIsNone(canonicalize_out_edge({"present": True, "samples": [0.1, 0.2]}))

    def test_present_without_hash_dropped(self):
        self.assertIsNone(canonicalize_out_edge({"present": True}))

    def test_commitment_changes_when_out_edge_present(self):
        a = build_envelope(session_id="s", ticks=[Tick(1, 1, "t", "coupling", None, None)])
        hashed = opcode_hash("R2:click", kind="rumble")
        b = build_envelope(
            session_id="s",
            ticks=[Tick(1, 1, "t", "coupling", None, None, False, {"present": True, "kind": "rumble", "opcode_hash": hashed, "lag_ns": 8000000})],
        )
        self.assertNotEqual(a.clock_commitment, b.clock_commitment)

    def test_session_view_maps_pad_out_only(self):
        recap = recap_from_session_view(
            {
                "session_id": "sess-io",
                "controller_bodied": False,
                "events": [
                    {
                        "t_start_ns": 5,
                        "frame_seq": 9,
                        "event_id": "e1",
                        "out_edge": {"kind": "led", "opcode": "player-2"},
                    }
                ],
            }
        )
        self.assertIn("out_edge", recap["ticks"][0])
        env = envelope_from_recap(recap)
        self.assertEqual(env.ticks[0]["out_edge"]["kind"], "led")

    def test_verify_does_not_require_out_edge(self):
        env = build_envelope(session_id="s", ticks=[Tick(1, 1, "t", "coupling", None, None)]).to_dict()
        out = verify_wrap(None, env)
        names = [c["name"] for c in out["checks"]]
        self.assertIn("out_edge_honest", names)
        self.assertIn("out_edge_optional", names)
