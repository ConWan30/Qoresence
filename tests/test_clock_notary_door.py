import unittest

from qoresence.compose.clock_notary import door as door_mod
from qoresence.compose.clock_notary.door import export_door


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
        self.assertNotIn("seal_phrase", body["door"])
        copy = body["door"]["copy"].lower()
        self.assertIn("eyes only", copy)
        self.assertIn("qortroller", copy)

    def test_seal_door_removed(self):
        self.assertFalse(hasattr(door_mod, "seal_door"))
        self.assertFalse(hasattr(door_mod, "verify_door"))
        self.assertFalse(hasattr(door_mod, "SEAL_PHRASE"))
        self.assertFalse(hasattr(door_mod, "discord_card"))

    def test_http_mount_export_only(self):
        from qoresence.deck import clock_notary_http as http_mod
        import inspect

        src = inspect.getsource(http_mod)
        self.assertIn('/api/session/clock-notary"', src) or self.assertIn(
            "/api/session/clock-notary", src
        )
        self.assertNotIn("/api/session/clock-notary/seal", src)
        self.assertNotIn("/api/session/clock-notary/verify", src)
        self.assertNotIn("seal_door", src)
        self.assertNotIn("verify_door", src)
        self.assertNotIn("wrap_notary", src)
