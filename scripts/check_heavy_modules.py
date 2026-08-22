#!/usr/bin/env python3
"""Fail CI if known-heavy Python modules collapse to stubs (#23 class).

Checks min byte size + required AST class symbols. No network.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (relpath, min_bytes, required ClassDef names)
GATES: list[tuple[str, int, tuple[str, ...]]] = [
    ("qoresence/agents/clutchbot.py", 20_000, ("ClutchBotAgent",)),
    (
        "qoresence/agents/moment_scorer.py",
        15_000,
        ("MomentScorer", "ClipWorthinessModel", "ScoredMoment"),
    ),
]

FAILURES: list[str] = []


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f" FAIL {msg}")
    FAILURES.append(msg)


def _class_names(tree: ast.AST) -> set[str]:
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}


def _is_docstring_stub(tree: ast.Module) -> bool:
    """True if module body is only a docstring and/or pass/ellipsis."""
    body = list(tree.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(getattr(body[0], "value", None), (ast.Constant, ast.Str))
    ):
        body = body[1:]
    if not body:
        return True
    for node in body:
        if isinstance(node, ast.Pass):
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(getattr(node, "value", None), ast.Constant)
            and node.value.value is Ellipsis
        ):
            continue
        return False
    return True


def check_one(rel: str, min_bytes: int, required: tuple[str, ...]) -> None:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing {rel}")
        return
    raw = path.read_bytes()
    n = len(raw)
    if n < min_bytes:
        fail(f"{rel} too small: {n} bytes (min {min_bytes})")
    else:
        ok(f"{rel} size {n} bytes")
    try:
        tree = ast.parse(raw.decode("utf-8"), filename=rel)
    except SyntaxError as e:
        fail(f"{rel} syntax error: {e}")
        return
    if not isinstance(tree, ast.Module):
        fail(f"{rel} not a module")
        return
    if _is_docstring_stub(tree):
        fail(f"{rel} looks like a docstring stub")
    classes = _class_names(tree)
    for name in required:
        if name in classes:
            ok(f"{rel} has class {name}")
        else:
            fail(f"{rel} missing class {name} (have {sorted(classes)[:12]})")


def main() -> int:
    print("Heavy-module size/shape gate")
    print("=" * 40)
    for rel, min_bytes, required in GATES:
        check_one(rel, min_bytes, required)
    print("=" * 40)
    if FAILURES:
        print(f"{len(FAILURES)} failure(s)")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
