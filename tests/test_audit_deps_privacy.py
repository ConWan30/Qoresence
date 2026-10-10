"""Guards from the install/privacy audit: base deps, fresh import, no third-party fonts."""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THIRD_PARTY_FONTS = ("fonts.googleapis.com", "fonts.gstatic.com")


def test_requests_is_a_base_dependency():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = {
        re.split(r"[<>=!~\[ ;]", d, maxsplit=1)[0].lower() for d in data["project"]["dependencies"]
    }
    assert "requests" in names


def test_helix_client_imports_in_fresh_interpreter():
    # helix_client imports requests at module top; a base install must provide it.
    r = subprocess.run(
        [sys.executable, "-c", "import qoresence.agents.helix_client"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr


def test_no_html_references_google_fonts():
    pages = list((ROOT / "docs").glob("*.html")) + list(
        (ROOT / "qoresence" / "deck").glob("*.html")
    )
    assert pages
    for page in pages:
        text = page.read_text(encoding="utf-8")
        for host in THIRD_PARTY_FONTS:
            assert host not in text, f"{page.relative_to(ROOT)} references {host}"


def test_deck_fonts_ship_in_package_data():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "deck/fonts/*.woff2" in data["tool"]["setuptools"]["package-data"]["qoresence"]
    assert list((ROOT / "qoresence" / "deck" / "fonts").glob("*.woff2"))


def test_privacy_md_discloses_network_features():
    text = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
    for needle in ("babel-api.testnet.iotex.io", "storage.googleapis.com", "api.quicksilverpro.io"):
        assert needle in text
