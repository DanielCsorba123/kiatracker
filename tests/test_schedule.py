from datetime import UTC, datetime, timedelta

from kiatracker.schedule import Job, run_jobs


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += timedelta(seconds=seconds)


def test_jobs_run_on_their_intervals():
    clock, ran = Clock(), []
    end = clock.t + timedelta(hours=2)
    jobs = [
        Job("collect", timedelta(minutes=5), lambda: ran.append("c")),
        Job("refresh", timedelta(hours=1), lambda: ran.append("r"), first_delay=timedelta(minutes=2)),
    ]
    run_jobs(jobs, now=clock.now, sleep=clock.sleep, until=lambda: clock.t >= end)
    assert ran.count("c") == 24 and ran.count("r") == 2
    assert ran[0] == "c"  # collect first, refresh two minutes later


def test_a_failing_job_does_not_stop_the_others(capsys):
    clock, ran = Clock(), []
    end = clock.t + timedelta(minutes=30)

    def broken():
        raise RuntimeError("API down")

    jobs = [
        Job("refresh", timedelta(minutes=10), broken),
        Job("collect", timedelta(minutes=5), lambda: ran.append(1)),
    ]
    run_jobs(jobs, now=clock.now, sleep=clock.sleep, until=lambda: clock.t >= end)
    assert len(ran) == 6
    assert "refresh failed: RuntimeError" in capsys.readouterr().out
