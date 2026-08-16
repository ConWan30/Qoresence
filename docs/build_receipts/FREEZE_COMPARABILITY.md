# FREEZE count comparability (schema v2)

Pre-C3 closeouts report only aggregate `freeze_events`. Schema v2 adds `freeze_events_by_kind` and `freeze_events_excluding_deck_lock`. Prefer the excluding-deck_lock figure when comparing stability across the C3 boundary.

Detection is unchanged. `freeze_events` is still the total storm count.

Local receipt: `logs/build/freeze_comparability_*`.
