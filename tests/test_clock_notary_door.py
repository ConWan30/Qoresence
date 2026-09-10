import unittest

from qoresence.compose.clock_notary.door import SEAL_PHRASE, export_door, seal_door, verify_door


VIEW = {
    "session_id": "ncaa-half-1",
    "board_locked": True,
    "controller_bodied": False,
    "events": [
        {
            "event_id": "cpl-1",
            "t_start_ns": 100,
            "frame_seq": 4,
            "score": {"home": 14, "away": 10},
            "input": {},
        }
    ],
}


class DoorTests(unittest.TestCase):
    def test_export_unsealed(self):
        body = export_door(VIEW)
        self.assertTrue(body["ok"])
        self.assertEqual(body["notary"]["status"], "UNSEALED")
        self.assertEqual(body["door"]["live_truth"], "DARK")
        self.assertTrue(body["hid_on_console"])

    def test_bridge_cannot_seal(self):
        env = export_door(VIEW)
        out = seal_door(
            {
                "envelope": env,
                "gamer": "bridge",
                "signed_by": "bridge",
                "granted": True,
                "phrase": SEAL_PHRASE,
                "purpose": "portcert",
            }
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "REFUSED")

    def test_wrong_phrase_refused(self):
        env = export_door(VIEW)
        out = seal_door(
            {
                "envelope": env,
                "gamer": "ConWanZo",
                "signed_by": "ConWanZo",
                "granted": True,
                "phrase": "sure",
                "purpose": "portcert",
            }
        )
        self.assertEqual(out["reason"], "phrase_or_signer")

    def test_gamer_seal_and_verify(self):
        env = export_door(VIEW)
        out = seal_door(
            {
                "envelope": env,
                "gamer": "ConWanZo",
                "signed_by": "ConWanZo",
                "granted": True,
                "phrase": SEAL_PHRASE,
                "purpose": "portcert",
            }
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["status"], "SEALED")
        self.assertIn("Clock Notary SEALED", out["discord_card"])
        self.assertEqual(out["chain"], "paused")
        self.assertEqual(out["locks"]["truth"]["state"], "TRUTH")
        verdict = verify_door(out, env)
        self.assertTrue(verdict["ok"], verdict)
        self.assertEqual(verdict["trust"], "recomputed — producer status field ignored")
