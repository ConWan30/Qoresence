"""Community game-profile SDK.

Allows users to define custom game profiles via YAML files without
touching core code. Profiles are loaded from a ``profiles/`` directory
at the project root (or a custom path) and merged into the
``GAME_PROFILE_REGISTRY`` at startup.

YAML schema
-----------
.. code-block:: yaml

    # profiles/my_game.yaml
    profile_id: my_game
    display_name: My Game
    category: shooter  # "football" | "shooter" | "other"
    event_types:
      - kill
      - death
      - match_start
      - match_end
    outcome_fields:
      - kills
      - deaths
      - score
    aliases:
      - mg
      - my_game_2027

Python API
----------
.. code-block:: python

    from qoresence.profiles.sdk import load_community_profiles
    load_community_profiles()  # scans profiles/ and registers all
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qoresence.core.unified_config import (
    GAME_PROFILE_ALIASES,
    GAME_PROFILE_REGISTRY,
    GameProfile,
    GameProfileId,
)

log = logging.getLogger(__name__)

# Default directory for community YAML profiles
DEFAULT_PROFILES_DIR = Path("profiles")


@dataclass(frozen=True)
class CommunityGameProfile(GameProfile):
    """A game profile loaded from a YAML file.

    Extends GameProfile with optional aliases and a source_path for
    debugging. The profile_id is a plain string (not a GameProfileId
    enum member) since community profiles aren't in the enum.
    """


def _parse_yaml_profile(path: Path) -> tuple[GameProfile, list[str]] | None:
    """Parse a single YAML profile file.

    Returns (GameProfile, aliases) or None on failure.
    """
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("community profile: failed to parse %s: %s", path, e)
        return None

    if not isinstance(data, dict):
        log.warning("community profile: %s is not a mapping", path)
        return None

    profile_id = str(data.get("profile_id") or "").strip()
    if not profile_id:
        log.warning("community profile: %s missing profile_id", path)
        return None

    display_name = str(data.get("display_name") or profile_id)
    category = str(data.get("category") or "other").strip()
    event_types = tuple(str(e) for e in (data.get("event_types") or []))
    outcome_fields = tuple(str(f) for f in (data.get("outcome_fields") or []))
    aliases = [str(a) for a in (data.get("aliases") or [])]

    if not event_types:
        log.warning("community profile: %s has no event_types", path)
        return None

    # Create a synthetic GameProfileId for the community profile
    # We use a plain string since GameProfileId is a StrEnum
    pid = (
        GameProfileId(profile_id)
        if profile_id in GameProfileId.__members__.values()
        else _CommunityProfileId(profile_id)
    )

    profile = GameProfile(
        profile_id=pid,  # type: ignore[arg-type]
        display_name=display_name,
        event_types=event_types,
        outcome_fields=outcome_fields,
        category=category,
    )
    return profile, aliases


class _CommunityProfileId(str):
    """A string that acts as a GameProfileId for community profiles.

    StrEnum members are also str instances, so this is compatible with
    the GameProfile.profile_id type annotation.
    """

    def __str__(self) -> str:
        return str.__str__(self)

    @property
    def value(self) -> str:
        return str.__str__(self)


def load_community_profiles(profiles_dir: Path | str | None = None) -> int:
    """Load all community YAML profiles from a directory.

    Scans ``profiles_dir`` (default: ``profiles/`` at cwd) for ``*.yaml``
    or ``*.yml`` files, parses each, and registers them in
    ``GAME_PROFILE_REGISTRY`` and ``GAME_PROFILE_ALIASES``.

    Returns the number of profiles loaded.
    """
    pdir = Path(profiles_dir) if profiles_dir else DEFAULT_PROFILES_DIR
    if not pdir.is_dir():
        log.debug("community profiles: %s does not exist, skipping", pdir)
        return 0

    count = 0
    for yml in sorted(pdir.glob("*.y*ml")):
        result = _parse_yaml_profile(yml)
        if result is None:
            continue
        profile, aliases = result
        # Register profile (skip if already a built-in)
        pid = profile.profile_id
        if pid in GAME_PROFILE_REGISTRY and not isinstance(pid, _CommunityProfileId):
            log.debug("community profile: %s already a built-in, skipping", pid)
            continue
        GAME_PROFILE_REGISTRY[pid] = profile
        # Register aliases
        for alias in aliases:
            GAME_PROFILE_ALIASES[alias] = pid
        log.info(
            "community profile loaded: %s (%s) from %s — %d events, %d fields, %d aliases",
            profile.profile_id,
            profile.display_name,
            yml.name,
            len(profile.event_types),
            len(profile.outcome_fields),
            len(aliases),
        )
        count += 1

    return count


def list_profiles() -> list[dict[str, Any]]:
    """List all registered profiles (built-in + community).

    Returns a list of dicts with profile_id, display_name, category,
    event count, and whether it's a community profile.
    """
    result = []
    for pid, p in GAME_PROFILE_REGISTRY.items():
        result.append(
            {
                "profile_id": str(pid),
                "display_name": p.display_name,
                "category": p.category,
                "event_count": len(p.event_types),
                "field_count": len(p.outcome_fields),
                "community": isinstance(pid, _CommunityProfileId),
            }
        )
    return result
