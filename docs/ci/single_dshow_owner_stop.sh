#!/usr/bin/env bash
# Optional CI fragment for single DShow owner — no product behavior change.
set -euo pipefail
pytest tests/test_capture_lease.py -q
python - <<'PY'
from pathlib import Path
text = Path("tools/obs/pattern_b_x_live.ps1").read_text(encoding="utf-8")
assert "DUAL_OPEN" in text
assert "WARN: source" not in text or "DUAL_OPEN" in text
print("single_dshow_owner: PASS")
PY
