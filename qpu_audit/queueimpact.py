"""Queue impact analysis.

Consuming QPU time and delaying other people are different quantities. Even
legitimate work, split into a thousand jobs fired a tenth of a second apart, pushes
everyone else back. This module measures that.

Intervals are approximated from ``created``, ``ended`` and actual QPU time::

    execution = [ended - qpu_seconds, ended]
    wait      = [created, ended - qpu_seconds]

**Being queued at the same time is not the same as blocking.** A serial QPU is
blocked by *occupancy*, so impact is measured as time spent executing while another
user's job was waiting. A job merely sitting in the queue blocks nobody.

Jobs without an end timestamp are excluded — including them makes a single pending
job appear to block everyone for days.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

# Submissions within this window count as one burst.
BURST_WINDOW_SECONDS = 60.0
BURST_MIN_JOBS = 5


@dataclass
class Interval:
    start: datetime
    end: datetime

    @property
    def seconds(self) -> float:
        return max((self.end - self.start).total_seconds(), 0.0)


@dataclass
class QueueImpact:
    user_id: str
    label: str = ""
    jobs: int = 0
    backends: set[str] = field(default_factory=set)

    # Total time this user's jobs spent queued (summed per job)
    pending_job_hours: float = 0.0
    max_concurrent: int = 0
    own_wait_hours: float = 0.0
    qpu_hours: float = 0.0

    # Time this user occupied the QPU while other users were waiting
    others_wait_overlap_hours: float = 0.0
    others_jobs_affected: int = 0
    others_users_affected: int = 0

    max_burst: int = 0
    burst_count: int = 0
    median_gap_seconds: float | None = None
    sub_second_gaps: int = 0
    # Session/batch containers this user created. Determined from workloads.mode, so
    # it is reliable even when job-level session_id is empty. Zero means every job
    # was submitted individually.
    containers: int = 0
    blocking_share: float = 0.0


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _merge(intervals: list[Interval]) -> list[Interval]:
    """Merge overlaps so concurrent jobs from one user count their time once."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda i: i.start)
    merged = [Interval(ordered[0].start, ordered[0].end)]
    for item in ordered[1:]:
        last = merged[-1]
        if item.start <= last.end:
            if item.end > last.end:
                last.end = item.end
        else:
            merged.append(Interval(item.start, item.end))
    return merged


def _overlap(a: Interval, merged: list[Interval]) -> float:
    """Intersection length in seconds between one interval and a merged list."""
    total = 0.0
    for item in merged:
        if item.end <= a.start:
            continue
        if item.start >= a.end:
            break
        total += (min(a.end, item.end) - max(a.start, item.start)).total_seconds()
    return max(total, 0.0)


def _max_concurrent(intervals: Iterable[Interval]) -> int:
    events: list[tuple[datetime, int]] = []
    for item in intervals:
        events.append((item.start, 1))
        events.append((item.end, -1))
    events.sort(key=lambda e: (e[0], -e[1]))
    current = peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def _bursts(timestamps: list[datetime]) -> tuple[int, int, float | None, int]:
    """(largest burst, burst count, median gap, gaps under one second)."""
    ordered = sorted(timestamps)
    if len(ordered) < 2:
        return len(ordered), 0, None, 0

    gaps = [(b - a).total_seconds() for a, b in zip(ordered, ordered[1:])]
    gaps_sorted = sorted(gaps)
    median = gaps_sorted[len(gaps_sorted) // 2]
    sub_second = sum(1 for g in gaps if g < 1.0)

    max_burst = burst_count = 0
    size = 1
    for gap in gaps:
        if gap <= BURST_WINDOW_SECONDS:
            size += 1
        else:
            if size >= BURST_MIN_JOBS:
                burst_count += 1
            max_burst = max(max_burst, size)
            size = 1
    if size >= BURST_MIN_JOBS:
        burst_count += 1
    max_burst = max(max_burst, size)
    return max_burst, burst_count, median, sub_second


def analyze_queue(store: Any, window_days: int, user_map: Any = None) -> list[QueueImpact]:
    """Per-user queue occupancy and delay inflicted on others."""
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    window_start = since.isoformat().replace("+00:00", "Z")

    rows = store.query(
        """
        SELECT w.id, w.user_id, w.backend, w.created, w.ended, w.mode,
               COALESCE(w.usage_seconds, 0) AS usage_seconds,
               j.session_id
        FROM workloads w
        LEFT JOIN jobs j ON j.id = w.id
        WHERE w.created >= ? AND w.user_id IS NOT NULL AND w.mode = 'job'
        ORDER BY w.created
        """,
        (window_start,),
    )

    # Session/batch container counts come from workloads.mode, which is definitive.
    containers: dict[str, int] = {
        row["user_id"]: row["n"]
        for row in store.query(
            "SELECT user_id, COUNT(*) AS n FROM workloads "
            "WHERE mode IN ('session','batch') AND created >= ? AND user_id IS NOT NULL "
            "GROUP BY user_id",
            (window_start,),
        )
    }

    waits: dict[str, dict[str, list[Interval]]] = {}
    execs: dict[str, dict[str, list[Interval]]] = {}
    per_user_times: dict[str, list[datetime]] = {}
    per_user_jobs: dict[str, int] = {}

    for row in rows:
        created = _parse(row["created"])
        user = row["user_id"]
        if created:
            per_user_times.setdefault(user, []).append(created)
        per_user_jobs[user] = per_user_jobs.get(user, 0) + 1

        ended = _parse(row["ended"])
        if created is None or ended is None:
            # An unfinished job has no bounded interval. Including it produces
            # nonsense like "one job blocked everyone for days".
            continue

        backend = row["backend"] or "(unknown)"
        usage = float(row["usage_seconds"] or 0.0)
        exec_start = ended - timedelta(seconds=usage)
        if exec_start < created:
            exec_start = created

        waits.setdefault(backend, {}).setdefault(user, []).append(Interval(created, exec_start))
        if usage > 0:
            execs.setdefault(backend, {}).setdefault(user, []).append(Interval(exec_start, ended))

    impacts: dict[str, QueueImpact] = {}
    wait_total_seconds = 0.0

    for backend, by_user in waits.items():
        exec_by_user = {
            user: _merge(items) for user, items in execs.get(backend, {}).items()
        }

        for user, items in by_user.items():
            impact = impacts.setdefault(user, QueueImpact(user_id=user))
            impact.backends.add(backend)
            impact.own_wait_hours += sum(i.seconds for i in items) / 3600.0
            impact.pending_job_hours += sum(i.seconds for i in items) / 3600.0
            impact.max_concurrent = max(impact.max_concurrent, _max_concurrent(items))
            impact.qpu_hours += (
                sum(i.seconds for i in execs.get(backend, {}).get(user, [])) / 3600.0
            )

        # What blocks others is QPU occupancy, not queue presence.
        for user, my_exec in exec_by_user.items():
            if not my_exec:
                continue
            impact = impacts.setdefault(user, QueueImpact(user_id=user))
            affected_jobs = 0
            affected_users: set[str] = set()
            overlap_seconds = 0.0
            for other, other_waits in by_user.items():
                if other == user:
                    continue
                for job_wait in other_waits:
                    shared = _overlap(job_wait, my_exec)
                    if shared > 0:
                        overlap_seconds += shared
                        affected_jobs += 1
                        affected_users.add(other)
            impact.others_wait_overlap_hours += overlap_seconds / 3600.0
            impact.others_jobs_affected += affected_jobs
            impact.others_users_affected = max(impact.others_users_affected, len(affected_users))

        wait_total_seconds += sum(i.seconds for items in by_user.values() for i in items)

    for user, impact in impacts.items():
        impact.jobs = per_user_jobs.get(user, 0)
        stamps = per_user_times.get(user, [])
        (
            impact.max_burst,
            impact.burst_count,
            impact.median_gap_seconds,
            impact.sub_second_gaps,
        ) = _bursts(stamps)
        impact.containers = containers.get(user, 0)
        if user_map is not None:
            impact.label = user_map.label(user)
        impact.blocking_share = (
            impact.others_wait_overlap_hours * 3600.0 / wait_total_seconds
            if wait_total_seconds
            else 0.0
        )

    return sorted(impacts.values(), key=lambda i: i.others_wait_overlap_hours, reverse=True)
