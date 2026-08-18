"""Runtime guard: a loguru logging call must be incapable of raising.

Why this exists (incident 2026-08-18): loguru has no ``exc_info`` parameter —
that is stdlib ``logging``. loguru does not ignore the unknown kwarg either:
any extra arg/kwarg switches the call into ``str.format()`` mode, so a message
containing braces (every JSON API error body does) detonates with ``KeyError``
*inside the except block that was trying to report the real failure*. The
original exception is replaced by the logger's own and diagnosis becomes
impossible exactly when it is needed most.

The guard patches ``loguru._logger.Logger._log`` (single choke point — covers
``bind()``/``opt()``/``exception()`` children automatically) so that:

1. stdlib-only kwargs (``exc_info``/``stack_info``/``stacklevel``) are stripped;
   a truthy ``exc_info`` is translated to loguru's ``exception`` option, so the
   stdlib idiom degrades to *working correctly* instead of raising;
2. any formatting failure is caught and re-emitted as a raw, unformatted
   fallback line at the same level (with the traceback preserved) instead of
   propagating out of the logging call.

This is a runtime safety net, NOT an endorsement of ``exc_info=`` — CI bans
writing it (``scripts/check_logging.py``). Defense in depth: the linter keeps
the code idiomatic, the guard keeps a slip from ever taking the bot down.

Pinned to loguru==0.7.3 internals. ``install()`` verifies the private API
shape and runs a live self-test; on any mismatch it rolls back and raises, so
a loguru version bump that breaks the guard fails loudly at startup (and in
CI via tests/test_logging_guard.py), never silently in production.

Installed from two places:
- ``app/config.py`` — the app path; failures raise and stop startup;
- ``/app/sitecustomize.py`` in the container — every interpreter, including
  ad-hoc ``docker exec ... python``; failures are swallowed there.
"""

import inspect

_STDLIB_ONLY_KWARGS = ("exc_info", "stack_info", "stacklevel")
_EXPECTED_LOG_PARAMS = ["self", "level", "from_decorator", "options", "message", "args", "kwargs"]
_OPTIONS_LEN = 9  # (exception, depth, record, lazy, colors, raw, capture, patchers, extra)

_original_log = None


def _guarded_log(self, level, from_decorator, options, message, args, kwargs):
    (exception, depth, record, lazy, colors, raw, capture, patchers, extra) = options

    if kwargs and any(k in kwargs for k in _STDLIB_ONLY_KWARGS):
        exc_info = kwargs.pop("exc_info", None)
        kwargs.pop("stack_info", None)
        kwargs.pop("stacklevel", None)
        if not exception:
            if exc_info is True:
                exception = True
            elif isinstance(exc_info, BaseException):
                exception = exc_info
            elif isinstance(exc_info, tuple) and len(exc_info) == 3 and exc_info[0] is not None:
                exception = exc_info

    # This wrapper adds exactly one frame between the public method and the
    # original _log, whatever the call path — compensate so {name}:{function}:
    # {line} keep pointing at the real caller.
    options = (exception, depth + 1, record, lazy, colors, raw, capture, patchers, extra)

    try:
        _original_log(self, level, from_decorator, options, message, args, kwargs)
    except Exception as format_error:  # noqa: BLE001 — the whole point
        try:
            fallback = (
                "[logging-guard] log call could not be formatted (%s: %s) — "
                "raw message follows, format args dropped: %s"
                % (type(format_error).__name__, format_error, message)
            )
            # No args/kwargs → loguru does not run str.format() → cannot raise
            # on braces. Level and exception option are preserved.
            _original_log(self, level, from_decorator, options, fallback, (), {})
        except Exception:  # noqa: BLE001 — last resort: lose the line, never raise
            pass


def _verify_private_api(logger_cls):
    params = list(inspect.signature(logger_cls._log).parameters)
    if params != _EXPECTED_LOG_PARAMS:
        raise RuntimeError(
            "logging_guard: loguru Logger._log signature changed "
            "(got %r, expected %r) — the installed loguru version does not "
            "match what the guard was written against; update app/logging_guard.py"
            % (params, _EXPECTED_LOG_PARAMS)
        )
    from loguru import logger as global_logger

    if len(global_logger._options) != _OPTIONS_LEN:
        raise RuntimeError(
            "logging_guard: loguru options tuple has %d elements, expected %d — "
            "update app/logging_guard.py for this loguru version"
            % (len(global_logger._options), _OPTIONS_LEN)
        )


def _self_test(logger_cls):
    """Exercise the patched path on a private Logger — zero side effects."""
    from loguru._logger import Core

    probe = logger_cls(
        core=Core(),
        exception=None,
        depth=0,
        record=False,
        lazy=False,
        colors=False,
        raw=False,
        capture=True,
        patchers=[],
        extra={},
    )
    captured = []
    probe.add(
        captured.append,
        level="DEBUG",
        format="{name}|{function}|{line}|{message}\n{exception}",
    )

    # 1. The incident call: stdlib idiom + JSON braces, inside an except block.
    try:
        raise ValueError("guard-self-test {'error': {'code': 401}}")
    except ValueError:
        probe.error("probe {'error': 1}", exc_info=True)  # logging-ci: allow

    text = "".join(str(m) for m in captured)
    if "probe {'error': 1}" not in text:
        raise RuntimeError("logging_guard self-test: message was not emitted")
    if "Traceback" not in text or "guard-self-test" not in text:
        raise RuntimeError("logging_guard self-test: traceback was not emitted")
    if "|_self_test|" not in text:
        raise RuntimeError(
            "logging_guard self-test: caller attribution broken (depth math)"
        )

    # 2. A generic formatting failure must fall back, not raise.
    captured.clear()
    probe.error("unformattable {oops}", nope=1)
    text = "".join(str(m) for m in captured)
    if "[logging-guard]" not in text or "unformattable {oops}" not in text:
        raise RuntimeError("logging_guard self-test: formatting fallback broken")


def install():
    """Install the guard. Idempotent. Raises RuntimeError if the guard cannot
    be proven working — callers on the app path must let that propagate."""
    global _original_log
    from loguru._logger import Logger

    if getattr(Logger, "_netwho_logging_guard", False):
        return

    _verify_private_api(Logger)

    _original_log = Logger._log
    Logger._log = _guarded_log
    try:
        _self_test(Logger)
    except Exception:
        Logger._log = _original_log  # roll back to the known (bad but familiar) state
        _original_log = None
        raise
    # Marker only after the self-test passed — a failed install must stay loud.
    Logger._netwho_logging_guard = True
