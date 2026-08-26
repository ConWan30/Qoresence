"""CFB_27 first-class profile contract tests.

This test suite enforces Contract (2): game_profile enum first-class cfb_27.
- Title lock "College Football 27" → game_profile=cfb_27, NOT madden_27
- Keep ncaa_football_27 enum but college/ncaa/cfb title aliases → CFB_27
"""

from __future__ import annotations

from qoresence.core import (
    CFB_27_PROFILE,
    GameProfileId,
    profile_from_title,
)
from qoresence.vision.vision_stack import VisionStack
from qoresence.vision.visual_context import GameCategory, GameState, VisualContext


def test_cfb_27_enum_value():
    """GameProfileId.CFB_27.value == "cfb_27"."""
    assert GameProfileId.CFB_27.value == "cfb_27"


def test_cfb_27_profile_display_name():
    """CFB_27_PROFILE.display_name == "College Football 27"."""
    assert CFB_27_PROFILE.display_name == "College Football 27"


def test_profile_from_title_college_football_27():
    """profile_from_title("College Football 27") == GameProfileId.CFB_27."""
    assert profile_from_title("College Football 27") == GameProfileId.CFB_27


def test_profile_from_title_ncaa():
    """profile_from_title("NCAA Football") == GameProfileId.CFB_27."""
    assert profile_from_title("NCAA Football") == GameProfileId.CFB_27


def test_profile_from_title_cfb():
    """profile_from_title("CFB 27") == GameProfileId.CFB_27."""
    assert profile_from_title("CFB 27") == GameProfileId.CFB_27


def test_profile_from_title_madden():
    """profile_from_title("Madden NFL 27") == GameProfileId.MADDEN_27."""
    assert profile_from_title("Madden NFL 27") == GameProfileId.MADDEN_27


def test_vision_stack_title_college_football_27():
    """VisionStack._visual_context_to_game_profile with game_title="College Football 27" → CFB_27."""
    ctx = VisualContext(
        game_title="College Football 27",
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        confidence=0.9,
    )
    profile, conf = VisionStack._visual_context_to_game_profile(ctx, None)
    assert profile == GameProfileId.CFB_27
    assert conf == 0.9


def test_vision_stack_title_ncaa():
    """VisionStack with game_title="NCAA Football" → CFB_27."""
    ctx = VisualContext(
        game_title="NCAA Football",
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        confidence=0.85,
    )
    profile, conf = VisionStack._visual_context_to_game_profile(ctx, None)
    assert profile == GameProfileId.CFB_27


def test_vision_stack_title_cfb():
    """VisionStack with game_title="CFB 27" → CFB_27."""
    ctx = VisualContext(
        game_title="CFB 27",
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        confidence=0.92,
    )
    profile, conf = VisionStack._visual_context_to_game_profile(ctx, None)
    assert profile == GameProfileId.CFB_27


def test_vision_stack_title_madden():
    """VisionStack with game_title="Madden NFL 27" → MADDEN_27, not CFB_27."""
    ctx = VisualContext(
        game_title="Madden NFL 27",
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        confidence=0.88,
    )
    profile, conf = VisionStack._visual_context_to_game_profile(ctx, None)
    assert profile == GameProfileId.MADDEN_27
    assert profile != GameProfileId.CFB_27


def test_vision_stack_fallback_category_football():
    """VisionStack fallback with category=football → CFB_27."""
    ctx = VisualContext(
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        confidence=0.7,
    )
    profile, conf = VisionStack._visual_context_to_game_profile(ctx, None)
    assert profile == GameProfileId.CFB_27


def test_visual_runtime_merge_scoreboard_cfb_title(monkeypatch):
    """VisualRuntime._merge_scoreboard with VisualConfig defaulting to madden_27 
    BUT context.game_title="College Football 27" → out.game_profile == "cfb_27".
    """
    monkeypatch.setenv("QORESENCE_EASY_OCR", "0")
    
    from qoresence.core import RetinaEventBus, VisualConfig
    from qoresence.lobes.visual import VisualRuntime
    
    # Config defaults to madden but title is CFB
    config = VisualConfig(
        enabled=True,
        game_profile="madden_27",
        game_category="football",
    )
    
    bus = RetinaEventBus()
    runtime = VisualRuntime(config, bus, session_head_ns=0)
    
    import numpy as np
    
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    ctx = VisualContext(
        game_title="College Football 27",
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        confidence=0.9,
    )
    
    result = runtime._merge_scoreboard(frame, ctx)
    
    assert result is not None
    assert result.game_profile == "cfb_27"


def test_visual_runtime_merge_scoreboard_madden_title(monkeypatch):
    """VisualRuntime._merge_scoreboard with game_title="Madden NFL 27" → madden_27."""
    monkeypatch.setenv("QORESENCE_EASY_OCR", "0")
    
    from qoresence.core import RetinaEventBus, VisualConfig
    from qoresence.lobes.visual import VisualRuntime
    
    config = VisualConfig(
        enabled=True,
        game_profile="football",
        game_category="football",
    )
    
    bus = RetinaEventBus()
    runtime = VisualRuntime(config, bus, session_head_ns=0)
    
    import numpy as np
    
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    ctx = VisualContext(
        game_title="Madden NFL 27",
        game_category=GameCategory.FOOTBALL,
        game_state=GameState.GAMEPLAY,
        confidence=0.88,
    )
    
    result = runtime._merge_scoreboard(frame, ctx)
    
    assert result is not None
    assert result.game_profile == "madden_27"
