"""APScheduler configuration for NetWho's background jobs."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from app.services.recall_service import recall_service


# A recall remains eligible for 60 minutes. Running every 15 minutes bounds the
# normal delivery delay to 14 minutes while avoiding four needless full scans.
RECALL_CRON_MINUTE = "*/15"
RECALL_MISFIRE_GRACE_SECONDS = 300


def configure_recall_scheduler(scheduler: AsyncIOScheduler, bot: Bot) -> None:
    """Register the one non-overlapping recall job with bounded catch-up."""
    scheduler.add_job(
        recall_service.process_recalls,
        "cron",
        id="active_recall",
        minute=RECALL_CRON_MINUTE,
        args=[bot],
        max_instances=1,
        coalesce=True,
        misfire_grace_time=RECALL_MISFIRE_GRACE_SECONDS,
        replace_existing=True,
    )
