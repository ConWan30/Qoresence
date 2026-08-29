"""Phase 1: outbound chat is silent unless a ticket or score lock licenses it."""

from __future__ import annotations

from qoresence.agents.chat_license import outbound_chat_allowed


def test_fast_chat_silent_without_coupling_ticket():
    assert outbound_chat_allowed(path="fast", coupling_ticket=None) is False


def test_fast_chat_ok_with_coupling_ticket():
    assert outbound_chat_allowed(path="fast", coupling_ticket=object()) is True


def test_confirm_chat_silent_without_ticket_or_lock():
    assert (
        outbound_chat_allowed(
            path="confirm",
            confirm_ticket=None,
            score_vlm_locked=False,
        )
        is False
    )


def test_confirm_chat_ok_with_vlm_lock():
    assert (
        outbound_chat_allowed(
            path="confirm",
            confirm_ticket=None,
            score_vlm_locked=True,
        )
        is True
    )


def test_confirm_chat_ok_with_confirm_ticket():
    assert (
        outbound_chat_allowed(
            path="confirm",
            confirm_ticket=object(),
            score_vlm_locked=False,
        )
        is True
    )


def test_unknown_path_silent():
    assert outbound_chat_allowed(path="ambient", coupling_ticket=object()) is False


def test_fast_chat_ok_with_picture_hid_ticket():
    assert outbound_chat_allowed(path="fast", picture_ticket=object()) is True


def test_fast_chat_silent_without_coupling_or_picture():
    assert outbound_chat_allowed(path="fast") is False
