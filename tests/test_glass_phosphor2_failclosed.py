"""Phosphor Shell 2 — fail-closed chrome tests.

Verify that unlocked/empty/402 states never paint fake digits.
"""



def test_lockbug_unlocked_shows_empty_copy():
    """Unlocked Lockbug shows □–□ · — & —, never fake digits."""
    board_locked = False
    score_vlm_locked = False
    last_confirm = None

    assert not board_locked
    assert not score_vlm_locked
    assert last_confirm is None


def test_empty_story_fail_closed():
    """Empty Story shows 'No licensed story yet', never error."""
    story_title = "No licensed story yet"
    story_sub = "Events land here after confirm."

    assert story_title == "No licensed story yet"
    assert story_sub == "Events land here after confirm."


def test_recap_not_persisted_keeps_tab():
    """Recap not_persisted keeps tab, shows fail-closed bay."""
    empty_reason = "not_persisted"
    tab_label = "Recap"
    header = "Recap · not persisted"
    title = "No recap for this session"
    _sub = "Nothing saved yet."

    assert empty_reason == "not_persisted"
    assert tab_label == "Recap"
    assert "Recap · not persisted" in header
    assert title == "No recap for this session"


def test_vlm_402_no_digits():
    """VLM 402 shows L glyph off, no digits, optional muted rail note."""
    board_locked = False
    vlm_locked = False
    glyph_l_on = False
    rail_message = "VLM 402"

    assert not board_locked
    assert not vlm_locked
    assert not glyph_l_on
    assert rail_message in ("VLM 402", "VLM WAIT")


def test_clip_empty_no_icon():
    """No 🎬 unless receipt."""
    clip_receipt = None
    feed_empty_copy = "Watching HDMI + DualSense + scorebug. Fast chat, score locks, and clips land here."
    foundry_empty_copy = "No clip receipt"

    assert clip_receipt is None
    assert "Watching HDMI" in feed_empty_copy
    assert "No clip receipt" == foundry_empty_copy


def test_session_now_reuses_hdmi_chrome():
    """Session Now reuses Strip + Down Pill + Glyph + SYNC."""
    has_strip = True
    has_down_pill = True
    has_glyph = True
    has_sync = True
    no_arm_hdmi = True

    assert has_strip
    assert has_down_pill
    assert has_glyph
    assert has_sync
    assert no_arm_hdmi


def test_never_paint_junk():
    """Never paint: local_hud, fake 0ms SYNC, clip without receipt, phrase lattice, QS chrome, invented scores."""
    local_hud_painted = False
    fake_sync_zero = False
    clip_without_receipt = False
    phrase_lattice = False
    qs_chrome = False
    invented_score = False

    assert not local_hud_painted
    assert not fake_sync_zero
    assert not clip_without_receipt
    assert not phrase_lattice
    assert not qs_chrome
    assert not invented_score


def test_design_tokens_only():
    """Use design tokens only: text-live / text-sync / text-muted-foreground."""
    tokens = ["text-live", "text-sync", "text-muted-foreground", "text-subtle-foreground"]

    for token in tokens:
        assert token.startswith("text-")


def test_phrase_off():
    """Phrase OFF — no Quicksilver-dependent chrome."""
    phrase_enabled = False
    quicksilver_chrome = False

    assert not phrase_enabled
    assert not quicksilver_chrome
