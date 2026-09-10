import os
import unittest
from unittest import mock

from qoresence.compose.clock_notary.from_session import payload_from_session_view
from qoresence.mcp.clock_notary import handle_wrap_clock_notary


class SessionMapTests(unittest.TestCase):
    def test_unlocked_score_stays_out(self):
        view = {
            "session_id": "s1",
            "board_locked": False,
            "controller_bodied": False,
            "events": [
                {
                    "event_id": "e1",
                    "t_start_ns": 10,
                    "frame_seq": 3,
                    "score": {"home": 14, "away": 10},
                }
            ],
        }
        body = payload_from_session_view(view)
        self.assertTrue(body["ok"])
        self.assertIsNone(body["ticks"][0]["score_digits"])
        self.assertEqual(body["notary"]["status"], "UNSEALED")
        self.assertEqual(body["locks"]["truth"]["glyph"], "\u25a1")
        self.assertTrue(body["hid_on_console"])

    def test_locked_confirm_ticket(self):
        view = {
            "session_id": "s1",
            "board_locked": True,
            "controller_bodied": True,
            "events": [
                {
                    "event_id": "cfm-1",
                    "t_start_ns": 20,
                    "score": {"home": 14, "away": 10},
                    "input": {"button": "R2"},
                }
            ],
        }
        body = payload_from_session_view(view)
        self.assertEqual(body["ticks"][0]["score_digits"], "14-10")
        self.assertEqual(body["ticks"][0]["ticket_kind"], "confirm")
        self.assertFalse(body["hid_on_console"])


class McpWrapTests(unittest.TestCase):
    def test_truth_dest_denied(self):
        out = handle_wrap_clock_notary("qortroller-truth")
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "dest_denied")

    def test_grant_required(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("QORESENCE_WRAP_GRANT_ID", None)
            out = handle_wrap_clock_notary("qoresence-research")
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "grant_missing")
