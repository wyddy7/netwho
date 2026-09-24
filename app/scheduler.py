"""APScheduler configuration for NetWho's background jobs."""

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from loguru import logger

from app.services.recall_service import recall_service


# A recall remains eligible for 60 minutes. Running every 15 minutes bounds the
# normal delivery delay to 14 minutes while avoiding four needless full scans.
RECALL_CRON_MINUTE = "*/15"
RECALL_MISFIRE_GRACE_SECONDS = 300
# Hard cap on one run (retries included), well under the 15-minute interval,
# so a stuck run can never hold the max_instances=1 slot into the next tick.
RECALL_JOB_TIMEOUT_SECONDS = 600


async def run_recall_job(bot: Bot) -> None:
    """One bounded recall run; a timeout is logged, not raised into APScheduler."""
    try:
        await asyncio.wait_for(recall_service.process_recalls(bot), timeout=RECALL_JOB_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.error("Recall job cancelled after {timeout}s timeout", timeout=RECALL_JOB_TIMEOUT_SECONDS)


def configure_recall_scheduler(scheduler: AsyncIOScheduler, bot: Bot) -> None:
    """Register the one non-overlapping recall job with bounded catch-up."""
    scheduler.add_job(
        run_recall_job,
        "cron",
        id="active_recall",
        minute=RECALL_CRON_MINUTE,
        args=[bot],
        max_instances=1,
        coalesce=True,
        misfire_grace_time=RECALL_MISFIRE_GRACE_SECONDS,
        replace_existing=True,
    )
