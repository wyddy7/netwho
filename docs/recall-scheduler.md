# Active Recall scheduler: verified query reduction

## Scope

The synchronous Supabase client remains unchanged. This maintenance change only
removes a redundant lookup from the recall scheduler and bounds the scheduler's
work after slow or missed runs.

## Before and after

📄 **Before (production-log baseline, 2026-08-18):** in a 5 h 35 min healthy
window, the minute-based job ran 336 times and made 3,365 `is_pro()` calls.
Each called `get_user()` despite the same sweep already having selected
`users.*`. That is at least 3,701 user-table calls (336 sweep selects + 3,365
redundant individual selects), before any contact or update calls.

📄 **Baseline rechecked immediately before this change on 2026-09-04:** the
running production image completed 35 recall sweeps in 35 minutes, with 350
per-user subscription decisions (10 rows per sweep), zero sends, zero overlap
skips, and zero errors. The user-scan path therefore made at least 385 DB calls
in that window: 35 batch selects plus 350 redundant individual selects.

📄 **After (verified by `tests/test_recall_scheduler.py`):** one scheduler
sweep over ten loaded rows executes exactly one users-table query and makes no
per-user `get_user()` call. The subscription decision uses each row's
`pro_until` and `trial_ends_at` values, tested for both paid and trial access.

🤖 **Derived equivalent 5 h 35 min comparison:** the new 15-minute cadence schedules
22 sweeps instead of 336. For the user-scan portion, the documented baseline
therefore changes from at least 3,701 DB calls to 22: a 99.4% reduction. This
does not include conditional contact reads or successful-send updates, which
are necessary work and depend on real recall decisions.

## Scheduler policy

- It runs every 15 minutes. The existing eligibility window is 60 minutes, so
  normal delivery remains within 14 minutes of a user's selected time.
- `max_instances=1` prevents concurrent scans; `coalesce=True` collapses
  missed ticks into one scan; `misfire_grace_time=300` discards stale runs more
  than five minutes late rather than replaying a backlog.

Run the regression proof with `uv run pytest tests/test_recall_scheduler.py`.
