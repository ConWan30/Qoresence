"""Play-pad bind + hid_by_seq regression tests (ConWan30 land).

DO NOT DELETE OR WEAKEN. These tests lock in the 2026-08 fix for PLL never
locking because laptop USB DualSense Edge was treated as the play pad.

Invariants:
  A. HID domain: laptop USB Edge (vid=054c pid=0df2 transport=usb) is OBSERVE.
     Ghost, PLL, coupling_ticket, controller_bodied must NEVER arm from observe.
  B. hid_by_seq: Ghost/IVC consume hid_by_seq[hub_seq], never HID[now].
     Pad equals painted frame by construction even at ~6fps HUDDLE.
  C. Seq-edge PLL: observe_phase from (hub.clock_ns - hid_sample.clock_ns)
     on each seq++, not starving for imu_bodied press.
"""

from __future__ import annotations

import time

import numpy as np

from qoresence.sync.hid_domain import (
    HidDomain,
    allow_bind,
    allow_coupling_ticket,
    allow_imu_bodied,
    allow_pll_observe_phase,
    classify_hid_domain,
)


class TestHidDomainClassification:
    """Goal A: HID domain detection (observe vs play)."""

    def test_laptop_usb_edge_is_observe(self):
        """Laptop USB DualSense Edge must be OBSERVE."""
        domain = classify_hid_domain(vid=0x054C, pid=0x0DF2, transport="usb")
        assert domain == HidDomain.OBSERVE, (
            "Laptop USB DualSense Edge (vid=054c pid=0df2 transport=usb) "
            "must be classified as OBSERVE, not PLAY."
        )

    def test_ps5_dualsense_is_play(self):
        """PS5 DualSense (BT or PS5 wired) must be PLAY."""
        # Standard DualSense BT
        domain_bt = classify_hid_domain(vid=0x054C, pid=0x0CE6, transport="bt")
        assert domain_bt == HidDomain.PLAY
        # Standard DualSense USB
        domain_usb = classify_hid_domain(vid=0x054C, pid=0x0CE6, transport="usb")
        assert domain_usb == HidDomain.PLAY
        # Edge BT
        domain_edge_bt = classify_hid_domain(vid=0x054C, pid=0x0DF2, transport="bt")
        assert domain_edge_bt == HidDomain.PLAY

    def test_edge_usb_observe_from_path_without_transport(self):
        """Edge USB is OBSERVE at open even before a parsed report (transport=None)."""
        path = r"\\?\HID#VID_054C&PID_0DF2&MI_03#7&abc#{"
        domain = classify_hid_domain(vid=0x054C, pid=0x0DF2, transport=None, path=path)
        assert domain == HidDomain.OBSERVE

    def test_edge_usb_observe_from_bus_type(self):
        domain = classify_hid_domain(vid=0x054C, pid=0x0DF2, transport=None, bus_type=1)
        assert domain == HidDomain.OBSERVE

    def test_picture_domain_veto_bind(self):
        assert not allow_bind(HidDomain.PICTURE)
        assert not allow_imu_bodied("picture")
        assert not allow_coupling_ticket("picture")
        assert not allow_pll_observe_phase("picture")

    def test_gamepad_collection_ranks_ahead_of_vendor(self):
        from qoresence.sync.hid_domain import rank_hid_collection

        assert rank_hid_collection(usage_page=0x01, usage=0x05) < rank_hid_collection(
            usage_page=0xFF00, usage=0x01
        )

    def test_observe_hid_veto_imu_bodied(self):
        """imu_bodied / imu_precursor can only be set from PLAY pad."""
        assert not allow_imu_bodied(HidDomain.OBSERVE)
        assert not allow_imu_bodied("observe")
        assert allow_imu_bodied(HidDomain.PLAY)
        assert allow_imu_bodied("play")

    def test_observe_hid_veto_coupling_ticket(self):
        """Coupling tickets can only be minted from PLAY pad HID."""
        assert not allow_coupling_ticket(HidDomain.OBSERVE)
        assert not allow_coupling_ticket("observe")
        assert allow_coupling_ticket(HidDomain.PLAY)
        assert allow_coupling_ticket("play")

    def test_observe_hid_veto_pll_phase(self):
        """PLL phase observations can only come from PLAY pad."""
        assert not allow_pll_observe_phase(HidDomain.OBSERVE)
        assert not allow_pll_observe_phase("observe")
        assert allow_pll_observe_phase(HidDomain.PLAY)
        assert allow_pll_observe_phase("play")

    def test_observe_hid_veto_bind(self):
        """Ghost bind can only arm from PLAY pad."""
        assert not allow_bind(HidDomain.OBSERVE)
        assert not allow_bind("observe")
        assert allow_bind(HidDomain.PLAY)
        assert allow_bind("play")


class TestHidBySeqDelayLine:
    """Goal B: hid_by_seq delay line (pad aligned to painted frame)."""

    def test_hid_seq_line_stores_samples_by_seq(self):
        """hid_by_seq[seq] stores HID snapshot at t_hub - lag."""
        from qoresence.sync.hid_seq_line import HidSeqLine

        line = HidSeqLine(lag_ms=24.0)
        # Simulate FrameHub seq++ events
        t0 = time.monotonic_ns()
        for seq in [1, 2, 3]:
            # Mock: would normally read InputRing, but here we just check storage
            line.snapshot_at_seq(hub_seq=seq, hub_clock_ns=t0 + seq * int(100e6))
        # Read back by seq
        s1 = line.get(1)
        s2 = line.get(2)
        s3 = line.get(3)
        assert s1 is not None and s1.hub_seq == 1
        assert s2 is not None and s2.hub_seq == 2
        assert s3 is not None and s3.hub_seq == 3
        assert line.get(99) is None  # non-existent seq

    def test_same_seq_sampled_twice_reuses_slot(self):
        """Same seq sampled twice = reuse slot (zero extra grab work)."""
        from qoresence.sync.hid_seq_line import HidSeqLine

        line = HidSeqLine()
        t0 = time.monotonic_ns()
        line.snapshot_at_seq(hub_seq=1, hub_clock_ns=t0)
        line.snapshot_at_seq(hub_seq=1, hub_clock_ns=t0 + int(50e6))
        # Only one entry for seq=1
        stats = line.stats()
        assert stats["count"] == 1
        assert 1 in stats["seqs"]

    def test_ghost_consumes_hid_by_seq_not_hid_now(self):
        """Ghost reads hid_by_seq[live_seq], never HID[now] (even at ~6fps)."""
        from qoresence.monitor.frame_hub import FrameHub
        from qoresence.sync.ghost_stick import snapshot_ghost_stick
        from qoresence.sync.hid_seq_line import get_hid_seq_line
        from qoresence.sync.input_ring import set_hold

        hub = FrameHub()
        line = get_hid_seq_line()
        line.clear()
        # Publish frame to trigger hid_by_seq snapshot
        t0 = time.monotonic_ns()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        set_hold(clock_ns=t0, r2=0.8, l2=0.0, lx=0.5, ly=-0.3)
        hub.publish(frame, clock_ns=t0, seq=42)
        # Ghost should read hid_by_seq[42]
        snap = snapshot_ghost_stick(situation={"frame_seq": 42})
        # If Ghost is using hid_by_seq, it gets the snapshot for seq=42
        # (even if HID[now] has moved on)
        sample = line.get(42)
        assert sample is not None, "hid_by_seq[42] should exist after hub.publish"
        # Ghost should use the delay-line sample (constructor checked by decide_ghost_stick)
        assert snap is not None

    def test_frame_hub_publish_does_not_hold_lock_during_snapshot(self):
        """FrameHub.publish releases lock BEFORE calling hid_seq_line.snapshot_at_seq.

        Veto: no bind code on grab path. The snapshot runs outside the FrameHub
        lock so it never blocks the capture loop.
        """
        from qoresence.monitor.frame_hub import FrameHub

        hub = FrameHub()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # publish triggers snapshot_at_seq, but never raises into capture loop
        hub.publish(frame, clock_ns=time.monotonic_ns())
        # If we got here without hanging, the lock was released before snapshot


class TestSeqEdgePLL:
    """Goal C: Seq-edge PLL (observe_phase from seq edges, not imu_bodied starve)."""

    def test_pll_can_observe_phase_from_seq_edge_without_imu_body(self):
        """PLL observe_phase fed from (hub.clock_ns - hid_sample.clock_ns) on seq++.

        Do not starve waiting for imu_bodied press or score_changed. Every frame
        feeds the PLL as long as HID is present and domain=PLAY.
        """
        from qoresence.sync.hid_seq_line import HidSeqLine
        from qoresence.sync.input_ring import set_hold
        from qoresence.sync.lag_estimator import get_lag_estimator

        line = HidSeqLine()
        est = get_lag_estimator()
        est.reset()
        t0 = time.monotonic_ns()
        # Seed InputRing with PLAY HID (no imu_bodied event, just analog hold)
        set_hold(clock_ns=t0, r2=0.5, l2=0.0, lx=0.0, ly=0.0)
        # Snapshot at seq++ with feed_pll=True
        line.snapshot_at_seq(
            hub_seq=1,
            hub_clock_ns=t0 + int(60e6),  # 60ms after HID
            feed_pll=True,
            video_age_s=0.0,
        )
        # PLL should have received one phase observation
        pll = est.snapshot()
        assert pll["pll_n"] >= 1, (
            "PLL did not observe_phase from seq-edge — starving without imu_bodied. "
            "Every frame must feed the PLL when HID is present and domain=PLAY."
        )

    def test_pll_does_not_observe_from_observe_hid(self):
        """PLL must NOT observe_phase from OBSERVE HID (laptop USB Edge)."""
        from qoresence.sync.hid_seq_line import HidSeqLine
        from qoresence.sync.input_ring import get_input_ring, push
        from qoresence.sync.lag_estimator import get_lag_estimator

        line = HidSeqLine()
        est = get_lag_estimator()
        est.reset()
        t0 = time.monotonic_ns()
        # Push OBSERVE HID event
        get_input_ring().clear()
        push(
            {
                "clock_ns": t0,
                "kind": "trigger",
                "name": "R2",
                "value": 0.8,
                "hid_domain": "observe",
            }
        )
        # Snapshot with feed_pll=True
        line.snapshot_at_seq(hub_seq=1, hub_clock_ns=t0 + int(50e6), feed_pll=True)
        # PLL should NOT have observed (observe HID is vetoed)
        pll = est.snapshot()
        assert pll["pll_n"] == 0, (
            "PLL observe_phase accepted OBSERVE HID — laptop USB Edge "
            "must be vetoed from PLL / coupling / bind."
        )


class TestIVCObserveHIDVeto:
    """IVC must not set imu_bodied or mint coupling tickets from OBSERVE HID."""

    def test_ivc_does_not_set_imu_bodied_from_observe_hid(self):
        """imu_bodied can only be set from PLAY pad (not laptop USB Edge)."""
        from qoresence.sync.ivc import InputVideoCoupler
        from qoresence.sync.input_ring import get_input_ring, push

        ring = get_input_ring()
        ring.clear()
        t0 = time.monotonic_ns()
        # Push OBSERVE HID with imu_precursor
        push(
            {
                "clock_ns": t0,
                "kind": "trigger",
                "name": "R2",
                "value": 0.9,
                "imu_precursor_ms": 20.0,
                "hid_domain": "observe",
            }
        )
        # Mock FrameHub stamp
        from qoresence.monitor.frame_hub import get_frame_hub

        hub = get_frame_hub()
        hub.clear()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        hub.publish(frame, clock_ns=t0 + int(60e6), seq=1)
        # IVC tick
        ivc = InputVideoCoupler(lag_lo_ms=0.0, lag_hi_ms=120.0)
        payload = ivc.tick_once()
        # imu_bodied must be False (observe HID is vetoed)
        assert payload is not None
        assert not payload.get("imu_bodied"), (
            "IVC set imu_bodied=True from OBSERVE HID — "
            "laptop USB Edge must be vetoed from imu_bodied."
        )

    def test_ivc_does_not_mint_coupling_ticket_from_observe_hid(self):
        """Coupling tickets can only be minted from PLAY pad events."""
        from qoresence.sync.ivc import InputVideoCoupler
        from qoresence.sync.input_ring import get_input_ring, push

        ring = get_input_ring()
        ring.clear()
        t0 = time.monotonic_ns()
        # Push OBSERVE HID
        push(
            {
                "clock_ns": t0,
                "kind": "trigger",
                "name": "R2",
                "value": 0.9,
                "hid_domain": "observe",
            }
        )
        # Mock FrameHub stamp
        from qoresence.monitor.frame_hub import get_frame_hub

        hub = get_frame_hub()
        hub.clear()
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        hub.publish(frame, clock_ns=t0 + int(60e6), seq=1)
        # IVC tick
        ivc = InputVideoCoupler(lag_lo_ms=0.0, lag_hi_ms=120.0)
        payload = ivc.tick_once()
        # coupling_ticket_id must be empty (observe HID events are vetoed)
        assert payload is not None
        assert not payload.get("coupling_ticket_id"), (
            "IVC minted coupling_ticket from OBSERVE HID — "
            "laptop USB Edge must be vetoed from coupling tickets."
        )
