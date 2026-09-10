"""X Glass — default-OFF Timeline VOD / receipt lobe (observation plane).

Never opens DirectShow. Never pushes RTMP. Never invents digits or tokens.
Publish is a second explicit click after create. DualSense stays on the PS5.
"""

from __future__ import annotations

from qoresence.x.glass import (
    XGlass,
    XGlassConfig,
    get_x_glass,
    set_x_glass,
    x_glass_health,
)

__all__ = [
    "XGlass",
    "XGlassConfig",
    "get_x_glass",
    "set_x_glass",
    "x_glass_health",
]
