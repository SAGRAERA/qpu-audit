"""Command line entry point.

  python -m qpu_audit probe                 check what this key can reach (start here)
  python -m qpu_audit collect               incremental workload + circuit sync
  python -m qpu_audit analyze               console summary
  python -m qpu_audit report                HTML report
  python -m qpu_audit usage                 monthly usage ledger
  python -m qpu_audit users --sync          resolve user IDs to real names
  python -m qpu_audit status                local database state
  python -m qpu_audit selftest              detection checks, no credentials needed
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import usermap
from .config import ConfigError, load_settings
from .report import default_report_path, write_csv, write_report
from .rules import analyze as run_analysis
from .store import Store


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _fmt_seconds(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.1f}h"
    if seconds >= 60:
        return f"{seconds / 60:.1f}m"
    return f"{seconds:.1f}s"


def cmd_probe(args: argparse.Namespace) -> int:
    from .probe import run_probe

    run_probe(load_settings())
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    from .collect import run_collect

    settings = load_settings()
    result = run_collect(
        settings,
        full=args.full,
        detail_limit=args.detail_limit,
        with_metrics=args.with_metrics,
        skip_details=args.no_details,
        refetch=args.refetch,
        only_instance=args.instance,
    )
    totals = result["totals"]
    print()
    if len(result.get("instances", {})) > 1:
        print("Per instance:")
        for name, per in result["instances"].items():
            workloads = per.get("workloads", {})
            details = per.get("details", {})
            print(
                f"  {name:<20} {workloads.get('seen', 0):>6} workloads "
                f"({workloads.get('new', 0)} new) · "
                f"{details.get('fetched', 0)} details fetched"
            )
    print(f"Local database: {settings.db_path}")
    print(
        f"  {totals['workloads']:,} workloads · {totals['jobs']:,} job details · "
        f"{totals['circuits']:,} circuits · {totals['users']} users"
    )
    if totals["detail_errors"]:
        print(
            f"  {totals['detail_errors']} detail fetches failed (permission or retention). "
            "See `status`."
        )
    return 0


def cmd_usage(args: argparse.Namespace) -> int:
    from . import usage as usage_module

    settings = load_settings()
    store = Store(settings.db_path)
    try:
        # Refresh both ledgers from current workloads, then read them back.
        entries = usage_module.compute_monthly(store)
        usage_module.persist(store, entries)
        usage_module.persist_by_instance(store, usage_module.compute_monthly_by_instance(store))

        umap = usermap.load(settings.user_map_path)

        if args.by_instance:
            breakdown = usage_module.load_breakdown(
                store, args.months, umap, settings.instance_names
            )
            if not breakdown.instances:
                print("No per-instance usage recorded yet. Run `collect` first.")
                return 0
            width = min(max((len(breakdown.labels.get(u, u)) for u in breakdown.users), default=10), 24)
            names = [breakdown.instance_name(c) for c in breakdown.instances]
            header = f"{'user':<{width}}" + "".join(f"{n[:13]:>14}" for n in names) + f"{'total':>12}"
            print(f"\nQPU hours by instance · {len(breakdown.instances)} instances")
            print(header)
            print("-" * len(header))
            for user in breakdown.users:
                line = f"{breakdown.labels.get(user, user)[:width]:<{width}}"
                for crn in breakdown.instances:
                    seconds = breakdown.seconds(user, crn)
                    if seconds:
                        share = breakdown.user_share_of(user, crn) * 100
                        line += f"{seconds / 3600:>9.2f}({share:>3.0f}%)"
                    else:
                        line += f"{'—':>14}"
                line += f"{breakdown.user_total(user) / 3600:>12.2f}"
                print(line)
            print("-" * len(header))
            total_line = f"{'instance total':<{width}}"
            for crn in breakdown.instances:
                total_line += f"{breakdown.instance_total(crn) / 3600:>14.2f}"
            total_line += f"{breakdown.grand_total() / 3600:>12.2f}"
            print(total_line + "\n")
            return 0

        ledger = usage_module.load_ledger(store, args.months, umap)
        if not ledger.months:
            print("No usage recorded yet. Run `collect` first.")
            return 0

        width = max((len(ledger.labels.get(u, u)) for u in ledger.users), default=10)
        width = min(max(width, 10), 24)
        header = (
            f"{'user':<{width}}" + "".join(f"{m:>11}" for m in ledger.months) + f"{'total':>11}"
        )
        print(
            f"\nMonthly QPU usage (hours) · {len(ledger.months)} months · "
            f"{len(ledger.users)} users"
        )
        print(header)
        print("-" * len(header))
        for user in ledger.users:
            label = ledger.labels.get(user, user)[:width]
            line = f"{label:<{width}}"
            for month in ledger.months:
                seconds = ledger.seconds(month, user)
                line += f"{seconds / 3600:>11.2f}" if seconds else f"{'—':>11}"
            line += f"{ledger.user_total(user) / 3600:>11.2f}"
            print(line)
        print("-" * len(header))
        total_line = f"{'month total':<{width}}"
        for month in ledger.months:
            total_line += f"{ledger.month_total(month) / 3600:>11.2f}"
        total_line += f"{ledger.grand_total() / 3600:>11.2f}"
        print(total_line)

        if ledger.latest_is_partial:
            print(
                f"\nNote: {ledger.months[-1]} is still in progress "
                "(comparisons use a full-month estimate)."
            )

        if len(ledger.months) >= 2:
            latest, previous = ledger.months[-1], ledger.months[-2]
            notable = [
                (user, change)
                for user in ledger.users
                if (change := ledger.change(user))
                and (change.ratio >= 1.5 or change.ratio <= 0.67)
            ]
            if notable:
                print(f"\n{previous} -> {latest} change (1.5x or more, either way)")
                for user, change in notable[:12]:
                    mark = "up  " if change.ratio > 1 else "down"
                    projected = (
                        f" -> {change.projected_seconds / 3600:.2f}h projected"
                        if change.prorated else ""
                    )
                    print(
                        f"  {ledger.labels.get(user, user)[:24]:<24} "
                        f"{change.previous_seconds / 3600:>7.2f}h -> "
                        f"{change.current_seconds / 3600:>7.2f}h  "
                        f"{mark} {change.label}{projected}"
                    )
        print()

        if args.csv:
            path = usage_module.write_csv(ledger, settings.reports_dir / "usage-monthly.csv")
            print(f"CSV: {path}")
    finally:
        store.close()
    return 0


def cmd_reindex(args: argparse.Namespace) -> int:
    from .collect import run_reindex

    settings = load_settings()
    result = run_reindex(settings)
    if result["total"]:
        print(f"\nReindexed {result['reindexed']:,} pubs ({result['failed']} failed)")
    return 0


def _load_analysis(settings):
    store = Store(settings.db_path)
    umap = usermap.load(settings.user_map_path)
    return store, run_analysis(store, settings, umap)


def cmd_analyze(args: argparse.Namespace) -> int:
    settings = load_settings()
    store, analysis = _load_analysis(settings)
    try:
        print(
            f"\nLast {analysis.window_days} days · {analysis.total_jobs:,} jobs · "
            f"{_fmt_seconds(analysis.total_seconds)} QPU · "
            f"{analysis.coverage * 100:.0f}% circuits retrieved"
        )
        for note in analysis.notes:
            print(f"  ! {note}")
        print()
        header = (
            f"{'score':>6}  {'user':<22} {'jobs':>6} {'QPU':>9} {'share':>7} "
            f"{'unexplained':>12} {'unique':>7}"
        )
        print(header)
        print("-" * len(header))
        for user in analysis.users[: args.top]:
            print(
                f"{user.score:6.0f}  {user.label[:22]:<22} {user.jobs:6d} "
                f"{_fmt_seconds(user.seconds):>9} {user.instance_share * 100:6.1f}% "
                f"{_fmt_seconds(user.flagged_waste_seconds):>12} {user.unique_ratio * 100:6.0f}%"
            )
            for finding in user.findings[:3]:
                print(f"          - {finding}")
        print()

        if not args.no_queue:
            from .queueimpact import analyze_queue

            impacts = analyze_queue(store, analysis.window_days)
            print("Queue impact (how much others were delayed)")
            header = (
                f"{'user':<22} {'jobs':>6} {'QPU held':>10} {'delay caused':>13} "
                f"{'share':>7} {'max burst':>10} {'median gap':>11} {'containers':>11}"
            )
            print(header)
            print("-" * len(header))
            for impact in impacts[: args.top]:
                gap = (
                    "—" if impact.median_gap_seconds is None
                    else f"{impact.median_gap_seconds:.1f}s"
                )
                print(
                    f"{impact.user_id[:22]:<22} {impact.jobs:6d} "
                    f"{impact.qpu_hours:9.2f}h "
                    f"{impact.others_wait_overlap_hours:12.1f}h "
                    f"{impact.blocking_share * 100:6.1f}% "
                    f"{impact.max_burst:10d} {gap:>11} {impact.containers:11d}"
                )
            print()
    finally:
        store.close()
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    settings = load_settings()
    store, analysis = _load_analysis(settings)
    try:
        out = Path(args.out) if args.out else default_report_path(settings.root)
        write_report(analysis, store, out, settings.section("report"))
        print(f"Report: {out}")
        if args.csv:
            csv_path = out.with_suffix(".csv")
            write_csv(analysis, csv_path)
            print(f"CSV   : {csv_path}")
    finally:
        store.close()
    return 0


def cmd_users(args: argparse.Namespace) -> int:
    settings = load_settings()
    store = Store(settings.db_path)
    try:
        rows = store.query(
            """
            SELECT user_id,
                   COUNT(*)                       AS jobs,
                   COALESCE(SUM(usage_seconds),0) AS seconds,
                   MIN(created)                   AS first_seen,
                   MAX(created)                   AS last_seen
            FROM workloads
            WHERE user_id IS NOT NULL
            GROUP BY user_id
            ORDER BY seconds DESC
            """
        )
        umap = usermap.load(settings.user_map_path)
        print(f"\n{'user_id':<28} {'label':<20} {'jobs':>6} {'QPU':>9}  last active")
        print("-" * 92)
        for row in rows:
            label = umap.entries.get(row["user_id"], ("", ""))[0] or "(unmapped)"
            print(
                f"{row['user_id']:<28} {label:<20} {row['jobs']:6d} "
                f"{_fmt_seconds(row['seconds']):>9}  {row['last_seen'] or '—'}"
            )
        print()

        resolved: dict[str, tuple[str, str]] = {}
        if args.sync:
            from .accounts import AccountLookupError, fetch_account_users

            try:
                account_users = fetch_account_users(settings)
            except AccountLookupError as exc:
                print(f"[account lookup failed] {exc}\n")
                account_users = []

            observed = {r["user_id"] for r in rows}
            resolved = {
                u.iam_id: (u.display_name, u.email)
                for u in account_users
                if u.iam_id in observed
            }
            print(
                f"Fetched {len(account_users)} user(s) from the IBM Cloud account; "
                f"{len(resolved)} matched users seen on this instance."
            )
            if account_users and len(resolved) < len(observed):
                print(
                    f"  ! {len(observed) - len(resolved)} of {len(observed)} observed users are "
                    "missing from the account listing."
                )
                print(
                    "    Either the account restricts user visibility, or the key lacks the "
                    "User Management Viewer role. See docs/user-mapping.md."
                )
            print()

        if args.export or args.sync:
            count, filled = usermap.export_template(
                settings.user_map_path, [r["user_id"] for r in rows], umap, resolved
            )
            print(f"Wrote {count} rows ({filled} filled automatically): {settings.user_map_path}")
            print("Fill in the rest by hand. See docs/user-mapping.md")
    finally:
        store.close()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    settings = load_settings()
    print(f"Project : {settings.root}")
    print(f"Database: {settings.db_path}")
    print(
        f"Creds   : API key {'set' if settings.api_key else 'missing'} / "
        f"CRN {'set' if settings.crn else 'missing'}"
    )
    if not settings.db_path.exists():
        print("\nNo database yet. Run `python -m qpu_audit collect` first.")
        return 0
    store = Store(settings.db_path)
    try:
        totals = store.counts()
        print(
            f"\n{totals['workloads']:,} workloads · {totals['jobs']:,} job details · "
            f"{totals['pubs']:,} pubs · {totals['circuits']:,} circuits · "
            f"{totals['users']} users"
        )
        errors = store.query(
            "SELECT status, COUNT(*) AS n FROM detail_errors GROUP BY status ORDER BY n DESC"
        )
        if errors:
            print("\nDetail fetch failures:")
            for row in errors:
                meaning = {
                    "denied": "no permission (401/403)",
                    "missing": "not retrievable (404, possibly aged out)",
                    "error": "other error",
                }.get(row["status"], row["status"])
                print(f"  {row['status']:<9} {row['n']:>6}  {meaning}")
        pending = len(store.jobs_needing_detail(10_000))
        print(f"\n{pending:,} job details still queued")
        watermark = store.get_meta("workloads_watermark")
        print(f"Collection watermark: {watermark or '(none)'}")
    finally:
        store.close()
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    from .selftest import run_selftest

    return run_selftest(Path(args.out) if args.out else None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qpu_audit",
        description="Audit QPU usage patterns on an IBM Quantum instance",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("probe", help="check what this API key can reach")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("collect", help="incrementally sync workloads and circuits")
    p.add_argument("--full", action="store_true", help="ignore the watermark, re-read lookback_days")
    p.add_argument("--detail-limit", type=int, default=None, help="job details to fetch this run")
    p.add_argument("--no-details", action="store_true", help="refresh the listing only")
    p.add_argument("--with-metrics", action="store_true", help="also fetch job metrics")
    p.add_argument(
        "--refetch",
        action="store_true",
        help="re-fetch every job detail (use after changing fingerprint rules)",
    )
    p.add_argument(
        "--instance",
        default=None,
        help="collect only this instance (name from config/instances.toml)",
    )
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("usage", help="monthly usage ledger")
    p.add_argument("--months", type=int, default=12, help="months to display (default 12)")
    p.add_argument("--csv", action="store_true", help="also write reports/usage-monthly.csv")
    p.add_argument(
        "--by-instance",
        action="store_true",
        help="break usage down per instance instead of per month",
    )
    p.set_defaults(func=cmd_usage)

    p = sub.add_parser("reindex", help="recompute fingerprints from stored payloads (no API calls)")
    p.set_defaults(func=cmd_reindex)

    p = sub.add_parser("analyze", help="console summary")
    p.add_argument("--top", type=int, default=15, help="users to display")
    p.add_argument("--no-queue", action="store_true", help="skip the queue impact analysis")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("report", help="generate the HTML report")
    p.add_argument("-o", "--out", help="output path (default reports/qpu-audit-<timestamp>.html)")
    p.add_argument("--csv", action="store_true", help="also write a CSV alongside it")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("users", help="list observed user IDs and resolve names")
    p.add_argument("--export", action="store_true", help="write config/user_map.csv")
    p.add_argument(
        "--sync",
        action="store_true",
        help="resolve names from the IBM Cloud account (implies --export)",
    )
    p.set_defaults(func=cmd_users)

    p = sub.add_parser("status", help="local database state")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("selftest", help="run detection checks on synthetic data (no credentials)")
    p.add_argument(
        "-o",
        "--out",
        default=None,
        help="where to write the sample report (default reports/selftest-sample.html)",
    )
    p.set_defaults(func=cmd_selftest)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return int(args.func(args))
    except ConfigError as exc:
        print(f"\n[configuration error] {exc}\n", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
