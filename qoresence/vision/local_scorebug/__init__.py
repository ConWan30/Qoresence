"""Keyless local scorebug reader (phase 1: Madden NFL 27 standard strip).

Reads score digits, game clock and quarter straight off the HDMI frame with
glyph templates (numpy + OpenCV only, no cloud key, no model download). It
answers only when every glyph clears an absolute confidence floor AND a
margin over the runner-up, and only after several consecutive sampled frames
agree. Anything else (unknown skin, a digit it has not learned, banners,
animations, red final-seconds clock) stays blank.

Seam: ``FootballScoreboardExtractor.extract`` asks ``get_local_scorebug()``
for a sure board and offers it to the unchanged mint path with
``source="local_scorebug"``. See README.md in this folder.
"""

from qoresence.vision.local_scorebug.agreement import AgreementConfig, AgreementWindow
from qoresence.vision.local_scorebug.reader import FrameRead, ScorebugReader, TemplatePack
from qoresence.vision.local_scorebug.service import (
    LOCAL_SOURCE,
    LocalScorebugService,
    choose_board,
    cloud_scorebug_active,
    get_local_scorebug,
    local_scorebug_enabled,
    local_scorebug_flag,
    reset_local_scorebug,
)

__all__ = [
    "LOCAL_SOURCE",
    "AgreementConfig",
    "AgreementWindow",
    "FrameRead",
    "LocalScorebugService",
    "ScorebugReader",
    "TemplatePack",
    "choose_board",
    "cloud_scorebug_active",
    "get_local_scorebug",
    "local_scorebug_enabled",
    "local_scorebug_flag",
    "reset_local_scorebug",
]
