"""Match-observer agent — DeepSeek v4 via Quicksilver, same path as ClutchBot.

Observation plane only. Default OFF. DualSense stays on the PS5.
Sees confirm-locked board + picture-HID labels + CIVIF clock.
Never invents scores. Never writes picture presses into InputRing.
Never treats OBSERVE Edge USB as play-pad HID.

LLM calls run on a poll thread, not the IVC / bus emit path.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from qoresence.agents.chat_license import license_gate
from qoresence.agents.llm_client import LLMConfig, QuicksilverLLMClient
from qoresence.vision.confirm_ticket import license_score_text

log = logging.getLogger(__name__)

_POLL_S = 1.0
_MAX_NOTE = 280


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def build_match_evidence(
    *,
    civif: dict[str, Any] | None = None,
    confirm: Any | None = None,
    picture: Any | None = None,
) -> dict[str, Any]:
    """Fail-closed bag for the LLM. Digits only with a confirm ticket."""
    rec = dict(civif or {})
    bodied = bool(rec.get("controller_bodied"))
    inp = rec.get("input") if isinstance(rec.get("input"), dict) else {}
    confirm_id = str(getattr(confirm, "ticket_id", "") or "")
    home = away = None
    if confirm is not None:
        home = getattr(confirm, "home_score", None)
        away = getattr(confirm, "away_score", None)
    pic = None
    if picture is not None:
        pic = {
            "ticket_id": str(getattr(picture, "ticket_id", "") or ""),
            "hid_button": str(getattr(picture, "hid_button", "") or ""),
            "prompt_text": getattr(picture, "prompt_text", None),
            "verb": getattr(picture, "verb", None),
            "frame_seq": int(getattr(picture, "frame_seq", 0) or 0),
            "hid_domain": "picture",
        }
        if not pic["ticket_id"] or not pic["hid_button"]:
            pic = None
    ticks = rec.get("input_ticks") if bodied else []
    if not isinstance(ticks, list):
        ticks = []
    return {
        "session_id": str(rec.get("session_id") or ""),
        "clock_ns": int(rec.get("clock_ns") or 0),
        "frame_seq": int(rec.get("frame_seq") or 0),
        "board_locked": bool(confirm_id),
        "home_score": home if confirm_id else None,
        "away_score": away if confirm_id else None,
        "confirm_ticket_id": confirm_id,
        "picture_hid": pic,
        "controller_bodied": bodied,
        "input_ticks": ticks if bodied else [],
        "body_reason": str(inp.get("reason") or rec.get("body_reason") or "")
        or ("pad_not_on_this_host" if not bodied else "input_ring"),
    }


def evidence_ticket_id(evidence: dict[str, Any]) -> str:
    tid = str(evidence.get("confirm_ticket_id") or "")
    if tid:
        return tid
    pic = evidence.get("picture_hid")
    if isinstance(pic, dict):
        return str(pic.get("ticket_id") or "")
    return ""


def _system_prompt() -> str:
    return (
        "You are a Qoresence match observer. Observation plane only. "
        "DualSense stays on the PS5. Picture HID labels are HDMI callouts, not pad presses. "
        "Cite ONLY the evidence JSON. Never invent scores, downs, or button names. "
        "If board_locked is false, do not speak digits. If picture_hid is null, say unlabeled. "
        "If controller_bodied is false, do not claim a press. One sentence, under 200 chars. "
        "Never claim to be human."
    )


class MatchAgent:
    """Polls CIVIF + ticket books at ~1 Hz. Quicksilver DeepSeek v4 like ClutchBot."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        llm_config: LLMConfig | None = None,
        poll_s: float = _POLL_S,
    ) -> None:
        env_on = _env_on("QORESENCE_MATCH_AGENT")
        self.enabled = env_on if enabled is None else bool(enabled)
        cfg = llm_config or LLMConfig.from_quicksilver_env(enabled=self.enabled)
        if self.enabled:
            cfg = LLMConfig(
                enabled=True,
                provider=cfg.provider,
                model=cfg.model,
                base_url=cfg.base_url,
                api_key=cfg.api_key,
                api_key_file=cfg.api_key_file,
                fallback_model=cfg.fallback_model,
                timeout_s=cfg.timeout_s,
                max_tokens=cfg.max_tokens,
            )
        self._llm = QuicksilverLLMClient(cfg)
        self.live = bool(self.enabled and self._llm.is_available())
        self.poll_s = max(0.5, float(poll_s or _POLL_S))
        self._running = False
        self._thread: threading.Thread | None = None
        self._last: dict[str, Any] | None = None
        self._lock = threading.Lock()

    def last_note(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._last) if self._last else None

    def collect_evidence(self) -> dict[str, Any]:
        civif: dict[str, Any] = {}
        try:
            from qoresence.foundry.cer_log import live_record

            raw = live_record()
            if isinstance(raw, dict):
                civif = raw
        except Exception:
            civif = {}
        confirm = None
        try:
            from qoresence.vision.confirm_ticket import get_ticket_book

            confirm = get_ticket_book().latest()
        except Exception:
            confirm = None
        picture = None
        try:
            from qoresence.sync.picture_hid_book import get_picture_hid_book

            seq = civif.get("frame_seq")
            picture = get_picture_hid_book().latest_nearby(seq)
        except Exception:
            picture = None
        return build_match_evidence(civif=civif, confirm=confirm, picture=picture)

    def propose(self, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        bag = evidence if isinstance(evidence, dict) else self.collect_evidence()
        tid = evidence_ticket_id(bag)
        confirm = None
        if bag.get("confirm_ticket_id"):
            confirm = type("T", (), {"ticket_id": bag["confirm_ticket_id"]})()
        path = "confirm" if bag.get("confirm_ticket_id") else "fast"
        pic = bag.get("picture_hid") if isinstance(bag.get("picture_hid"), dict) else None
        allowed = bool(tid) and license_gate(
            path=path,
            ticket_id=tid,
            confirm_ticket=confirm,
            score_vlm_locked=bool(bag.get("board_locked")),
            picture_ticket=pic,
        )
        stub = self._stub(bag)
        if not allowed or not self.live:
            return stub
        try:
            text = self._llm.enhance_message(
                situation=bag,
                event_type="match_observe",
                event_payload={"evidence": bag},
                persona="observer",
                base_message="One observation sentence from the evidence JSON.",
                system_prompt=_system_prompt(),
            )
        except Exception as e:
            log.warning("MatchAgent Quicksilver failed, stub: %s", e)
            return stub
        if not text:
            return stub
        if bag.get("confirm_ticket_id"):
            text = license_score_text(
                text,
                ticket=type(
                    "C",
                    (),
                    {
                        "home_score": bag.get("home_score"),
                        "away_score": bag.get("away_score"),
                    },
                )(),
                home_score=bag.get("home_score"),
                away_score=bag.get("away_score"),
            )
        else:
            text = license_score_text(text, ticket=None)
        return {
            "ok": True,
            "live": True,
            "text": str(text)[:_MAX_NOTE],
            "ticket_id": tid,
            "path": path,
            "evidence": bag,
            "model": self._llm.config.model,
        }

    def _stub(self, bag: dict[str, Any]) -> dict[str, Any]:
        pic = bag.get("picture_hid") if isinstance(bag.get("picture_hid"), dict) else None
        if bag.get("confirm_ticket_id") and bag.get("home_score") is not None:
            text = "Board licensed on this seq."
        elif pic:
            text = f"Picture HUD labeled {pic.get('hid_button')} — not a pad press."
        else:
            text = "Unlabeled. Pad not on this host."
        return {
            "ok": True,
            "live": False,
            "text": text[:_MAX_NOTE],
            "ticket_id": evidence_ticket_id(bag),
            "path": "hold" if not evidence_ticket_id(bag) else "fast",
            "evidence": bag,
            "model": "stub-match-agent",
        }

    def start(self) -> bool:
        if not self.enabled:
            log.debug("MatchAgent off (pass --match-agent or QORESENCE_MATCH_AGENT=1)")
            return False
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._run, name="match-agent", daemon=True)
        self._thread.start()
        log.info(
            "MatchAgent started live=%s model=%s (Quicksilver DeepSeek v4, ClutchBot key)",
            self.live,
            self._llm.config.model,
        )
        return True

    def stop(self) -> None:
        self._running = False

    def _run(self) -> None:
        while self._running:
            try:
                note = self.propose()
                with self._lock:
                    self._last = note
            except Exception as e:
                log.debug("MatchAgent poll: %s", e)
            time.sleep(self.poll_s)


_agent: MatchAgent | None = None


def get_match_agent() -> MatchAgent | None:
    return _agent


def start_match_agent(*, enabled: bool = False, poll_s: float = _POLL_S) -> MatchAgent | None:
    global _agent
    agent = MatchAgent(enabled=enabled, poll_s=poll_s)
    _agent = agent
    if enabled:
        agent.start()
    return agent


def stop_match_agent() -> None:
    global _agent
    if _agent is not None:
        _agent.stop()
        _agent = None


def surface_last_note() -> dict[str, Any]:
    """Fail-closed Deck poll surface for last_note().

    Empty when OFF (agent is None or enabled=False), quiet (last_note is None),
    or unlicensed (missing ticket_id OR path == "hold" OR empty text).

    Licensed note (ticket_id present AND path in {fast, confirm} AND non-empty text)
    returns ok=True with text, live, ticket_id, path, model.

    Does NOT include the evidence bag. DualSense/PS5: observation only; never
    claim a pad press; picture_hid tickets are labels not InputRing.
    """
    empty = {
        "ok": False,
        "text": "",
        "live": False,
        "ticket_id": "",
        "path": "hold",
        "model": "",
    }
    try:
        agent = get_match_agent()
        if agent is None or not agent.enabled:
            return empty
        note = agent.last_note()
        if note is None:
            return empty
        live = bool(note.get("live"))
        if not live:
            return empty
        tid = str(note.get("ticket_id") or "")
        path = str(note.get("path") or "hold")
        text = str(note.get("text") or "")
        if not tid or path == "hold" or not text:
            return empty
        if path not in {"fast", "confirm"}:
            return empty
        return {
            "ok": True,
            "text": text[:280],
            "live": live,
            "ticket_id": tid,
            "path": path,
            "model": str(note.get("model") or ""),
        }
    except Exception:
        return empty
