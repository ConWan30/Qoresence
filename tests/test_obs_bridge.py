"""OBS bridge spike — fake OBS client, no network."""

from __future__ import annotations

import json
import logging
import sys
import types

import pytest

from qoresence.obs import bridge as ob
from qoresence.obs.bridge import (
    ObsBridge,
    ObsBridgeConfig,
    ObsRequestError,
    observation_from_payload,
)

SECRET = "hunter2-super-secret"


class FakeObs:
    def __init__(self, scene: str = "Gameplay") -> None:
        self.calls: list[tuple] = []
        self.scene = scene
        self.chapter_supported = True
        self.closed = False

    def save_replay_buffer(self) -> None:
        self.calls.append(("replay",))

    def current_scene(self) -> str:
        return self.scene

    def set_scene(self, name: str) -> None:
        self.calls.append(("scene", name))
        self.scene = name

    def set_text(self, source: str, text: str) -> None:
        self.calls.append(("text", source, text))

    def create_chapter(self, name: str) -> None:
        if not self.chapter_supported:
            raise ObsRequestError("code=204")
        self.calls.append(("chapter", name))

    def close(self) -> None:
        self.closed = True

    def kinds(self) -> list[str]:
        return [c[0] for c in self.calls]


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class Ev:
    def __init__(self, payload: dict, type_: str = "visual_context") -> None:
        self.type = types.SimpleNamespace(value=type_)
        self.payload = payload


def locked(home: int, away: int, **fb) -> Ev:
    f = {"home_score": home, "away_score": away, "home_team": "KC", "away_team": "BUF"}
    f.update(fb)
    return Ev({"score_vlm_locked": True, "football": f})


def unlocked(home: int | None = 7, away: int | None = 3) -> Ev:
    return Ev({"score_vlm_locked": False, "football": {"home_score": home, "away_score": away}})


LIVE = {"has_frame": True, "age_s": 0.05, "seq": 10}


def make(cfg: ObsBridgeConfig | None = None, fake: FakeObs | None = None, stamp=None):
    fake = fake or FakeObs()
    clock = Clock()
    stamp_box = {"v": dict(LIVE) if stamp is None else stamp}
    b = ObsBridge(
        cfg or ObsBridgeConfig(enabled=True, scene="Qoresence Score", password=SECRET),
        client_factory=lambda _c: fake,
        frame_stamp=lambda: stamp_box["v"],
        clock=clock,
    )
    return b, fake, clock, stamp_box


def feed(b: ObsBridge, ev: Ev) -> None:
    b.on_event(ev)
    b.step()


def test_parse_fail_closed():
    assert observation_from_payload(None).pair is None
    assert observation_from_payload({"score_vlm_locked": True}).pair is None
    assert observation_from_payload(unlocked().payload).pair is None
    assert (
        observation_from_payload(
            {"score_vlm_locked": True, "football": {"home_score": None, "away_score": 3}}
        ).pair
        is None
    )
    o = observation_from_payload(locked(14, 7).payload)
    assert o.pair == (14, 7) and o.text == "KC 14 - 7 BUF"
    o = observation_from_payload(locked(14, 7, home_left=False).payload)
    assert o.text == "BUF 7 - 14 KC"


def test_first_lock_is_baseline_text_only():
    b, fake, _, _ = make()
    feed(b, locked(0, 0))
    assert fake.calls == [("text", "Qoresence Score", "KC 0 - 0 BUF")]


def test_change_triggers_replay_text_and_scene_then_restores():
    b, fake, clock, _ = make()
    feed(b, locked(0, 0))
    fake.calls.clear()
    feed(b, locked(7, 0))
    assert ("replay",) in fake.calls
    assert ("scene", "Qoresence Score") in fake.calls
    assert ("text", "Qoresence Score", "KC 7 - 0 BUF") in fake.calls
    st = b.stats()
    assert st["connected"] and st["actions"] >= 4 and st["actions_by_kind"]["replay"] == 1
    # hold not elapsed → no restore
    clock.t += 1.0
    b.step()
    assert fake.scene == "Qoresence Score"
    clock.t += 5.0
    b.step()
    assert fake.calls[-1] == ("scene", "Gameplay")


def test_restore_respects_manual_scene_switch():
    b, fake, clock, _ = make()
    feed(b, locked(0, 0))
    feed(b, locked(3, 0))
    fake.scene = "Operator Picked"
    clock.t += 10
    b.step()
    assert fake.scene == "Operator Picked"


def test_same_score_is_noop():
    b, fake, _, _ = make()
    feed(b, locked(0, 0))
    feed(b, locked(7, 0))
    n = len(fake.calls)
    for _ in range(5):
        feed(b, locked(7, 0))
    assert len(fake.calls) == n


def test_unlock_blanks_text_and_relock_same_score_no_replay():
    b, fake, _, _ = make()
    feed(b, locked(0, 0))
    feed(b, locked(7, 0))
    fake.calls.clear()
    feed(b, unlocked())
    assert fake.calls == [("text", "Qoresence Score", "")]
    fake.calls.clear()
    feed(b, locked(7, 0))
    assert fake.calls == [("text", "Qoresence Score", "KC 7 - 0 BUF")]


def test_blank_read_never_triggers_actions():
    b, fake, _, _ = make()
    feed(b, locked(7, 0))
    fake.calls.clear()
    feed(b, Ev({"score_vlm_locked": True, "football": {}}))
    feed(b, Ev({"game_state": "menu"}))
    assert "replay" not in fake.kinds() and "scene" not in fake.kinds()
    assert fake.calls == [("text", "Qoresence Score", "")]


def test_no_capture_blanks_text_and_ignores_lock():
    b, fake, _, stamp = make()
    feed(b, locked(0, 0))
    feed(b, locked(7, 0))
    fake.calls.clear()
    stamp["v"] = {"has_frame": False}
    feed(b, locked(14, 0))
    assert fake.calls == [("text", "Qoresence Score", "")]
    stamp["v"] = {"has_frame": True, "age_s": 30.0}  # stale frame
    feed(b, locked(14, 0))
    assert fake.calls == [("text", "Qoresence Score", "")]


def test_score_decrease_updates_text_without_replay():
    b, fake, _, _ = make()
    feed(b, locked(21, 14))
    feed(b, locked(0, 0))  # new game / correction
    assert "replay" not in fake.kinds()
    assert fake.calls[-1] == ("text", "Qoresence Score", "KC 0 - 0 BUF")


def test_replay_rate_limited():
    b, fake, clock, _ = make()
    feed(b, locked(0, 0))
    feed(b, locked(7, 0))
    clock.t += 2
    feed(b, locked(14, 0))
    assert fake.kinds().count("replay") == 1
    clock.t += 30
    feed(b, locked(21, 0))
    assert fake.kinds().count("replay") == 2


def test_chapter_optional_and_unsupported_tolerated():
    cfg = ObsBridgeConfig(enabled=True, chapters=True)
    b, fake, _, _ = make(cfg)
    feed(b, locked(0, 0))
    feed(b, locked(3, 0))
    assert ("chapter", "Score 0-0 -> 3-0") in fake.calls
    fake.chapter_supported = False
    feed(b, locked(10, 0))  # refused chapter must not drop the connection
    assert b.connected and "refused" in b.stats()["last_error"]
    assert fake.calls[-1] == ("text", "Qoresence Score", "KC 10 - 0 BUF")


def test_unreachable_obs_does_not_crash_and_backs_off(caplog):
    attempts = []

    def boom(_cfg):
        attempts.append(1)
        raise ConnectionRefusedError(f"refused (pw={SECRET})")

    clock = Clock()
    b = ObsBridge(
        ObsBridgeConfig(enabled=True, password=SECRET),
        client_factory=boom,
        frame_stamp=lambda: dict(LIVE),
        clock=clock,
    )
    with caplog.at_level(logging.DEBUG):
        for _ in range(5):
            feed(b, locked(7, 0))
        assert len(attempts) == 1  # backoff: no hammering
        clock.t += 1.5
        b.step()
        assert len(attempts) == 2
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    st = b.stats()
    assert st["connected"] is False and st["last_error"].startswith("connect:")
    assert SECRET not in caplog.text


def test_reconnect_resyncs_text_after_connection_loss():
    fake = FakeObs()
    b, _, clock, _ = make(fake=fake)
    feed(b, locked(7, 0))

    def dead(*_a, **_k):
        raise BrokenPipeError("gone")

    fake.save_replay_buffer = dead  # type: ignore[method-assign]
    feed(b, locked(14, 0))
    assert not b.connected and fake.closed
    fake.save_replay_buffer = lambda: fake.calls.append(("replay",))  # type: ignore[method-assign]
    fake.calls.clear()
    clock.t += 2
    b.step()
    assert b.connected
    assert fake.calls == [("text", "Qoresence Score", "KC 14 - 0 BUF")]


def test_password_never_in_health_or_logs(caplog, monkeypatch):
    monkeypatch.setenv("QORESENCE_OBS_PASSWORD", SECRET)
    cfg = ObsBridgeConfig.from_env(enabled=True, password="argv-ignored")
    assert cfg.password == SECRET
    assert SECRET not in repr(cfg)
    with caplog.at_level(logging.DEBUG):
        b, fake, _, _ = make(cfg)
        b.start(None)
        b.stop()
        feed(b, locked(0, 0))
        feed(b, locked(7, 0))
    blob = json.dumps(b.stats())
    assert SECRET not in blob and '"password_set": true' in blob
    assert SECRET not in caplog.text


def test_real_adapter_silences_obsws_logger(monkeypatch):
    """The obsws-python logger prints the password at INFO; the adapter mutes it."""
    captured = {}

    class FakeReq:
        def __init__(self, **kw):
            captured.update(kw)
            logging.getLogger("obsws_python.baseclient.ObsClient").info(
                "Connecting with parameters: password='%s'", kw["password"]
            )

    mod = types.ModuleType("obsws_python")
    mod.ReqClient = FakeReq  # type: ignore[attr-defined]
    mod.error = types.SimpleNamespace(OBSSDKRequestError=RuntimeError)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "obsws_python", mod)
    records: list[logging.LogRecord] = []

    class H(logging.Handler):
        def emit(self, record):
            records.append(record)

    h = H(level=logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(h)
    try:
        ob._ObsWsClient(ObsBridgeConfig(enabled=True, password=SECRET))
    finally:
        root.removeHandler(h)
    assert captured["password"] == SECRET and captured["port"] == 4455
    assert not any(SECRET in r.getMessage() for r in records)


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("QORESENCE_OBS", raising=False)
    assert ob.make_obs_bridge_from_config(ObsBridgeConfig.from_env()) is None
    assert ob.make_obs_bridge_from_config(None) is None
    assert ob.get_obs_bridge() is None


def test_ignores_other_event_types():
    b, fake, _, _ = make()
    b.on_event(Ev(locked(7, 0).payload, type_="outcome_event"))
    b.step()
    assert b.events_seen == 0


def test_health_includes_bridge_only_when_enabled(monkeypatch):
    monkeypatch.setattr(ob, "_BRIDGE", None)
    body: dict = {"ok": True}
    ob.attach_health(body)
    assert "obs_bridge" not in body
    b, _, _, _ = make(ObsBridgeConfig(enabled=True, password=SECRET))
    monkeypatch.setattr(ob, "_BRIDGE", b)
    ob.attach_health(body)
    assert body["obs_bridge"]["enabled"] is True
    assert SECRET not in json.dumps(body)


def test_both_deck_health_handlers_attach_bridge():
    """FastAPI /health and the stdlib fallback /health both call attach_health."""
    from pathlib import Path

    import qoresence.deck.server as server

    src = Path(server.__file__).read_text(encoding="utf-8")
    assert src.count("_obs_attach_health(body)") == 1
    assert src.count("_obs_attach_health(health)") == 1


def test_obs_bridge_config_survives_dataclasses_replace():
    """--play wiring rebuilds the config with dataclasses.replace(); --obs must survive.

    Live regression: before ``obs_bridge`` was a declared field, the --play path's
    ``replace(config, enable_ws=True)`` dropped the dynamic attribute and the
    bridge silently never started.
    """
    from dataclasses import replace

    from qoresence.core.unified_config import RetinaUnifiedConfig

    cfg = RetinaUnifiedConfig()
    assert cfg.obs_bridge is None
    cfg.obs_bridge = ObsBridgeConfig(enabled=True, scene="Qoresence Flash")
    out = replace(cfg, enable_ws=True)
    assert out.obs_bridge is cfg.obs_bridge
    assert out.obs_bridge.enabled is True
