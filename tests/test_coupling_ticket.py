"""Coupling ticket mint + heat-speech license (no hardware)."""

from __future__ import annotations

import time

from qoresence.sync.coupling_ticket import (
    get_coupling_book,
    heat_speech,
    license_heat_text,
    mint_coupling_ticket,
    reset_coupling_book,
    why_strip_coupling,
)


def test_idle_does_not_mint():
    assert mint_coupling_ticket(
        clock_ns=1, frame_seq=1, phrase="IDLE", coupling=0.0, hold_energy=0.0
    ) is None
    assert mint_coupling_ticket(
        clock_ns=1, frame_seq=1, phrase="HUDDLE", coupling=0.1, hold_energy=0.0
    ) is None


def test_sprint_mints_and_licenses_heat():
    reset_coupling_book()
    t = mint_coupling_ticket(
        clock_ns=time.monotonic_ns(),
        frame_seq=9,
        phrase="SPRINT",
        coupling=0.4,
        hold_energy=1.1,
        pll_lock=True,
        video_fresh=True,
    )
    assert t is not None
    assert t.phrase == "SPRINT"
    get_coupling_book().put(t)
    heat = "Controller heat on a live drive — eyes up."
    assert heat_speech(heat)
    assert license_heat_text(heat, ticket=t) == heat
    assert license_heat_text(heat, ticket=None) == ""
    assert "SPRINT" in why_strip_coupling(t)
    assert why_strip_coupling(None) == "couple: none"


def test_non_heat_passes_without_ticket():
    msg = "Red-zone energy spike — something's cooking."
    assert license_heat_text(msg, ticket=None) == msg


def test_latest_live_expires():
    reset_coupling_book()
    t = mint_coupling_ticket(
        clock_ns=time.monotonic_ns() - int(800 * 1e6),
        frame_seq=2,
        phrase="CUT",
        coupling=0.5,
        hold_energy=0.4,
        pll_lock=True,
        video_fresh=True,
    )
    get_coupling_book().put(t)
    assert get_coupling_book().latest_live() is None


def test_sprint_without_pll_does_not_mint():
    assert mint_coupling_ticket(
        clock_ns=1,
        frame_seq=1,
        phrase="SPRINT",
        coupling=0.4,
        hold_energy=1.0,
        pll_lock=False,
        video_fresh=True,
    ) is None
    assert mint_coupling_ticket(
        clock_ns=1,
        frame_seq=1,
        phrase="SPRINT",
        coupling=0.4,
        hold_energy=1.0,
        pll_lock=True,
        video_fresh=False,
    ) is None
