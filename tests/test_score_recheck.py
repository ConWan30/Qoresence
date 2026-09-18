from dataclasses import replace

from qoresence.vision.score_recheck import BoardObservation, ScoreRecheck


def observation(seq, home=20, away=0, **kw):
    return BoardObservation(
        session_id="s", frame_seq=seq, captured_ns=seq * 1_000_000_000,
        crop_hash="crop", home_team="A", away_team="B", home_score=home,
        away_score=away, **kw,
    )


def test_safety_and_separate_extra_point():
    guard = ScoreRecheck()
    assert guard.evaluate(observation(1, 7, 3), 1_000_000_000) == "accepted"
    assert guard.evaluate(observation(2, 9, 3), 2_000_000_000) == "accepted"
    assert guard.evaluate(observation(3, 15, 3), 3_000_000_000) == "accepted"
    assert guard.evaluate(observation(4, 16, 3), 4_000_000_000) == "accepted"


def test_echo_requires_new_source_frame_not_cached_reads():
    guard = ScoreRecheck()
    guard.evaluate(observation(1), 1_000_000_000)
    candidate = observation(2, away=20)
    assert guard.evaluate(candidate, 2_000_000_000) == "recheck"
    assert guard.evaluate(candidate, 3_000_000_000) == "duplicate"
    assert guard.evaluate(observation(3, away=20), 3_000_000_000) == "accepted"


def test_correction_and_both_sides_can_recover():
    for pair in [(14, 0), (23, 3), (30, 0)]:
        guard = ScoreRecheck()
        guard.evaluate(observation(1), 1_000_000_000)
        assert guard.evaluate(observation(2, *pair), 2_000_000_000) == "recheck"
        assert guard.evaluate(observation(3, *pair), 3_000_000_000) == "accepted"


def test_stale_future_and_out_of_order_results_do_not_advance():
    guard = ScoreRecheck()
    first = observation(1)
    assert guard.evaluate(first, 10_000_000_000) == "stale"
    assert guard.evaluate(first, 0) == "stale"
    assert guard.evaluate(observation(3), 3_000_000_000) == "accepted"
    assert guard.evaluate(observation(2), 3_000_000_000) == "out_of_order"


def test_long_observation_gap_rebaselines_not_single_play_law():
    guard = ScoreRecheck()
    guard.evaluate(observation(1), 1_000_000_000)
    assert guard.evaluate(observation(40, 40, 21), 40_000_000_000) == "accepted"


def test_new_session_and_side_mapping_do_not_corroborate_old_candidate():
    guard = ScoreRecheck()
    guard.evaluate(observation(1), 1_000_000_000)
    guard.evaluate(observation(2, away=20), 2_000_000_000)
    changed = replace(observation(3, away=20), home_team="B", away_team="A")
    assert guard.evaluate(changed, 3_000_000_000) == "accepted"
    assert guard.evaluate(replace(observation(1), session_id="new"), 4_000_000_000) == "accepted"


def test_rechecks_are_bounded_and_timeout_never_accepts():
    guard = ScoreRecheck()
    guard.evaluate(observation(1), 1_000_000_000)
    assert guard.evaluate(observation(2, 30), 2_000_000_000) == "recheck"
    assert guard.evaluate(observation(3, 40), 3_000_000_000) == "recheck"
    assert guard.evaluate(observation(4, 50), 4_000_000_000) == "exhausted"
    assert guard.evaluate(observation(5, 50), 5_000_000_000) == "exhausted"
    assert guard.evaluate(observation(6, 23), 6_000_000_000) == "accepted"


def test_missing_identity_never_counts_as_corroboration():
    guard = ScoreRecheck()
    assert guard.evaluate(replace(observation(1), home_team=""), 1_000_000_000) == "missing_evidence"
