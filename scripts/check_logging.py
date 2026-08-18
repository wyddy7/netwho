#!/usr/bin/env python3
"""CI gate: ban loguru logging calls that can raise. Stdlib-only, no deps.

netwho logs through loguru, and loguru re-formats the message whenever a
logging call carries ANY extra args/kwargs. Two call shapes are therefore
build errors here:

1. stdlib-only kwargs: ``logger.error(..., exc_info=True)`` (also
   ``stack_info=``/``stacklevel=``). loguru has no such parameters; the
   unknown kwarg switches the call into ``str.format()`` mode and a brace in
   the message (every JSON error body has one) raises KeyError INSIDE the
   except block. Use ``logger.exception("static message")`` or
   ``logger.opt(exception=True).error(...)`` instead.

2. f-string message plus any args/kwargs: the already-interpolated string is
   formatted AGAIN, so braces in the interpolated data detonate the same way.
   Use a static template and pass values as kwargs:
   ``logger.error("failed: {m}", m=str(e))`` — substituted values are never
   re-formatted.

AST-based on purpose: the incident's 9th call site was multiline and
invisible to grep. Escape hatch for intentional cases (the guard's own
self-test, tests): append ``# logging-ci: allow`` on the offending line.

A runtime safety net for the same class lives in app/logging_guard.py; this
script is the "never gets written" half, the guard is the "never detonates"
half.
"""

import ast
import sys
from pathlib import Path

LOG_METHODS = {
    "trace", "debug", "info", "success", "warning",
    "error", "critical", "exception", "log",
}
STDLIB_ONLY_KWARGS = {"exc_info", "stack_info", "stacklevel"}
SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", ".mypy_cache", ".ruff_cache"}
ALLOW_MARKER = "# logging-ci: allow"


def is_log_call(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Attribute) and node.func.attr in LOG_METHODS


def check_file(path: Path) -> list:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        return [(path, e.lineno or 0, "syntax error: %s" % e.msg)]

    def allowed(node) -> bool:
        start = node.lineno - 1
        end = getattr(node, "end_lineno", node.lineno)
        return any(ALLOW_MARKER in lines[i] for i in range(start, min(end, len(lines))))

    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # Rule 1: stdlib-only kwargs on ANY call (netwho is loguru-only, so
        # exc_info= is wrong everywhere, whatever the receiver is called).
        bad_kwargs = sorted(
            kw.arg for kw in node.keywords if kw.arg in STDLIB_ONLY_KWARGS
        )
        if bad_kwargs and not allowed(node):
            problems.append((
                path, node.lineno,
                "%s= is stdlib logging, not loguru — it switches the call into "
                "str.format() mode and braces in the message raise KeyError. "
                "Use logger.exception(\"static message\") or "
                "logger.opt(exception=True)." % "/".join(bad_kwargs),
            ))
            continue

        # Rule 2: f-string message + extra format args/kwargs on a log call.
        if (
            is_log_call(node)
            and node.args
            and isinstance(node.args[0], ast.JoinedStr)
            and (len(node.args) > 1 or node.keywords)
            and not allowed(node)
        ):
            problems.append((
                path, node.lineno,
                "f-string message plus extra args/kwargs: loguru re-formats the "
                "already-interpolated string, braces in the data detonate. Use a "
                "static template with values as kwargs: "
                "logger.error(\"failed: {m}\", m=str(e)).",
            ))
    return problems


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    problems = []
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        problems.extend(check_file(path))

    if problems:
        print("check_logging: %d forbidden logging call(s):\n" % len(problems))
        for path, lineno, msg in problems:
            print("  %s:%d\n    %s\n" % (path.relative_to(root), lineno, msg))
        print("Intentional (tests/self-checks only): append '%s'." % ALLOW_MARKER)
        return 1
    print("check_logging: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
