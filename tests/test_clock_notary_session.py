import os
import unittest
from unittest import mock

from qoresence.compose.clock_notary.from_session import (
    payload_from_session_view,
    recap_from_session_view,
)
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
        recap = recap_from_session_view(view)
        self.assertIsNone(recap["ticks"][0]["score_digits"])
        self.assertFalse(recap["ticks"][0]["score_vlm_locked"])
        self.assertNotEqual(recap["ticks"][0]["ticket_kind"], "confirm")
        body = payload_from_session_view(view)
        self.assertTrue(body["ok"])
        self.assertIsNone(body["ticks"][0]["score_digits"])
        self.assertNotEqual(body["ticks"][0]["ticket_kind"], "confirm")
        self.assertEqual(body["notary"]["status"], "UNSEALED")
        self.assertEqual(body["locks"]["truth"]["glyph"], "\u25a1")
        self.assertTrue(body["hid_on_console"])

    def test_board_locked_alone_blanks_digits(self):
        """board_locked without ConfirmTicket / score_vlm_locked must not serialize digits."""
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
        recap = recap_from_session_view(view)
        tick = recap["ticks"][0]
        self.assertIsNone(tick["score_digits"])
        self.assertFalse(tick["score_vlm_locked"])
        self.assertNotEqual(tick["ticket_kind"], "confirm")
        body = payload_from_session_view(view)
        self.assertIsNone(body["ticks"][0]["score_digits"])
        self.assertNotEqual(body["ticks"][0]["ticket_kind"], "confirm")
        self.assertFalse(body["hid_on_console"])

    def test_confirm_ticket_and_vlm_lock_exports_digits(self):
        view = {
            "session_id": "s1",
            "board_locked": True,
            "score_vlm_locked": True,
            "confirm_ticket_id": "cfm-1",
            "controller_bodied": True,
            "events": [
                {
                    "event_id": "cfm-1",
                    "confirm_ticket_id": "cfm-1",
                    "ticket_kind": "confirm",
                    "score_vlm_locked": True,
                    "t_start_ns": 20,
                    "score": {"home": 14, "away": 10},
                    "input": {"button": "R2"},
                }
            ],
        }
        recap = recap_from_session_view(view)
        self.assertEqual(recap["ticks"][0]["score_digits"], "14-10")
        self.assertTrue(recap["ticks"][0]["score_vlm_locked"])
        self.assertEqual(recap["ticks"][0]["ticket_kind"], "confirm")
        body = payload_from_session_view(view)
        self.assertEqual(body["ticks"][0]["score_digits"], "14-10")
        self.assertEqual(body["ticks"][0]["ticket_kind"], "confirm")
        self.assertFalse(body["hid_on_console"])

    def test_stale_ticket_fresh_blanks_digits(self):
        view = {
            "session_id": "s1",
            "score_vlm_locked": True,
            "confirm_ticket_id": "cfm-1",
            "ticket_fresh": False,
            "controller_bodied": False,
            "events": [
                {
                    "event_id": "cfm-1",
                    "confirm_ticket_id": "cfm-1",
                    "score_vlm_locked": True,
                    "ticket_fresh": False,
                    "t_start_ns": 20,
                    "score": {"home": 21, "away": 17},
                }
            ],
        }
        recap = recap_from_session_view(view)
        tick = recap["ticks"][0]
        self.assertIsNone(tick["score_digits"])
        self.assertFalse(tick["score_vlm_locked"])
        self.assertNotEqual(tick["ticket_kind"], "confirm")
        body = payload_from_session_view(view)
        self.assertIsNone(body["ticks"][0]["score_digits"])


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
