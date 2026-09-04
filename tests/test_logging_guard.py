"""The logging guard: a loguru call must be incapable of raising.

Every test in the first class FAILS on unguarded code: without
app/logging_guard.py, ``logger.error("x {'error': 1}", exc_info=True)``
raises ``KeyError("'error'")`` from loguru's str.format() pass — the
2026-08-18 incident that replaced a plain 401 with an unreadable log line.

These tests are also the pre-deploy gate for the guard itself: install()
depends on loguru==0.7.3 private internals and self-verifies; a loguru bump
that breaks it fails HERE (and at bot startup), not silently in production.
"""

import sys
from pathlib import Path

import pytest
from loguru import logger

from app.logging_guard import install

install()


@pytest.fixture()
def sink():
    captured = []
    handler_id = logger.add(
        captured.append,
        level="DEBUG",
        format="{name}|{function}|{line}|{message}\n{exception}",
    )
    yield captured
    logger.remove(handler_id)


class TestGuardRuntime:
    def test_incident_call_does_not_raise_and_keeps_the_traceback(self, sink):
        """The exact incident shape: stdlib idiom + JSON braces, inside except."""
        try:
            raise ValueError("401 - {'error': {'message': 'User not found.'}}")
        except ValueError:
            logger.error("Router Agent failed", exc_info=True)  # logging-ci: allow

        text = "".join(str(m) for m in sink)
        assert "Router Agent failed" in text
        assert "Traceback" in text
        assert "ValueError" in text
        assert "User not found" in text

    def test_braces_in_message_with_exc_info_do_not_raise(self, sink):
        """The literal repro one-liner (no active exception → no traceback)."""
        logger.error("x {'error': 1}", exc_info=True)  # logging-ci: allow
        text = "".join(str(m) for m in sink)
        assert "x {'error': 1}" in text

    def test_generic_format_failure_falls_back_instead_of_raising(self, sink):
        logger.error("bad {oops}", nope=1)
        text = "".join(str(m) for m in sink)
        assert "[logging-guard]" in text
        assert "bad {oops}" in text  # the raw message survives

    def test_caller_attribution_points_at_this_test_not_the_guard(self, sink):
        """Depth math: a regression here silently ruins every log line."""
        logger.error("attribution probe")
        name, function, line, _rest = str(sink[0]).split("|", 3)
        assert name == __name__
        assert function == "test_caller_attribution_points_at_this_test_not_the_guard"
        assert int(line) > 0

    def test_correct_loguru_calls_are_untouched(self, sink):
        logger.error("ok {x}", x=1)
        assert "ok 1" in str(sink[0])

    def test_logger_exception_still_carries_traceback(self, sink):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception("static context")
        text = "".join(str(m) for m in sink)
        assert "static context" in text
        assert "RuntimeError" in text and "boom" in text

    def test_install_is_idempotent(self, sink):
        install()
        install()
        logger.error("once")
        assert len(sink) == 1


class TestCheckLoggingGate:
    """The CI gate must actually catch what the guard defends against."""

    @pytest.fixture(autouse=True)
    def _import_checker(self):
        scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
        sys.path.insert(0, scripts_dir)
        import check_logging

        self.check_file = check_logging.check_file
        yield
        sys.path.remove(scripts_dir)

    def _problems(self, tmp_path, source):
        f = tmp_path / "bad.py"
        f.write_text(source, encoding="utf-8")
        return self.check_file(f)

    def test_catches_exc_info_kwarg(self, tmp_path):
        assert self._problems(
            tmp_path, 'logger.error("x", exc_info=True)\n'
        )

    def test_catches_multiline_exc_info(self, tmp_path):
        """The incident's 9th site was multiline and invisible to grep."""
        src = 'logger.error(\n    f"failed: {e} "\n    f"more",\n    exc_info=True\n)\n'
        assert self._problems(tmp_path, src)

    def test_catches_fstring_plus_kwargs(self, tmp_path):
        assert self._problems(
            tmp_path, 'logger.error(f"failed: {err}", user=user_id)\n'
        )

    def test_allows_static_template_with_kwargs(self, tmp_path):
        assert not self._problems(
            tmp_path, 'logger.error("failed: {m}", m=str(e))\n'
        )

    def test_allows_plain_fstring_without_args(self, tmp_path):
        assert not self._problems(
            tmp_path, 'logger.warning(f"queue depth {depth}")\n'
        )

    def test_allow_marker_is_respected(self, tmp_path):
        assert not self._problems(
            tmp_path, 'logger.error("x", exc_info=True)  # logging-ci: allow\n'
        )

    def test_catches_secret_in_fstring(self, tmp_path):
        assert self._problems(
            tmp_path, 'logger.info(f"proxy={settings.PROXY_URL}")\n'
        )

    def test_catches_secret_as_format_value(self, tmp_path):
        assert self._problems(
            tmp_path,
            'logger.info("proxy={proxy}", proxy=settings.PROXY_URL)\n',
        )

    def test_allows_secret_presence_as_boolean(self, tmp_path):
        assert not self._problems(
            tmp_path,
            'logger.info("has_proxy={value}", value=bool(settings.PROXY_URL))\n',
        )

    def test_repo_tree_is_clean(self):
        """Zero forbidden calls in the actual codebase."""
        root = Path(__file__).resolve().parent.parent
        import check_logging

        problems = []
        for path in sorted(root.rglob("*.py")):
            if any(p in check_logging.SKIP_DIRS for p in path.parts):
                continue
            problems.extend(check_logging.check_file(path))
        assert problems == []
