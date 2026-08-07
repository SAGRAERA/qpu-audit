"""Detection logic checked against synthetic scenarios. No credentials needed.

The point is not to prove that abuse gets caught — that part is easy. It is to prove
that **legitimate research stays unflagged**, which is the failure mode that names
innocent people. Every scenario below that must not fire was added after a real false
positive.
"""

from __future__ import annotations

import random
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import DEFAULTS, PROJECT_ROOT, Settings
from .fingerprint import fingerprint_params
from .report import write_report
from .rules import analyze
from .store import Store
from .usermap import UserMap

BELL = """OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0];
cx q[0], q[1];
measure q[0] -> c[0];
measure q[1] -> c[1];
"""

TRIVIAL = """OPENQASM 3.0;
include "stdgates.inc";
qubit[3] q;
bit[3] c;
h q[0];
x q[1];
h q[2];
measure q[0] -> c[0];
measure q[1] -> c[1];
measure q[2] -> c[2];
"""

ANSATZ = """OPENQASM 3.0;
include "stdgates.inc";
qubit[4] q;
bit[4] c;
ry(0.1) q[0];
ry(0.2) q[1];
cx q[0], q[1];
ry(0.3) q[2];
cx q[1], q[2];
ry(0.4) q[3];
cx q[2], q[3];
measure q[0] -> c[0];
measure q[1] -> c[1];
measure q[2] -> c[2];
measure q[3] -> c[3];
"""


def _qasm_variant(seed: int) -> str:
    """Generate genuinely different circuits."""
    rng = random.Random(seed)
    depth = rng.randint(3, 8)
    lines = ["OPENQASM 3.0;", 'include "stdgates.inc";', "qubit[5] q;", "bit[5] c;"]
    for _ in range(depth):
        gate = rng.choice(["h", "x", "t", "sdg"])
        lines.append(f"{gate} q[{rng.randint(0, 4)}];")
        lines.append(f"cx q[{rng.randint(0, 2)}], q[{rng.randint(3, 4)}];")
    lines += [f"measure q[{i}] -> c[{i}];" for i in range(5)]
    return "\n".join(lines) + "\n"


def _insert(
    store: Store,
    job_id: str,
    user_id: str,
    created: datetime,
    backend: str,
    seconds: float,
    qasm: str,
    param_values: list[float] | None,
    shots: int,
    session_id: str | None = None,
    status: str = "completed",
    observables: dict[str, float] | None = None,
) -> None:
    stamp = created.isoformat(timespec="seconds").replace("+00:00", "Z")
    values = param_values if param_values is not None else []
    if observables is not None:
        # estimator shape: [circuit, observables, parameter_values, precision]
        params = {
            "pubs": [[qasm, observables, values, None]],
            "options": {"default_shots": shots},
            "program_id": "estimator",
        }
    else:
        params = {
            "pubs": [[qasm, values, shots]],
            "options": {"default_shots": shots},
            "program_id": "sampler",
        }
    store.upsert_workload(
        {
            "id": job_id,
            "created": stamp,
            "ended": stamp,
            "backend": backend,
            "instance": "selftest",
            "user_id": user_id,
            "mode": "job",
            "status": status,
            "tags": [],
            "usage": {"qpu_charge_time_seconds": seconds, "status": "complete"},
        },
        stamp,
    )
    store.upsert_job_detail(
        {
            "id": job_id,
            "created": stamp,
            "backend": backend,
            "user_id": user_id,
            "session_id": session_id,
            "program": {"id": params["program_id"]},
            "status": status,
            "usage": {"qpu_charge_time_seconds": seconds},
            "params": params,
        },
        fingerprint_params(params),
        params_available=True,
        now=stamp,
    )


def seed(store: Store) -> None:
    base = datetime.now(timezone.utc) - timedelta(days=10)
    rng = random.Random(7)

    # 1) Abuser: the exact same circuit every 5 minutes, 40 times. Nothing varies.
    for i in range(40):
        _insert(
            store, f"abuse-{i:03d}", "u_abuser", base + timedelta(minutes=5 * i),
            "ibm_torino", 12.0, BELL, [], 4096,
        )

    # 2) A trivial circuit (no two-qubit gates) repeated every 3 minutes.
    for i in range(25):
        _insert(
            store, f"trivial-{i:03d}", "u_trivial", base + timedelta(minutes=3 * i),
            "ibm_brisbane", 6.0, TRIVIAL, [], 1024,
        )

    # 3) VQE: same skeleton, parameters converging, inside a session.
    theta = [1.0, -0.8, 0.6, 0.4]
    for i in range(30):
        step = 0.5 * (0.85 ** i)
        theta = [t - step * (1 if j % 2 == 0 else -1) for j, t in enumerate(theta)]
        _insert(
            store, f"vqe-{i:03d}", "u_vqe", base + timedelta(minutes=4 * i),
            "ibm_torino", 9.0, ANSATZ, [round(t, 6) for t in theta], 2048,
            session_id="sess-vqe-1",
        )

    # 4) Benchmark: one circuit, spread over ten days across two backends.
    for i in range(10):
        _insert(
            store, f"bench-{i:03d}", "u_bench", base + timedelta(days=i, hours=1),
            "ibm_torino" if i % 2 else "ibm_brisbane", 15.0, BELL, [], 4096,
        )

    # 5) Ordinary user: different circuit each time, irregular gaps.
    offset = 0.0
    for i in range(15):
        offset += rng.uniform(0.5, 20.0)
        _insert(
            store, f"normal-{i:03d}", "u_normal", base + timedelta(hours=offset),
            "ibm_torino", 20.0, _qasm_variant(i), [], 4096,
        )

    # 6) QAOA: five repeats per parameter set for statistics. The repeat count
    #    crosses the threshold, but the trajectory converges, so it must stay normal.
    #    If the convergence test breaks, this scenario is what catches it.
    angles = [0.9, -0.7, 0.5, 0.3]
    index = 0
    for step_i in range(12):
        delta = 0.4 * (0.82 ** step_i)
        angles = [a - delta * (1 if j % 2 == 0 else -1) for j, a in enumerate(angles)]
        bound = [round(a, 6) for a in angles]
        for _ in range(5):
            _insert(
                store, f"qaoa-{index:03d}", "u_qaoa",
                base + timedelta(minutes=2 * index),
                "ibm_torino", 7.0, ANSATZ, bound, 2048, session_id="sess-qaoa-1",
            )
            index += 1

    # 7) Estimator observable scan: one circuit measured with 40 different Pauli
    #    observables, 2 minutes apart, same backend and shots. Superficially it looks
    #    exactly like abuse, but the observables differ every time, so it must stay
    #    normal. This mirrors a real false positive.
    for i in range(40):
        position = i % 7
        pauli = "I" * position + "Z" + "I" * (6 - position)
        _insert(
            store, f"est-{i:03d}", "u_estimator", base + timedelta(minutes=2 * i),
            "ibm_torino", 5.0, ANSATZ, [0.1, 0.2, 0.3, 0.4], 4096,
            observables={pauli: 1.0, "I" * 7: float(i)},
        )


EXPECTED = {
    # Identical circuit 40 times at 5-minute intervals — must be caught.
    "u_abuser": {"flagged": True, "min_score": 40},
    # Non-entangling circuit repeated — must be caught.
    "u_trivial": {"flagged": True, "min_score": 40},
    # VQE varies parameters every iteration — must not be flagged.
    "u_vqe": {"flagged": False, "max_score": 15},
    # QAOA repeats each parameter set but converges — must not be flagged.
    "u_qaoa": {"flagged": False, "max_score": 15},
    # Long-running drift benchmark — must not be flagged.
    "u_bench": {"flagged": False, "max_score": 15},
    # Different circuit every time — near zero.
    "u_normal": {"flagged": False, "max_score": 10},
    # Same circuit, different observables each run — must not be flagged.
    "u_estimator": {"flagged": False, "max_score": 15},
}


def run_selftest(out_path: Path | None = None) -> int:
    # The database goes to a temporary directory so real collections are untouched.
    # The report lands in the project's reports/ folder so it can be inspected.
    tmp = Path(tempfile.mkdtemp(prefix="qpu-audit-selftest-"))
    settings = Settings(api_key="", crn="", root=tmp, tuning=DEFAULTS)
    store = Store(settings.db_path)
    failures: list[str] = []
    try:
        seed(store)
        analysis = analyze(store, settings, UserMap(entries={}))
        analysis.notes.insert(
            0,
            "This report was generated by selftest from synthetic data. "
            "It does not reflect any real instance.",
        )
        by_user = {u.user_id: u for u in analysis.users}

        print("\nSynthetic scenario results")
        print("-" * 76)
        print(f"{'user':<14} {'score':>6} {'flagged':>8} {'unexplained':>13} {'unique':>8}  result")
        print("-" * 76)

        for user_id, expect in EXPECTED.items():
            user = by_user.get(user_id)
            if user is None:
                failures.append(f"{user_id}: missing from the analysis")
                continue
            flagged_groups = user.abuse_groups
            ok = True
            if expect["flagged"] and flagged_groups == 0:
                ok = False
                failures.append(f"{user_id}: should have been flagged but was not")
            if not expect["flagged"] and flagged_groups > 0:
                ok = False
                failures.append(
                    f"{user_id}: legitimate pattern flagged ({flagged_groups} groups)"
                )
            if "min_score" in expect and user.score < expect["min_score"]:
                ok = False
                failures.append(f"{user_id}: score {user.score} < expected {expect['min_score']}")
            if "max_score" in expect and user.score > expect["max_score"]:
                ok = False
                failures.append(f"{user_id}: score {user.score} > allowed {expect['max_score']}")
            print(
                f"{user_id:<14} {user.score:6.0f} {flagged_groups:8d} "
                f"{user.flagged_waste_seconds:12.0f}s {user.unique_ratio * 100:7.0f}%  "
                f"{'PASS' if ok else 'FAIL'}"
            )
            for finding in user.findings[:2]:
                print(f"               - {finding}")

        report_path = write_report(
            analysis,
            store,
            out_path or (PROJECT_ROOT / "reports" / "selftest-sample.html"),
            settings.section("report"),
            # Synthetic data carries no QPY payloads, so family comparison is moot.
            with_extras=False,
        )
        print("-" * 76)
        print(f"Sample report: {report_path}")
        print("  (synthetic data — real results come from collect + report)")

        if failures:
            print("\nFailures:")
            for item in failures:
                print(f"  x {item}")
            return 1
        print("\nAll scenarios passed.")
        return 0
    finally:
        store.close()
