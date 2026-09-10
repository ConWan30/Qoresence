"""X Glass runtime — Timeline VOD draft/create + second-click post (default OFF).

Pattern B: no encoder/RTMP, no second VideoCapture, no Truth-plane.
OAuth tokens are never invented; missing creds → oauth_missing on post.
"""

from __future__ import annotations

import logging
import pathlib
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from qoresence.x.caption import build_caption

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"
CLIP_NAME_RE = re.compile(r"^hdmi_clip_[\w\-]+\.mp4$", re.I)

_glass: "XGlass | None" = None
_glass_lock = threading.Lock()


@dataclass
class XGlassConfig:
    """Opt-in X Glass publish lobe. All defaults OFF / fail-closed."""

    enabled: bool = False
    grant: bool = False
    token_file: str | None = ".secrets/x_glass.token"
    post_cooldown_s: float = 30.0
    clips_dir: str = "clips"


@dataclass
class Draft:
    clip_name: str
    clip_path: str
    media_url: str
    caption: str
    digit_silent: bool
    caption_mode: str
    gate: dict[str, Any] = field(default_factory=dict)
    created_mono: float = 0.0


class XGlass:
    """Default-OFF Timeline VOD actuator. create ≠ post."""

    def __init__(self, config: XGlassConfig | None = None) -> None:
        self.config = config or XGlassConfig()
        self._lock = threading.Lock()
        self._draft: Draft | None = None
        self._last_reason: str = "lobe_off" if not self.config.enabled else "idle"
        self._last_post_mono: float = 0.0
        self._creates = 0
        self._posts_ok = 0
        self._posts_hold = 0

    def health(self) -> dict[str, Any]:
        oauth = self._oauth_present()
        enabled = bool(self.config.enabled)
        grant = bool(self.config.grant)
        ready = bool(enabled and grant and oauth and self._draft is not None)
        with self._lock:
            draft = None
            if self._draft is not None:
                d = self._draft
                draft = {
                    "clip_name": d.clip_name,
                    "media_url": d.media_url,
                    "digit_silent": d.digit_silent,
                    "caption_mode": d.caption_mode,
                    "caption": d.caption,
                }
            reason = self._last_reason
        return {
            "enabled": enabled,
            "grant": grant,
            "ready": ready,
            "last_reason": reason,
            "oauth_present": oauth,
            "draft": draft,
            "creates": self._creates,
            "posts_ok": self._posts_ok,
            "posts_hold": self._posts_hold,
            "plane": PLANE,
            "token_file": self.config.token_file,
        }

    def snapshot_field(self) -> dict[str, Any]:
        h = self.health()
        return {
            "enabled": h["enabled"],
            "grant": h["grant"],
            "ready": h["ready"],
            "last_reason": h["last_reason"],
        }

    def resolve_mp4(
        self, clip_name: str | None = None, clip_path: str | None = None
    ) -> tuple[pathlib.Path | None, str]:
        root = pathlib.Path(self.config.clips_dir).resolve()
        name = ""
        if clip_name:
            name = pathlib.Path(str(clip_name)).name
        elif clip_path:
            p = pathlib.Path(str(clip_path))
            name = p.name
            try:
                resolved = p.resolve()
                resolved.relative_to(root)
                if resolved.is_file() and resolved.suffix.lower() == ".mp4":
                    if not (
                        CLIP_NAME_RE.match(resolved.name)
                        or re.fullmatch(r"[\w\-]+\.mp4", resolved.name, flags=re.I)
                    ):
                        return None, "invalid_clip"
                    return resolved, ""
            except (ValueError, OSError):
                name = p.name

        if not name:
            return None, "no_mp4"
        if not (
            CLIP_NAME_RE.match(name) or re.fullmatch(r"[\w\-]+\.mp4", name, flags=re.I)
        ):
            return None, "invalid_clip"
        path = (root / name).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return None, "invalid_clip"
        if not path.is_file() or path.suffix.lower() != ".mp4":
            return None, "no_mp4"
        return path, ""

    def _oauth_present(self) -> bool:
        tf = self.config.token_file
        if not tf:
            return False
        try:
            p = pathlib.Path(tf)
            return p.is_file() and p.stat().st_size > 0
        except OSError:
            return False

    def _situation(self) -> dict[str, Any]:
        try:
            from qoresence.deck.server import _state

            sit = getattr(_state, "situation", None)
            if isinstance(sit, dict):
                return dict(sit)
            snap = _state.snapshot() if _state is not None else {}
            if isinstance(snap, dict):
                out = dict(snap.get("situation") or {})
                for k in (
                    "confirm_ticket_id",
                    "score_vlm_locked",
                    "crop_hash",
                    "ticket_crop_hash",
                    "home_score",
                    "away_score",
                    "confirm_clock_ns",
                    "updated_ns",
                    "same_seq",
                    "title",
                    "board_locked",
                    "scoreboard_locked",
                    "confirm",
                    "video",
                    "last_confirm",
                ):
                    if k in snap and k not in out:
                        out[k] = snap[k]
                if "video" not in out and isinstance(snap.get("video"), dict):
                    out["video"] = snap["video"]
                return out
        except Exception:
            pass
        return {}

    def create(
        self,
        *,
        clip_name: str | None = None,
        clip_path: str | None = None,
        caption_mode: str = "auto",
        situation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.config.enabled:
            self._last_reason = "lobe_off"
            return {"ok": False, "error": "lobe_off", "x_glass": self.snapshot_field()}

        path, err = self.resolve_mp4(clip_name, clip_path)
        if path is None:
            self._last_reason = err or "no_mp4"
            return {"ok": False, "error": err or "no_mp4", "x_glass": self.snapshot_field()}

        sit = situation if isinstance(situation, dict) else self._situation()
        cap = build_caption(sit, caption_mode=caption_mode)
        draft = Draft(
            clip_name=path.name,
            clip_path=str(path),
            media_url=f"/media/clips/{path.name}",
            caption=cap["caption"],
            digit_silent=bool(cap["digit_silent"]),
            caption_mode=cap["caption_mode"],
            gate=cap.get("gate") or {},
            created_mono=time.monotonic(),
        )
        with self._lock:
            self._draft = draft
            self._creates += 1
            self._last_reason = "digit_silent" if draft.digit_silent else "draft_ready"

        return {
            "ok": True,
            "draft": {
                "clip_name": draft.clip_name,
                "clip_path": draft.clip_path,
                "media_url": draft.media_url,
                "caption": draft.caption,
                "digit_silent": draft.digit_silent,
                "caption_mode": draft.caption_mode,
                "gate_void_reason": (draft.gate or {}).get("void_reason"),
            },
            "x_glass": self.snapshot_field(),
            "posted": False,
        }

    def post(
        self,
        *,
        clip_name: str | None = None,
        clip_path: str | None = None,
        caption_mode: str | None = None,
        situation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Second explicit click. Never auto-posts. Never invents OAuth.

        caption_mode=auto + any missing ConfirmTicket / score_vlm_locked /
        ticket-fresh → refuse digit_silent (Qorex kill-path).
        caption_mode=silent → blank digits, continue to oauth/grant checks.
        """
        if not self.config.enabled:
            self._posts_hold += 1
            self._last_reason = "lobe_off"
            return {"ok": False, "error": "lobe_off", "x_glass": self.snapshot_field()}

        if not self.config.grant:
            self._posts_hold += 1
            self._last_reason = "no_grant"
            return {"ok": False, "error": "no_grant", "x_glass": self.snapshot_field()}

        with self._lock:
            draft = self._draft

        if draft is None:
            self._posts_hold += 1
            self._last_reason = "create_required"
            return {
                "ok": False,
                "error": "create_required",
                "x_glass": self.snapshot_field(),
            }

        if clip_name or clip_path:
            path, err = self.resolve_mp4(clip_name, clip_path)
            if path is None:
                self._posts_hold += 1
                self._last_reason = err or "no_mp4"
                return {"ok": False, "error": err or "no_mp4", "x_glass": self.snapshot_field()}
            if path.name != draft.clip_name:
                self._posts_hold += 1
                self._last_reason = "create_required"
                return {
                    "ok": False,
                    "error": "create_required",
                    "detail": "clip_mismatch_rebuild_draft",
                    "x_glass": self.snapshot_field(),
                }

        if not pathlib.Path(draft.clip_path).is_file():
            self._posts_hold += 1
            self._last_reason = "no_mp4"
            return {"ok": False, "error": "no_mp4", "x_glass": self.snapshot_field()}

        mode = str(caption_mode or draft.caption_mode or "auto").strip().lower()
        if mode not in ("auto", "silent"):
            mode = "auto"
        sit = situation if isinstance(situation, dict) else self._situation()
        cap = build_caption(sit, caption_mode=mode)
        digit_silent = bool(cap["digit_silent"])

        # Qorex kill-path: auto mode refuses when ANY digit gate leg is missing.
        # board_locked alone never licenses (handled inside build_caption).
        if mode == "auto" and digit_silent:
            self._posts_hold += 1
            self._last_reason = "digit_silent"
            return {
                "ok": False,
                "error": "digit_silent",
                "caption": cap["caption"],
                "gate_void_reason": (cap.get("gate") or {}).get("void_reason"),
                "x_glass": self.snapshot_field(),
            }

        now = time.monotonic()
        cool = float(self.config.post_cooldown_s or 0)
        if self._last_post_mono and cool > 0 and (now - self._last_post_mono) < cool:
            self._posts_hold += 1
            self._last_reason = "rate_limited"
            return {
                "ok": False,
                "error": "rate_limited",
                "retry_after_s": round(cool - (now - self._last_post_mono), 1),
                "x_glass": self.snapshot_field(),
            }

        # Publisher stub: never invent tokens. File presence still yields
        # oauth_missing until a real X media+tweet helper ships.
        self._posts_hold += 1
        self._last_reason = "oauth_missing"
        return {
            "ok": False,
            "error": "oauth_missing",
            "digit_silent": digit_silent,
            "caption": cap["caption"],
            "detail": "publisher_stub",
            "oauth_present": self._oauth_present(),
            "draft": {
                "clip_name": draft.clip_name,
                "media_url": draft.media_url,
            },
            "x_glass": self.snapshot_field(),
            "hint": (
                "Operator: enable --x-glass, set QORESENCE_X_GLASS_GRANT=1, "
                "place OAuth at token_file (never commit). create then post."
            ),
        }


def get_x_glass() -> XGlass:
    global _glass
    with _glass_lock:
        if _glass is None:
            _glass = XGlass(XGlassConfig())
        return _glass


def set_x_glass(glass: XGlass | None) -> None:
    global _glass
    with _glass_lock:
        _glass = glass


def x_glass_health() -> dict[str, Any]:
    return get_x_glass().health()
