"""Monthly usage ledger.

IBM does not retain workloads indefinitely, so aggregates are accumulated into a
local table. Once the originals are gone, "who used how much in which month" remains.

The ledger is refreshed on every ``collect``. Past months are settled and safe to
overwrite; the current month is updated each run.
"""

from __future__ import annotations

import calendar
import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class MonthChange:
    """Month-over-month change. A partial month is scaled to a full-month estimate."""

    previous_seconds: float
    current_seconds: float
    ratio: float
    prorated: bool = False
    projected_seconds: float = 0.0

    @property
    def is_new(self) -> bool:
        return self.ratio == float("inf")

    @property
    def label(self) -> str:
        if self.is_new:
            return "new"
        return f"{self.ratio:.1f}x" + (" (est.)" if self.prorated else "")


@dataclass
class MonthlyUsage:
    month: str          # YYYY-MM
    user_id: str
    jobs: int = 0
    qpu_seconds: float = 0.0
    backends: int = 0
    first_seen: str = ""
    last_seen: str = ""

    @property
    def hours(self) -> float:
        return self.qpu_seconds / 3600.0


@dataclass
class UsageLedger:
    months: list[str] = field(default_factory=list)          # oldest first
    users: list[str] = field(default_factory=list)           # heaviest first
    cells: dict[tuple[str, str], MonthlyUsage] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)

    def get(self, month: str, user_id: str) -> MonthlyUsage | None:
        return self.cells.get((month, user_id))

    def seconds(self, month: str, user_id: str) -> float:
        cell = self.get(month, user_id)
        return cell.qpu_seconds if cell else 0.0

    def user_total(self, user_id: str) -> float:
        return sum(self.seconds(m, user_id) for m in self.months)

    def month_total(self, month: str) -> float:
        return sum(self.seconds(month, u) for u in self.users)

    def grand_total(self) -> float:
        return sum(self.month_total(m) for m in self.months)

    @property
    def latest_is_partial(self) -> bool:
        return bool(self.months) and self.months[-1] == current_month()

    def change(self, user_id: str, floor_seconds: float = 60.0) -> MonthChange | None:
        """Month-over-month change, or None when there is nothing meaningful to compare.

        Comparing a month in progress against a completed one reports everybody as
        collapsing during the first days of a month, so the partial month is scaled
        to a projected total and marked as an estimate.
        """
        if len(self.months) < 2:
            return None
        latest, previous = self.months[-1], self.months[-2]
        current = self.seconds(latest, user_id)
        before = self.seconds(previous, user_id)

        prorated = False
        projected = current
        if self.latest_is_partial:
            factor = month_progress_factor()
            if factor > 1.0:
                projected = current * factor
                prorated = True

        # "10x growth" over a few seconds of usage is noise.
        if max(projected, before) < floor_seconds:
            return None
        if before <= 0:
            if projected <= 0:
                return None
            return MonthChange(before, current, float("inf"), prorated, projected)
        return MonthChange(before, current, projected / before, prorated, projected)


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def month_progress_factor(now: datetime | None = None) -> float:
    """Multiplier that scales the current month to a full-month estimate."""
    now = now or datetime.now(timezone.utc)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    elapsed = now.day - 1 + now.hour / 24.0
    return days_in_month / max(elapsed, 0.5)


def compute_monthly(store: Any) -> list[MonthlyUsage]:
    """Aggregate workloads by user and month."""
    rows = store.query(
        """
        SELECT substr(created, 1, 7)            AS month,
               user_id,
               COUNT(*)                         AS jobs,
               SUM(COALESCE(usage_seconds, 0))  AS qpu_seconds,
               COUNT(DISTINCT backend)          AS backends,
               MIN(created)                     AS first_seen,
               MAX(created)                     AS last_seen
        FROM workloads
        WHERE mode = 'job' AND user_id IS NOT NULL AND created IS NOT NULL
        GROUP BY month, user_id
        """
    )
    return [
        MonthlyUsage(
            month=row["month"],
            user_id=row["user_id"],
            jobs=int(row["jobs"] or 0),
            qpu_seconds=float(row["qpu_seconds"] or 0.0),
            backends=int(row["backends"] or 0),
            first_seen=row["first_seen"] or "",
            last_seen=row["last_seen"] or "",
        )
        for row in rows
        if row["month"]
    ]


@dataclass
class InstanceUsage:
    """Usage for one (month, user, instance)."""

    month: str
    user_id: str
    instance: str
    jobs: int = 0
    qpu_seconds: float = 0.0


def compute_monthly_by_instance(store: Any) -> list[InstanceUsage]:
    rows = store.query(
        """
        SELECT substr(created, 1, 7)            AS month,
               user_id,
               instance,
               COUNT(*)                         AS jobs,
               SUM(COALESCE(usage_seconds, 0))  AS qpu_seconds
        FROM workloads
        WHERE mode = 'job' AND user_id IS NOT NULL AND created IS NOT NULL
          AND instance IS NOT NULL
        GROUP BY month, user_id, instance
        """
    )
    return [
        InstanceUsage(
            month=row["month"],
            user_id=row["user_id"],
            instance=row["instance"],
            jobs=int(row["jobs"] or 0),
            qpu_seconds=float(row["qpu_seconds"] or 0.0),
        )
        for row in rows
        if row["month"]
    ]


def persist_by_instance(store: Any, entries: list[InstanceUsage]) -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with store.tx() as conn:
        for entry in entries:
            conn.execute(
                """
                INSERT INTO usage_monthly_instance
                    (month, user_id, instance, jobs, qpu_seconds, updated_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(month, user_id, instance) DO UPDATE SET
                    jobs        = excluded.jobs,
                    qpu_seconds = excluded.qpu_seconds,
                    updated_at  = excluded.updated_at
                """,
                (entry.month, entry.user_id, entry.instance, entry.jobs,
                 entry.qpu_seconds, now),
            )
    return len(entries)


@dataclass
class InstanceBreakdown:
    """Usage per user per instance, plus totals in both directions.

    Both views are needed. Per-instance numbers reveal someone monopolising one
    instance; the totals column reveals someone spread thinly across all of them who
    nevertheless dominates the account.
    """

    instances: list[str] = field(default_factory=list)   # CRNs, heaviest first
    users: list[str] = field(default_factory=list)       # heaviest first
    cells: dict[tuple[str, str], float] = field(default_factory=dict)  # (user, crn) -> seconds
    labels: dict[str, str] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)  # CRN -> friendly name

    def seconds(self, user_id: str, instance: str) -> float:
        return self.cells.get((user_id, instance), 0.0)

    def user_total(self, user_id: str) -> float:
        return sum(self.seconds(user_id, i) for i in self.instances)

    def instance_total(self, instance: str) -> float:
        return sum(self.seconds(u, instance) for u in self.users)

    def grand_total(self) -> float:
        return sum(self.instance_total(i) for i in self.instances)

    def user_share_of(self, user_id: str, instance: str) -> float:
        total = self.instance_total(instance)
        return self.seconds(user_id, instance) / total if total else 0.0

    def instance_name(self, crn: str) -> str:
        if crn in self.names:
            return self.names[crn]
        parts = [p for p in crn.split(":") if p]
        return parts[-1][:12] if parts else crn


def load_breakdown(
    store: Any, months: int = 12, user_map: Any = None, names: dict[str, str] | None = None
) -> InstanceBreakdown:
    """Read the per-instance ledger for the last N months."""
    rows = store.query(
        "SELECT month, user_id, instance, qpu_seconds FROM usage_monthly_instance ORDER BY month"
    )
    breakdown = InstanceBreakdown(names=dict(names or {}))
    all_months = sorted({row["month"] for row in rows})
    keep = set(all_months[-months:]) if months > 0 else set(all_months)

    user_totals: dict[str, float] = {}
    instance_totals: dict[str, float] = {}
    for row in rows:
        if row["month"] not in keep:
            continue
        key = (row["user_id"], row["instance"])
        seconds = float(row["qpu_seconds"] or 0.0)
        breakdown.cells[key] = breakdown.cells.get(key, 0.0) + seconds
        user_totals[row["user_id"]] = user_totals.get(row["user_id"], 0.0) + seconds
        instance_totals[row["instance"]] = instance_totals.get(row["instance"], 0.0) + seconds

    breakdown.instances = sorted(instance_totals, key=lambda i: -instance_totals[i])
    breakdown.users = sorted(user_totals, key=lambda u: -user_totals[u])
    if user_map is not None:
        breakdown.labels = {u: user_map.label(u) for u in breakdown.users}
    return breakdown


def persist(store: Any, entries: list[MonthlyUsage]) -> int:
    """Write to the ledger. Existing (month, user) rows are updated in place."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with store.tx() as conn:
        for entry in entries:
            conn.execute(
                """
                INSERT INTO usage_monthly
                    (month, user_id, jobs, qpu_seconds, backends, first_seen, last_seen, updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(month, user_id) DO UPDATE SET
                    jobs        = excluded.jobs,
                    qpu_seconds = excluded.qpu_seconds,
                    backends    = excluded.backends,
                    last_seen   = excluded.last_seen,
                    updated_at  = excluded.updated_at
                """,
                (
                    entry.month, entry.user_id, entry.jobs, entry.qpu_seconds,
                    entry.backends, entry.first_seen, entry.last_seen, now,
                ),
            )
    return len(entries)


def load_ledger(store: Any, months: int = 12, user_map: Any = None) -> UsageLedger:
    """Read the last N months from the ledger, which survives IBM deleting originals."""
    rows = store.query(
        """
        SELECT month, user_id, jobs, qpu_seconds, backends, first_seen, last_seen
        FROM usage_monthly ORDER BY month
        """
    )
    ledger = UsageLedger()
    all_months = sorted({row["month"] for row in rows})
    keep = set(all_months[-months:]) if months > 0 else set(all_months)

    totals: dict[str, float] = {}
    for row in rows:
        if row["month"] not in keep:
            continue
        entry = MonthlyUsage(
            month=row["month"],
            user_id=row["user_id"],
            jobs=int(row["jobs"] or 0),
            qpu_seconds=float(row["qpu_seconds"] or 0.0),
            backends=int(row["backends"] or 0),
            first_seen=row["first_seen"] or "",
            last_seen=row["last_seen"] or "",
        )
        ledger.cells[(entry.month, entry.user_id)] = entry
        totals[entry.user_id] = totals.get(entry.user_id, 0.0) + entry.qpu_seconds

    ledger.months = sorted(keep)
    ledger.users = sorted(totals, key=lambda u: -totals[u])
    if user_map is not None:
        ledger.labels = {u: user_map.label(u) for u in ledger.users}
    return ledger


def write_csv(ledger: UsageLedger, path: Path) -> Path:
    """Monthly usage as a spreadsheet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["user_id", "label"] + ledger.months + ["total_hours"])
        for user in ledger.users:
            row: list[Any] = [user, ledger.labels.get(user, "")]
            for month in ledger.months:
                row.append(round(ledger.seconds(month, user) / 3600.0, 3))
            row.append(round(ledger.user_total(user) / 3600.0, 3))
            writer.writerow(row)
        writer.writerow(
            ["", "month_total_hours"]
            + [round(ledger.month_total(m) / 3600.0, 3) for m in ledger.months]
            + [round(ledger.grand_total() / 3600.0, 3)]
        )
    return path
