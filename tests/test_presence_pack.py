import inspect
import unittest
import zipfile
from io import BytesIO

from qoresence.compose.clock_notary.door import export_door
from qoresence.compose.clock_notary.presence_pack import (
    SCHEMA,
    assemble_pack,
    pack_zip_bytes,
)


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


class PresencePackTests(unittest.TestCase):
    def test_assemble_from_export_door(self):
        packed = assemble_pack(export_door(VIEW))
        self.assertTrue(packed["ok"])
        self.assertEqual(packed["manifest"]["schema"], SCHEMA)
        self.assertEqual(packed["manifest"]["sku"], "presence-pack")
        self.assertEqual(packed["manifest"]["plane"], "qoresence-observation")
        self.assertEqual(packed["manifest"]["listing_status"], "draft")
        self.assertEqual(packed["manifest"]["notary"], "UNSEALED")
        self.assertEqual(packed["manifest"]["live_truth"], "DARK")
        self.assertEqual(packed["manifest"]["out_edge"], "omitted")
        self.assertNotIn("out_edge.json", packed["files"])
        raw = pack_zip_bytes(packed["files"])
        names = zipfile.ZipFile(BytesIO(raw)).namelist()
        self.assertIn("MANIFEST.json", names)
        self.assertIn("observation-envelope.json", names)
        self.assertIn("listing-draft.json", names)
        self.assertNotIn("out_edge.json", names)

    def test_refuse_missing_commitment(self):
        packed = assemble_pack({"ok": True, "session_id": "x"})
        self.assertFalse(packed["ok"])
        self.assertEqual(packed["files"], {})

    def test_refuse_forbidden_token(self):
        body = export_door(VIEW)
        body["extras"] = {"note": "humanity claim"}
        packed = assemble_pack(body)
        self.assertFalse(packed["ok"])
        self.assertIn("humanity", packed["error"])

    def test_out_edge_only_when_canonical(self):
        body = export_door(VIEW)
        body["ticks"][0]["out_edge"] = {
            "kind": "button",
            "opcode": "cross",
        }
        packed = assemble_pack(body)
        self.assertTrue(packed["ok"])
        self.assertEqual(packed["manifest"]["out_edge"], "present")
        self.assertIn("out_edge.json", packed["files"])

    def test_empty_hid_is_not_out_edge(self):
        body = export_door(VIEW)
        body["ticks"][0]["hid_edge"] = "R2"
        packed = assemble_pack(body)
        self.assertEqual(packed["manifest"]["out_edge"], "omitted")

    def test_assembler_does_not_import_wrap(self):
        import qoresence.compose.clock_notary.presence_pack as pack_mod

        src = inspect.getsource(pack_mod)
        self.assertNotIn("wrap.py", src)
        self.assertNotIn("from .wrap", src)
        self.assertNotIn("seal_door", src)
        self.assertNotIn("verify_door", src)
        self.assertNotIn("qortroller-truth", src)


class PresencePackHttpTests(unittest.TestCase):
    def test_http_mount_adds_pack_not_seal(self):
        from qoresence.deck import clock_notary_http as http_mod

        src = inspect.getsource(http_mod)
        self.assertIn("/api/session/presence-pack", src)
        self.assertIn("/api/session/presence-pack.zip", src)
        self.assertNotIn("/api/session/clock-notary/seal", src)
        self.assertNotIn("/api/session/clock-notary/verify", src)
        self.assertNotIn("wrap_notary", src)
        self.assertNotIn("seal_door", src)
