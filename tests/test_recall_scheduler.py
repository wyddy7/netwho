"""Regression tests for the bounded, non-N+1 Active Recall scheduler."""
import asyncio
from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace

# The service module constructs Settings at import time. Keep this offline
# regression test runnable without a developer or production .env file.
os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")

from app.scheduler import (  # noqa: E402
    RECALL_CRON_MINUTE,
    RECALL_MISFIRE_GRACE_SECONDS,
    configure_recall_scheduler,
)
from app.services.recall_service import recall_service  # noqa: E402
from app.services.user_service import user_service  # noqa: E402


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.execute_calls = 0

    def select(self, _fields):
        return self

    def execute(self):
        self.execute_calls += 1
        return SimpleNamespace(data=self.rows)


class _Supabase:
    def __init__(self, rows):
        self.users_query = _Query(rows)

    def table(self, name):
        assert name == "users"
        return self.users_query


def test_recall_scan_uses_loaded_subscription_fields_without_per_user_queries(monkeypatch):
    """One scan query stays one query even when it contains many users."""
    rows = [
        {
            "id": user_id,
            # Empty days still reaches the subscription decision, then exits
            # before contact/LLM work regardless of the current weekday.
            "recall_settings": {"enabled": True, "days": []},
            "pro_until": None,
            "trial_ends_at": None,
        }
        for user_id in range(1, 11)
    ]
    supabase = _Supabase(rows)
    monkeypatch.setattr(recall_service, "supabase", supabase)

    async def unexpected_get_user(_user_id):
        raise AssertionError("recall scan must not call get_user for a loaded row")

    monkeypatch.setattr(user_service, "get_user", unexpected_get_user)
    original_loaded_check = user_service.is_pro_from_loaded_row
    checked_user_ids = []

    def track_loaded_check(user):
        checked_user_ids.append(user["id"])
        return original_loaded_check(user)

    monkeypatch.setattr(user_service, "is_pro_from_loaded_row", track_loaded_check)

    asyncio.run(recall_service.process_recalls(bot=object()))

    assert supabase.users_query.execute_calls == 1
    assert checked_user_ids == list(range(1, 11))


def test_loaded_row_subscription_check_covers_paid_and_trial_status():
    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    assert user_service.is_pro_from_loaded_row(
        {"pro_until": (now + timedelta(days=1)).isoformat(), "trial_ends_at": None}, now=now
    )
    assert user_service.is_pro_from_loaded_row(
        {"pro_until": None, "trial_ends_at": now + timedelta(days=1)}, now=now
    )
    assert not user_service.is_pro_from_loaded_row(
        {"pro_until": (now - timedelta(seconds=1)).isoformat(), "trial_ends_at": None}, now=now
    )
    assert not user_service.is_pro_from_loaded_row(
        {"id": 42, "pro_until": "not-a-timestamp", "trial_ends_at": None}, now=now
    )


def test_recall_job_has_bounded_cadence_and_misfire_policy():
    class FakeScheduler:
        def __init__(self):
            self.args = None
            self.kwargs = None

        def add_job(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    scheduler = FakeScheduler()
    bot = object()
    configure_recall_scheduler(scheduler, bot)

    assert scheduler.args[1] == "cron"
    assert scheduler.kwargs == {
        "id": "active_recall",
        "minute": RECALL_CRON_MINUTE,
        "args": [bot],
        "max_instances": 1,
        "coalesce": True,
        "misfire_grace_time": RECALL_MISFIRE_GRACE_SECONDS,
        "replace_existing": True,
    }
