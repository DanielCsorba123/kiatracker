"""A tiny in-process scheduler for the container on the Raspberry Pi: collect every 5 minutes, refresh hourly.

One long-running process instead of cron or Task Scheduler, so the Docker image is the whole deployment and
`restart: unless-stopped` brings it back after a reboot. A failing job is logged and retried at its next turn.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass
class Job:
    name: str
    every: timedelta
    run: Callable[[], object]
    first_delay: timedelta = timedelta(0)
    next_every: Callable[[object], timedelta] | None = None  # pick the next interval from run()'s result
    next_at: datetime | None = field(default=None, init=False)


def run_jobs(
    jobs: list[Job],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    until: Callable[[], bool] = lambda: False,
) -> None:
    start = now()
    for job in jobs:
        job.next_at = start + job.first_delay
    while not until():
        current = now()
        for job in jobs:
            if current >= job.next_at:
                every = job.every
                try:
                    result = job.run()
                    if job.next_every is not None:
                        every = job.next_every(result)
                except Exception as err:  # keep collecting whatever one job does
                    print(
                        f"{current:%m-%d %H:%M}  {job.name} failed: {type(err).__name__}: {err}", flush=True
                    )
                job.next_at += every
                if job.next_at <= current:  # fell behind (e.g. the Pi was suspended): don't run in a burst
                    job.next_at = current + every
        wait = min(job.next_at for job in jobs) - now()
        sleep(max(1.0, wait.total_seconds()))
