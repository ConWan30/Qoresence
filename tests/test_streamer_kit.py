"""Streamer Kit bundle: scene JSON loads, names match the OBS bridge, page links resolve."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from qoresence.obs.bridge import DEFAULT_TEXT_SOURCE, ObsBridgeConfig

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "streamer-kit"
SCENE_JSON = KIT / "Qoresence_Streamer_Kit.scene.json"
LAUNCHER = KIT / "qoresence-stream.cmd"
PAGE = ROOT / "docs" / "streamer-kit.html"
SCENE = "Qoresence Score"
TEXT = "Qoresence Score Text"


def _collection() -> dict:
    return json.loads(SCENE_JSON.read_text(encoding="utf-8"))


def test_scene_collection_loads_with_obs_shape():
    d = _collection()
    for key in ("name", "current_scene", "current_program_scene", "scene_order", "sources"):
        assert key in d, key
    assert d["current_scene"] == SCENE
    assert [s["name"] for s in d["scene_order"]] == [SCENE]


def test_scene_and_text_source_names():
    srcs = {s["name"]: s for s in _collection()["sources"]}
    assert srcs[SCENE]["id"] == "scene"
    assert srcs[TEXT]["id"].startswith("text_")
    items = srcs[SCENE]["settings"]["items"]
    assert [i["name"] for i in items] == [TEXT]
    assert items[0]["source_uuid"] == srcs[TEXT]["uuid"]
    assert srcs[TEXT]["settings"]["text"] == ""  # blank until a lock
    # OBS shares one namespace for scenes and sources (error 601).
    assert len(srcs) == len(_collection()["sources"])


def test_names_match_bridge_defaults():
    assert ObsBridgeConfig().port == 4455
    # Scene takes the bridge default name, so the launcher must override the text source.
    assert SCENE == DEFAULT_TEXT_SOURCE
    cmd = LAUNCHER.read_text(encoding="utf-8")
    assert f'--obs-text-source "{TEXT}"' in cmd
    assert "--obs " in cmd


def test_launcher_never_hardcodes_password():
    cmd = LAUNCHER.read_text(encoding="utf-8")
    assert "QORESENCE_OBS_PASSWORD_FILE" in cmd
    for line in cmd.splitlines():
        m = re.match(r'\s*set\s+"?QORESENCE_OBS_PASSWORD=(.*)', line, re.I)
        assert not m, line
    assert "--obs-password" not in cmd


def test_bundle_zips(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("bsk", ROOT / "scripts" / "build_streamer_kit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.build(tmp_path / "kit.zip")
    names = zipfile.ZipFile(out).namelist()
    assert "qoresence-streamer-kit/Qoresence_Streamer_Kit.scene.json" in names
    assert "qoresence-streamer-kit/qoresence-stream.cmd" in names


def test_page_links_and_content():
    html = PAGE.read_text(encoding="utf-8")
    assert "mailto:qoresence@mail.grokbot.com" in html
    assert "issues/new?template=streamer_kit_interest.md" in html
    assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "streamer_kit_interest.md").exists()
    assert "$" not in re.sub(r"<code>.*?</code>", "", html)  # no invented pricing
    for href in re.findall(r'href="\./([^"#?]+)', html):
        assert (ROOT / "docs" / href).exists(), href
    for rel in re.findall(r"github.com/ConWan30/Qoresence/(?:blob|tree)/main/([^\"#]+)", html):
        assert (ROOT / rel).exists(), rel
    assert 'href="./streamer-kit.html"' in (ROOT / "docs" / "index.html").read_text(
        encoding="utf-8"
    )
