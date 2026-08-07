"""Permission probe.

Establishes what this key can actually reach. Two answers decide everything else:

  1) can other users' jobs be read via ``GET /v1/jobs/{id}`` (200 or 403)?
  2) does that response include ``params`` — the circuit?

The ``/v1/analytics/*`` endpoints being admin-only is expected and harmless; nothing
else depends on them.
"""

from __future__ import annotations

from typing import Any

from .client import RuntimeClient
from .config import Settings

CHECKS = [
    ("Instance info", "/v1/instance", None),
    ("Instance usage", "/v1/instances/usage", None),
    ("Instance limits", "/v1/instances/configuration", None),
    ("Backend list", "/v1/backends", None),
    ("Workloads (whole instance)", "/v1/workloads", {"limit": 20}),
    ("Workloads (mine only)", "/v1/workloads", {"limit": 5, "user": "me"}),
    ("My jobs", "/v1/jobs", {"limit": 5, "exclude_params": "true"}),
    ("Admin: analytics filters", "/v1/analytics/filters", None),
    ("Admin: usage by user", "/v1/analytics/usage_grouped", {"group_by": "user_id"}),
]

OK = "  OK  "
NO = " FAIL "


def _line(status: str, name: str, detail: str = "") -> str:
    return f"[{status}] {name:<30} {detail}"


def run_probe(settings: Settings) -> dict[str, Any]:
    """Probe every configured instance. Permissions can differ between them."""
    settings.ensure_credentials()
    results: dict[str, Any] = {}
    for instance in settings.instances:
        results[instance.name] = _probe_one(settings.for_instance(instance), instance.name)
    return results


def _probe_one(settings: Settings, instance_name: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    print("=" * 82)
    print(f"qpu-audit permission probe — instance: {instance_name}")
    print(f"  base_url : {settings.base_url}")
    print(f"  CRN      : {settings.crn[:60]}{'...' if len(settings.crn) > 60 else ''}")
    print(f"  auth     : {settings.auth_mode}")
    print("=" * 82)

    with RuntimeClient(settings) as client:
        results: dict[str, Any] = {}
        for name, path, params in CHECKS:
            result = client.probe(path, params)
            results[path + str(params)] = result
            detail = "" if result.ok else f"HTTP {result.status} {result.detail[:80]}"
            print(_line(OK if result.ok else NO, name, detail))
            summary[name] = {"ok": result.ok, "status": result.status}

        print("-" * 82)

        # -- identify myself ------------------------------------------------
        me_result = results.get("/v1/workloads" + str({"limit": 5, "user": "me"}))
        my_ids = _user_ids(me_result.payload if me_result and me_result.ok else None)
        my_id = next(iter(my_ids), None)
        if my_id:
            print(_line(OK, "My user_id", my_id))
        else:
            print(_line(NO, "My user_id", "not determined (you may have run no jobs)"))
        summary["my_user_id"] = my_id

        # -- is the whole instance visible? ---------------------------------
        all_result = results.get("/v1/workloads" + str({"limit": 20}))
        all_payload = all_result.payload if all_result and all_result.ok else None
        all_ids = _user_ids(all_payload)
        others = [uid for uid in all_ids if uid != my_id]
        if others:
            print(_line(OK, "Other users' workloads", f"{len(all_ids)} users seen ({len(others)} besides me)"))
        elif all_ids:
            print(_line(NO, "Other users' workloads", "only my own — instance-wide listing unavailable"))
        else:
            print(_line(NO, "Other users' workloads", "no workloads returned"))
        summary["other_users_visible"] = bool(others)
        summary["observed_users"] = len(all_ids)

        # -- job detail and circuit access ----------------------------------
        target = _pick_job(all_payload, exclude_user=my_id)
        if target is None:
            target = _pick_job(all_payload, exclude_user=None)
            scope = "my own job"
        else:
            scope = "another user's job"

        if target is None:
            print(_line(NO, "Job detail", "no job available to test"))
            summary["job_detail"] = None
        else:
            detail = client.probe(f"/v1/jobs/{target['id']}")
            if detail.ok:
                params_present = bool((detail.payload or {}).get("params"))
                print(_line(OK, f"Job detail ({scope})", f"id={target['id']}"))
                print(
                    _line(
                        OK if params_present else NO,
                        "  circuit (params) present",
                        "yes — circuit fingerprinting available"
                        if params_present
                        else "no — private job or restricted access",
                    )
                )
                summary["job_detail"] = {"scope": scope, "status": 200, "params": params_present}
            else:
                print(_line(NO, f"Job detail ({scope})", f"HTTP {detail.status} {detail.detail[:70]}"))
                summary["job_detail"] = {"scope": scope, "status": detail.status, "params": False}

        # -- does analytics expose names? -----------------------------------
        filters = results.get("/v1/analytics/filters" + str(None))
        if filters and filters.ok:
            users = (filters.payload or {}).get("users") or []
            keys = sorted({k for u in users if isinstance(u, dict) for k in u})
            print(_line(OK, "analytics users fields", f"{len(users)} users, fields={keys or 'none'}"))
            has_name = any(k in keys for k in ("name", "email", "label", "username"))
            print(
                _line(
                    OK if has_name else NO,
                    "  real names provided",
                    "yes" if has_name else "no — IDs only, see docs/user-mapping.md",
                )
            )
            summary["analytics_user_fields"] = keys

    print("=" * 82)
    _conclude(summary)
    return summary


def _user_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    out: list[str] = []
    for item in payload.get("workloads") or []:
        uid = item.get("user_id")
        if uid and uid not in out:
            out.append(uid)
    return out


def _pick_job(payload: Any, exclude_user: str | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    for item in payload.get("workloads") or []:
        if item.get("mode") != "job":
            continue
        if exclude_user and item.get("user_id") == exclude_user:
            continue
        return item
    return None


def _conclude(summary: dict[str, Any]) -> None:
    print("Conclusion")
    detail = summary.get("job_detail") or {}
    if summary.get("other_users_visible") and detail.get("params"):
        print("  OK   Instance-wide workloads and circuits are available.")
        print("       Circuit-fingerprint detection is fully enabled.")
    elif summary.get("other_users_visible"):
        print("  !    Other users' workloads are visible but no circuit was returned.")
        print("       Try a collect run; if it stays blocked, detection falls back to")
        print("       behavioural signals only.")
    else:
        print("  X    Instance-wide listing is unavailable. This key can only analyse")
        print("       your own jobs.")

    if summary.get("Admin: usage by user", {}).get("ok"):
        print("  OK   Analytics available — usable for cross-checking per-user totals.")
    else:
        print("  -    Analytics is admin-only and unavailable. Everything else still works.")

    if summary.get("Instance limits", {}).get("ok"):
        print("  OK   Instance limits readable — quota consumption can be reported.")
    print("=" * 82)
