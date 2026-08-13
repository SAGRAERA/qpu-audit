"""Incremental collector.

  1) GET /v1/workloads  — every workload on the instance (user, usage, status)
  2) GET /v1/jobs/{id}  — per-job detail, where the circuit lives in ``params``
  3) GET /v1/jobs/{id}/metrics — optional: client version and actual QPU time

Step 2 is the only way to obtain circuits and costs one call per job, so a job is
never fetched twice; only unfinished jobs are re-queued for refresh.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .client import AccessDenied, NotFound, RuntimeClient
from .config import Settings
from .fingerprint import fingerprint_params, fingerprint_payload
from .store import Store

log = logging.getLogger(__name__)

WATERMARK_KEY = "workloads_watermark"

# Deliberate overlap. Upserts make duplicates harmless; missing a boundary item is
# considerably worse.
OVERLAP = timedelta(minutes=30)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class Collector:
    def __init__(
        self,
        settings: Settings,
        client: RuntimeClient,
        store: Store,
        instance_name: str = "",
    ) -> None:
        self.settings = settings
        self.client = client
        self.store = store
        self.cfg = settings.section("collect")
        # Each instance keeps its own watermark; they are collected independently
        # and may be added at different times.
        self.instance_name = instance_name
        self.watermark_key = (
            f"{WATERMARK_KEY}:{instance_name}" if instance_name else WATERMARK_KEY
        )

    # -- stage 1: workload listing -----------------------------------------
    def sync_workloads(self, full: bool = False) -> dict[str, int]:
        now = _utcnow()
        page_size = int(self.cfg.get("page_size", 200))

        created_after: str | None = None
        if not full:
            mark = self.store.get_meta(self.watermark_key)
            if mark:
                base = _parse_ts(mark)
                if base:
                    created_after = (base - OVERLAP).isoformat().replace("+00:00", "Z")
        if created_after is None:
            days = int(self.cfg.get("lookback_days", 30))
            created_after = (
                datetime.now(timezone.utc) - timedelta(days=days)
            ).isoformat(timespec="seconds").replace("+00:00", "Z")

        where = f" [{self.instance_name}]" if self.instance_name else ""
        log.info("Syncing workloads%s (created_after=%s)", where, created_after)

        new_count = seen = 0
        newest: datetime | None = None
        for item in self.client.iter_workloads(created_after=created_after, limit=page_size):
            if self.store.upsert_workload(item, now):
                new_count += 1
            seen += 1
            ts = _parse_ts(item.get("created"))
            if ts and (newest is None or ts > newest):
                newest = ts
            if seen % 200 == 0:
                self.store.conn.commit()
                log.info("  ...%d processed", seen)
        self.store.conn.commit()

        # Still-running workloads can fall outside the created_after window.
        active = 0
        for status in ("pending", "in_progress"):
            for item in self.client.iter_workloads(status=[status], limit=page_size):
                self.store.upsert_workload(item, now)
                active += 1
        self.store.conn.commit()

        if newest:
            self.store.set_meta(self.watermark_key, newest.isoformat().replace("+00:00", "Z"))

        log.info("%d workloads seen (%d new), %d active refreshed", seen, new_count, active)
        return {"seen": seen, "new": new_count, "active_refreshed": active}

    # -- stage 2: job detail and circuit fingerprints ----------------------
    def sync_job_details(self, limit: int | None = None, with_metrics: bool = False) -> dict[str, int]:
        budget = limit if limit is not None else int(self.cfg.get("job_detail_max_per_run", 500))
        pending = self.store.jobs_needing_detail(budget)
        seen: set[str] = set(pending)

        # Collected by an older version: detail present, raw payload missing.
        # Payloads are what make reindexing possible.
        remaining = max(budget - len(pending), 0)
        backfill = [
            j for j in self.store.jobs_missing_payloads(remaining) if j not in seen
        ] if remaining else []
        seen.update(backfill)

        # Spend whatever budget is left refreshing unfinished jobs, whose usage is
        # finalised later.
        remaining = max(budget - len(pending) - len(backfill), 0)
        refresh = [
            j for j in self.store.jobs_needing_refresh(remaining) if j not in seen
        ] if remaining else []
        targets = pending + backfill + refresh

        if not targets:
            log.info("No job details to fetch.")
            return {"fetched": 0, "with_circuit": 0, "denied": 0, "missing": 0, "failed": 0}

        log.info(
            "Fetching %d job details (new %d, payload backfill %d, refresh %d)",
            len(targets), len(pending), len(backfill), len(refresh),
        )

        stats = {"fetched": 0, "with_circuit": 0, "denied": 0, "missing": 0, "failed": 0}
        now = _utcnow()

        for index, job_id in enumerate(targets, start=1):
            try:
                job = self.client.job(job_id)
            except AccessDenied as exc:
                self.store.record_detail_error(job_id, "denied", str(exc), now)
                stats["denied"] += 1
                continue
            except NotFound:
                self.store.record_detail_error(job_id, "missing", "404 (possibly aged out)", now)
                stats["missing"] += 1
                continue
            except Exception as exc:  # noqa: BLE001 - one failure must not stop the run
                self.store.record_detail_error(job_id, "error", f"{type(exc).__name__}: {exc}", now)
                stats["failed"] += 1
                continue

            params = job.get("params")
            pubs = fingerprint_params(params, keep_payload=True)
            self.store.upsert_job_detail(job, pubs, params_available=bool(params), now=now)
            stats["fetched"] += 1
            if pubs:
                stats["with_circuit"] += 1

            if with_metrics:
                try:
                    metrics = self.client.job_metrics(job_id)
                    self.store.update_metrics(
                        job_id, metrics.get("caller"), metrics.get("circuits_execution_time_ns")
                    )
                except Exception:  # noqa: BLE001 - metrics are supplementary
                    pass

            if index % 50 == 0:
                log.info("  ...%d/%d", index, len(targets))

        log.info(
            "Detail fetch complete: %d ok (%d with circuits), %d denied, %d missing, %d failed",
            stats["fetched"], stats["with_circuit"], stats["denied"],
            stats["missing"], stats["failed"],
        )
        return stats

    # -- optional: admin-only analytics ------------------------------------
    def fetch_admin_analytics(self, days: int = 30) -> dict[str, Any] | None:
        """Per-user aggregates, when permitted. Returns None otherwise."""
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            return self.client.analytics_usage_grouped(
                "user_id", interval_start=start, interval_end=end
            )
        except AccessDenied:
            log.info("Analytics endpoints are admin-only and not available. Skipping.")
            return None
        except Exception as exc:  # noqa: BLE001
            log.warning("Analytics request failed: %s", exc)
            return None


def run_reindex(settings: Settings) -> dict[str, Any]:
    """Recompute fingerprints from stored QPY payloads. Makes no API calls.

    This is what makes changing fingerprint rules cheap — no re-fetching thousands
    of jobs.
    """
    import json as _json

    with Store(settings.db_path) as store:
        total = store.payload_count()
        if not total:
            log.warning("No stored payloads. Run `collect` first.")
            return {"total": 0, "reindexed": 0, "failed": 0}

        log.info("Reindexing %d pubs", total)
        store.reset_derived()
        now = _utcnow()
        done = failed = 0

        for row in store.iter_payloads():
            try:
                vector = _json.loads(row["param_vector"] or "[]")
            except ValueError:
                vector = []
            try:
                pub = fingerprint_payload(
                    row["pub_index"],
                    row["payload"],
                    row["shots"],
                    vector,
                    row["param_sig"] or "",
                    row["observable_sig"] or "",
                )
                store.write_pub(row["job_id"], pub, now)
                done += 1
            except Exception as exc:  # noqa: BLE001 - one failure must not stop the run
                failed += 1
                log.debug("Reindex failed for %s[%s]: %s", row["job_id"], row["pub_index"], exc)
            if done % 500 == 0 and done:
                store.conn.commit()
                log.info("  ...%d/%d", done, total)

        store.conn.commit()
        log.info("Reindex complete: %d done (%d failed)", done, failed)
        return {"total": total, "reindexed": done, "failed": failed}


def run_collect(
    settings: Settings,
    full: bool = False,
    detail_limit: int | None = None,
    with_metrics: bool = False,
    skip_details: bool = False,
    refetch: bool = False,
    only_instance: str | None = None,
) -> dict[str, Any]:
    """Collect every configured instance in turn.

    The detail budget is applied **per instance**. Sharing one budget across all of
    them lets a busy instance consume it entirely, leaving the others permanently
    unfetched.
    """
    settings.ensure_credentials()

    targets = settings.instances
    if only_instance:
        targets = [i for i in targets if i.name == only_instance or i.crn == only_instance]
        if not targets:
            names = ", ".join(i.name for i in settings.instances)
            raise ValueError(f"Unknown instance {only_instance!r}. Configured: {names}")

    result: dict[str, Any] = {"instances": {}}
    with Store(settings.db_path) as store:
        if refetch:
            cleared = store.clear_details()
            log.info("Marked %d job details for re-fetching", cleared)

        for instance in targets:
            if len(targets) > 1:
                log.info("=== instance: %s ===", instance.name)
            with RuntimeClient(settings.for_instance(instance)) as client:
                collector = Collector(settings, client, store, instance.name)
                per: dict[str, Any] = {"workloads": collector.sync_workloads(full=full)}
                if not skip_details:
                    per["details"] = collector.sync_job_details(detail_limit, with_metrics)
                result["instances"][instance.name] = per

        # Update the monthly ledger. It outlives IBM's retention of the workloads.
        from . import usage as usage_module

        entries = usage_module.compute_monthly(store)
        usage_module.persist(store, entries)
        usage_module.persist_by_instance(store, usage_module.compute_monthly_by_instance(store))
        usage_module.persist_by_backend(store, usage_module.compute_monthly_by_backend(store))
        result["monthly_rows"] = len(entries)

        result["totals"] = store.counts()
        return result
