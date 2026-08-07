"""Detection rules and metrics.

The question is never "how many times was this circuit run" but **why it was run
again**. VQE reruns one ansatz hundreds of times by design. Three axes separate the
cases:

  same exact_hash       identical re-execution, parameters included
  same structural       same skeleton, different parameters
  parameter trajectory  converging means an optimizer loop, not waste

Scores only come from groups that survived the verdict rules. Work judged normal
contributes zero no matter how often it ran — otherwise diligent researchers rank
at the top.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .i18n import Msg

TERMINAL_FAILED = {"failed"}

VERDICT_LABEL = {
    "abuse": "flagged",
    "gray": "unexplained",
    "benign": "normal",
}

# Grey means "repetition without an explanation", so it counts at half weight.
VERDICT_WEIGHT = {"abuse": 1.0, "gray": 0.5, "benign": 0.0}

SIGNAL_LABELS = {
    "duplicate_waste": "repeated identical execution",
    "top_circuit_share": "single-circuit concentration",
    "trivial_circuit": "non-entangling circuits",
    "failure_resubmit": "failed-payload resubmission",
    "burst_submission": "burst submission",
    "no_session": "no session/batch grouping",
    "overuse": "suspected overuse",
    "regular_interval": "mechanical submission interval",
    "usage_spike": "usage spike",
}

# Signals fall into three classes, because "is this work legitimate?" and "does this
# behaviour harm others?" are different questions and must not be collapsed.
#
#   waste    QPU time burned on nothing. Questions the work itself.
#   queue    Harm to other users regardless of whether the work is legitimate.
#            A burst of a thousand jobs monopolises the queue even when the science
#            is impeccable — and the fix ("use batch") does not question the science.
#   context  Information only. Fires on ordinary situations and cannot, by itself,
#            justify anything.
SIGNAL_CLASS = {
    "duplicate_waste": "waste",
    "top_circuit_share": "waste",
    "trivial_circuit": "waste",
    "failure_resubmit": "waste",
    "burst_submission": "queue",
    "no_session": "queue",
    "overuse": "context",
    "regular_interval": "context",
    "usage_spike": "context",
}

CLASS_LABEL = {
    "waste": "wasted QPU",
    "queue": "queue impact",
    "context": "context",
}


@dataclass
class RiskSignal:
    """One risk indicator.

    Points express suspicion, not guilt. ``klass`` says what kind of suspicion:
    waste questions the work, queue questions the submission pattern, context
    questions nothing at all.
    """

    code: str
    label: str
    points: float
    detail: Msg | None
    klass: str = "context"

    @property
    def label_key(self) -> str:
        return f"sig_{self.code}"

    @property
    def context_only(self) -> bool:
        return self.klass == "context"

    @property
    def severity(self) -> str:
        if self.points >= 15:
            return "high"
        if self.points >= 7:
            return "medium"
        return "low"


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class Run:
    """One pub execution — the unit of analysis."""

    job_id: str
    user_id: str
    created: datetime | None
    backend: str | None
    instance: str
    status: str
    session_id: str | None
    exact_hash: str | None
    structural_hash: str | None
    shots: int | None
    seconds: float
    param_vector: list[float]
    intent_hash: str | None = None
    name: str = ""
    program: str = ""
    n_qubits: int = 0
    n_ops: int = 0
    n_2q_ops: int = 0
    depth: int = 0
    has_measure: bool = False
    clifford_only: bool = False
    parsed: bool = False

    @property
    def identity(self) -> str | None:
        """What counts as "the same circuit".

        A trustworthy experiment name wins, because it survives re-transpilation.
        Otherwise fall back to the byte-level exact fingerprint.
        """
        return self.intent_hash or self.exact_hash

    @property
    def trivial(self) -> bool:
        """A circuit with no reason to occupy a QPU.

        Two deliberate exclusions:
        - Clifford-only is not counted. Randomized benchmarking and calibration use
          Clifford circuits legitimately.
        - **Estimator jobs have no measurement gates by design** — observables are
          supplied separately and the service applies basis rotations. Counting that
          as waste flags normal expectation-value work.
        """
        if not self.parsed or self.n_ops == 0:
            return False
        if self.n_2q_ops == 0:
            return True
        return not self.has_measure and self.program != "estimator"

    @property
    def trivial_reason(self) -> Msg | None:
        if not self.trivial:
            return None
        if self.n_2q_ops == 0:
            return Msg("trivial_no_2q")
        return Msg("trivial_no_measure")


@dataclass
class CircuitGroup:
    """Executions of "the same circuit" by one user.

    Grouped by ``Run.identity``. Several ``exact_hashes`` means it was re-transpiled
    on each submission; exactly one means the identical payload was resubmitted.
    """

    exact_hash: str          # representative fingerprint, for evidence lookup
    structural_hash: str
    identity: str = ""
    kind: str = "exact"      # intent | exact
    name: str = ""
    exact_hashes: set[str] = field(default_factory=set)
    structural_hashes: set[str] = field(default_factory=set)
    param_vectors: list[list[float]] = field(default_factory=list)
    runs: int = 0
    seconds: float = 0.0
    repeat_runs: int = 0
    repeat_seconds: float = 0.0
    repeat_no_session: int = 0
    first: datetime | None = None
    last: datetime | None = None
    backends: set[str] = field(default_factory=set)
    shots: set[int] = field(default_factory=set)
    sessioned: int = 0
    failed: int = 0
    trivial: bool = False
    trivial_reason: Msg | None = None
    clifford_only: bool = False
    n_qubits: int = 0
    n_ops: int = 0
    n_2q_ops: int = 0
    intervals: list[float] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)
    job_ids: list[str] = field(default_factory=list)
    sample_job_id: str = ""
    verdict: str = "benign"
    reasons: list[Msg] = field(default_factory=list)

    @property
    def span_hours(self) -> float:
        if not self.first or not self.last:
            return 0.0
        return (self.last - self.first).total_seconds() / 3600.0

    @property
    def median_interval_min(self) -> float | None:
        return statistics.median(self.intervals) / 60.0 if self.intervals else None

    @property
    def weight(self) -> float:
        return VERDICT_WEIGHT.get(self.verdict, 0.0)

    @property
    def distinct_exact(self) -> int:
        return len(self.exact_hashes)

    @property
    def retranspiled(self) -> bool:
        """Gate sequence differed every run — re-transpiled on each submission."""
        return self.runs > 1 and self.distinct_exact >= self.runs

    @property
    def identical_payload(self) -> bool:
        """Byte-identical payload resubmitted — the strongest evidence available."""
        return self.runs > 1 and self.distinct_exact == 1


@dataclass
class StructuralGroup:
    structural_hash: str
    runs: int = 0
    distinct_exact: int = 0
    seconds: float = 0.0
    converging: bool | None = None
    convergence_ratio: float | None = None
    param_dim: int = 0


@dataclass
class UserReport:
    user_id: str
    label: str
    jobs: int = 0
    runs: int = 0
    seconds: float = 0.0
    jobs_with_circuit: int = 0
    jobs_without_circuit: int = 0
    private_jobs: int = 0
    unique_exact: int = 0        # distinct circuit identities
    unique_payloads: int = 0     # distinct payloads, re-transpilations included
    unique_structural: int = 0
    intent_groups: int = 0

    # Informational: every repeat, regardless of verdict
    duplicate_runs: int = 0
    wasted_seconds: float = 0.0

    # Scored: only from flagged or grey groups
    flagged_waste_seconds: float = 0.0
    flagged_trivial_seconds: float = 0.0
    flagged_no_session_runs: int = 0
    flagged_top_seconds: float = 0.0
    failure_resubmit_runs: int = 0

    interval_cv: float | None = None
    interval_samples: int = 0
    # Share of the whole service, across every instance collected.
    instance_share: float = 0.0
    # Largest share this user holds inside any single instance, and which one.
    # Both matter: hogging one small instance and hogging everything are different
    # problems, and looking at only one of them misses the other.
    top_instance_share: float = 0.0
    top_instance: str = ""
    instances: dict[str, float] = field(default_factory=dict)  # instance -> QPU seconds
    waste_share: float = 0.0
    max_burst: int = 0
    month_ratio: float | None = None
    signals: list[RiskSignal] = field(default_factory=list)
    score: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)
    findings: list[Msg] = field(default_factory=list)
    groups: list[CircuitGroup] = field(default_factory=list)
    structural: list[StructuralGroup] = field(default_factory=list)
    backends: set[str] = field(default_factory=set)

    @property
    def unique_ratio(self) -> float:
        return self.unique_exact / self.runs if self.runs else 1.0

    @property
    def top_circuit_share(self) -> float:
        return self.flagged_top_seconds / self.seconds if self.seconds else 0.0

    @property
    def coverage(self) -> float:
        """Share of jobs whose circuit was actually retrieved."""
        return self.jobs_with_circuit / self.jobs if self.jobs else 0.0

    @property
    def abuse_groups(self) -> int:
        return sum(1 for g in self.groups if g.verdict == "abuse")

    def class_points(self, klass: str) -> float:
        return round(sum(s.points for s in self.signals if s.klass == klass), 1)

    @property
    def waste_points(self) -> float:
        return self.class_points("waste")

    @property
    def queue_points(self) -> float:
        return self.class_points("queue")

    @property
    def context_points(self) -> float:
        return self.class_points("context")

    @property
    def actionable_points(self) -> float:
        """Score excluding context signals — waste plus queue impact."""
        return round(self.waste_points + self.queue_points, 1)


@dataclass
class Analysis:
    window_days: int
    generated_at: datetime
    users: list[UserReport]
    total_seconds: float
    total_jobs: int
    total_runs: int
    coverage: float
    unmapped_users: list[str]
    notes: list[Msg] = field(default_factory=list)
    session_data_available: bool = True
    # instance CRN -> total QPU seconds in the window, and CRN -> friendly name
    instances: dict[str, float] = field(default_factory=dict)
    instance_names: dict[str, str] = field(default_factory=dict)

    def instance_label(self, crn: str) -> str:
        return self.instance_names.get(crn) or (crn.rsplit(":", 2)[-2][:12] if ":" in crn else crn)


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_runs(store: Any, since: datetime) -> list[Run]:
    rows = store.query(
        """
        SELECT
            w.id            AS job_id,
            w.user_id       AS user_id,
            w.created       AS created,
            w.backend       AS backend,
            w.instance      AS instance,
            w.status        AS status,
            COALESCE(w.usage_seconds, j.usage_seconds, 0) AS seconds,
            COALESCE(j.pub_count, 0)      AS pub_count,
            j.session_id    AS session_id,
            j.program       AS program,
            j.private       AS private,
            p.exact_hash, p.structural_hash, p.intent_hash, p.shots, p.param_vector,
            c.n_qubits, c.n_ops, c.n_2q_ops, c.depth, c.has_measure,
            c.clifford_only, c.parsed, c.name
        FROM workloads w
        LEFT JOIN jobs     j ON j.id = w.id
        LEFT JOIN pubs     p ON p.job_id = w.id
        LEFT JOIN circuits c ON c.exact_hash = p.exact_hash
        WHERE w.mode = 'job'
          AND w.created >= ?
          AND w.user_id IS NOT NULL
        ORDER BY w.created ASC
        """,
        (since.isoformat().replace("+00:00", "Z"),),
    )

    runs: list[Run] = []
    for row in rows:
        pub_count = max(int(row["pub_count"] or 0), 1)
        try:
            params = json.loads(row["param_vector"]) if row["param_vector"] else []
        except (TypeError, ValueError):
            params = []
        runs.append(
            Run(
                job_id=row["job_id"],
                user_id=row["user_id"],
                created=_parse_ts(row["created"]),
                backend=row["backend"],
                instance=row["instance"] or "",
                status=(row["status"] or "").lower(),
                session_id=row["session_id"],
                exact_hash=row["exact_hash"],
                structural_hash=row["structural_hash"],
                intent_hash=row["intent_hash"],
                name=row["name"] or "",
                program=(row["program"] or "").lower(),
                shots=row["shots"],
                # Spread the job's usage across its pubs.
                seconds=float(row["seconds"] or 0.0) / pub_count,
                param_vector=[float(v) for v in params] if isinstance(params, list) else [],
                n_qubits=int(row["n_qubits"] or 0),
                n_ops=int(row["n_ops"] or 0),
                n_2q_ops=int(row["n_2q_ops"] or 0),
                depth=int(row["depth"] or 0),
                has_measure=bool(row["has_measure"]),
                clifford_only=bool(row["clifford_only"]),
                parsed=bool(row["parsed"]),
            )
        )
    return runs


# ---------------------------------------------------------------------------
# parameter trajectory: is this an optimizer?
# ---------------------------------------------------------------------------

def assess_convergence(
    vectors: list[list[float]], threshold: float
) -> tuple[bool | None, float | None]:
    """Shrinking steps between consecutive parameter vectors indicate an optimizer.

    Returns (converging, late/early mean step ratio), or (None, None) when undecidable.
    """
    usable = [v for v in vectors if v]
    if len(usable) < 6:
        return None, None
    dim = len(usable[0])
    if dim == 0 or any(len(v) != dim for v in usable):
        return None, None

    steps = [math.dist(prev, cur) for prev, cur in zip(usable, usable[1:])]
    if not steps or all(s == 0 for s in steps):
        # Parameters never moved, so this is not an optimization.
        return False, 0.0

    half = len(steps) // 2
    early = statistics.fmean(steps[:half]) if half else 0.0
    late = statistics.fmean(steps[half:]) if len(steps) - half else 0.0
    if early <= 0:
        return None, None
    ratio = late / early
    return ratio < threshold, ratio


# ---------------------------------------------------------------------------
# verdicts
# ---------------------------------------------------------------------------

def _max_burst(timestamps: list[datetime], window_seconds: float = 60.0) -> int:
    """Largest run of submissions arriving within one window."""
    ordered = sorted(t for t in timestamps if t)
    if not ordered:
        return 0
    best = size = 1
    for previous, current in zip(ordered, ordered[1:]):
        if (current - previous).total_seconds() <= window_seconds:
            size += 1
        else:
            size = 1
        best = max(best, size)
    return best


def _interval_stats(timestamps: list[datetime]) -> tuple[float | None, int]:
    """Coefficient of variation of submission gaps. Low means mechanical."""
    ordered = sorted(t for t in timestamps if t)
    deltas = [
        (b - a).total_seconds()
        for a, b in zip(ordered, ordered[1:])
        if (b - a).total_seconds() > 0
    ]
    if len(deltas) < 3:
        return None, len(deltas)
    mean = statistics.fmean(deltas)
    if mean <= 0:
        return None, len(deltas)
    return statistics.pstdev(deltas) / mean, len(deltas)


def judge_group(group: CircuitGroup, rules: dict[str, Any], converging: bool | None) -> None:
    """Verdict for one circuit group. Implements the table in docs/detection.md."""
    min_repeats = int(rules.get("min_repeats_for_flag", 5))
    short_min = float(rules.get("short_interval_minutes", 30))

    if group.runs < min_repeats:
        group.verdict = "benign"
        return

    median_int = group.median_interval_min
    same_backend = len(group.backends) <= 1
    same_shots = len(group.shots) <= 1
    short_gap = median_int is not None and median_int <= short_min
    mostly_no_session = (group.sessioned / group.runs) < 0.2 if group.runs else True

    if converging:
        group.verdict = "benign"
        group.reasons.append(Msg("r_converging"))
        return

    # Tight repetition is the primary signal and must be checked first. Excusing it
    # because the overall span is long lets every burst pattern through.
    if short_gap and same_shots:
        label = f"'{group.name}'" if group.name else "—"
        if same_backend:
            group.verdict = "abuse"
            group.reasons.append(
                Msg(
                    "r_flagged", label=label, runs=group.runs,
                    gap=f"{median_int:.1f}", span=f"{group.span_hours:.1f}",
                )
            )
        else:
            # Spread over backends could be a deliberate comparison.
            group.verdict = "gray"
            group.reasons.append(
                Msg(
                    "r_gray_backends", label=label, runs=group.runs,
                    gap=f"{median_int:.1f}", n=len(group.backends),
                )
            )
        if group.identical_payload:
            group.reasons.append(Msg("r_identical"))
        elif group.retranspiled:
            group.reasons.append(Msg("r_retranspiled", n=group.distinct_exact))
        if mostly_no_session:
            group.reasons.append(Msg("r_nosession"))
        if group.trivial and group.trivial_reason:
            group.reasons.append(Msg("r_trivial", reason=group.trivial_reason))
        elif group.clifford_only:
            group.reasons.append(Msg("r_clifford"))
        return

    # Genuinely spread out — treat as drift tracking or benchmarking.
    if group.span_hours >= 48 or not same_backend:
        group.verdict = "benign"
        group.reasons.append(Msg("r_benign_spread"))
        return

    group.verdict = "gray"
    detail: list[Msg] = []
    if median_int is not None:
        detail.append(Msg("r_detail_gap", gap=f"{median_int:.1f}"))
    if not same_shots:
        detail.append(Msg("r_detail_shots"))
    group.reasons.append(_gray_repeat_msg(group.runs, detail))
    if group.trivial and group.trivial_reason:
        group.reasons.append(Msg("r_trivial", reason=group.trivial_reason))


class _JoinedMsg(Msg):
    """A Msg whose detail clause is assembled from other Msgs at render time."""

    __slots__ = ("_parts",)

    def __init__(self, runs: int, parts: list[Msg]) -> None:
        super().__init__("r_gray_repeat", runs=runs, detail="")
        self._parts = parts

    def text(self, lang: str = "en") -> str:
        joined = ", ".join(p.text(lang) for p in self._parts)
        self.params["detail"] = f" ({joined})" if joined else ""
        return super().text(lang)


def _gray_repeat_msg(runs: int, parts: list[Msg]) -> Msg:
    return _JoinedMsg(runs, parts)


def _fmt_duration(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.1f} h"
    if seconds >= 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.0f} s"


def _score(
    user: UserReport,
    weights: dict[str, Any],
    rules: dict[str, Any],
    session_known: bool = True,
) -> None:
    total = user.seconds or 1.0
    runs = user.runs or 1

    components = {
        "duplicate_waste": min(user.flagged_waste_seconds / total, 1.0),
        "top_circuit_share": min(user.top_circuit_share, 1.0),
        "trivial_circuit": min(user.flagged_trivial_seconds / total, 1.0),
        "regular_interval": 0.0,
        "failure_resubmit": min(user.failure_resubmit_runs / runs, 1.0),
        # With no session_id anywhere, "not used" and "not reported" are
        # indistinguishable. Do not score what has not been established.
        "no_session": min(user.flagged_no_session_runs / runs, 1.0) if session_known else 0.0,
        "overuse": 0.0,
        "usage_spike": 0.0,
        "burst_submission": 0.0,
    }
    details: dict[str, Msg] = {
        "duplicate_waste": Msg(
            "d_duplicate_waste",
            amount=_fmt_duration(user.flagged_waste_seconds),
            pct=f"{user.flagged_waste_seconds / total * 100:.0f}",
        ),
        "top_circuit_share": Msg(
            "d_top_circuit_share", pct=f"{user.top_circuit_share * 100:.0f}"
        ),
        "trivial_circuit": Msg(
            "d_trivial_circuit", amount=_fmt_duration(user.flagged_trivial_seconds)
        ),
        "failure_resubmit": Msg("d_failure_resubmit", n=user.failure_resubmit_runs),
        "no_session": Msg("d_no_session", n=user.flagged_no_session_runs),
    }

    cv_threshold = float(rules.get("interval_regularity_cv", 0.20))
    min_samples = int(rules.get("interval_min_samples", 8))
    if user.interval_cv is not None and user.interval_samples >= min_samples:
        components["regular_interval"] = min(max(0.0, 1.0 - user.interval_cv / cv_threshold), 1.0)
        # Timing alone is not worth penalising when nothing else was flagged.
        if user.abuse_groups == 0 and user.flagged_waste_seconds <= 0:
            components["regular_interval"] *= 0.3
        details["regular_interval"] = Msg(
            "d_regular_interval", cv=f"{user.interval_cv:.2f}"
        )

    floor = float(rules.get("overuse_share_floor", 0.30))
    ceiling = float(rules.get("overuse_share_full", 0.50))
    # Take whichever is worse: dominating the whole service, or dominating one
    # instance. Scoring only the global share lets someone monopolise a small
    # instance unnoticed; scoring only the per-instance share misses the person
    # who took over every instance at once.
    worst_share = max(user.instance_share, user.top_instance_share)
    if worst_share > floor and ceiling > floor:
        components["overuse"] = min((worst_share - floor) / (ceiling - floor), 1.0)
        if user.top_instance_share > user.instance_share and user.top_instance:
            details["overuse"] = Msg(
                "d_overuse_instance",
                pct=f"{user.top_instance_share * 100:.0f}",
                instance=user.top_instance,
                global_pct=f"{user.instance_share * 100:.0f}",
                amount=_fmt_duration(user.seconds),
                jobs=user.jobs,
            )
        else:
            details["overuse"] = Msg(
                "d_overuse_global",
                pct=f"{user.instance_share * 100:.0f}",
                amount=_fmt_duration(user.seconds),
                jobs=user.jobs,
            )

    spike_at = float(rules.get("usage_spike_ratio", 2.0))
    if user.month_ratio is not None and user.month_ratio > spike_at:
        components["usage_spike"] = min((user.month_ratio - spike_at) / spike_at, 1.0)
        details["usage_spike"] = (
            Msg("d_usage_spike_new")
            if user.month_ratio == float("inf")
            else Msg("d_usage_spike", ratio=f"{user.month_ratio:.1f}")
        )

    burst_at = int(rules.get("burst_size_warn", 10))
    if user.max_burst >= burst_at:
        components["burst_submission"] = min(user.max_burst / (burst_at * 5), 1.0)
        details["burst_submission"] = Msg("d_burst", n=user.max_burst)

    user.breakdown = {
        key: round(float(weights.get(key, 0)) * value, 2) for key, value in components.items()
    }
    user.score = round(min(sum(user.breakdown.values()), 100.0), 1)
    class_order = {"waste": 0, "queue": 1, "context": 2}
    user.signals = [
        RiskSignal(
            code=key,
            label=SIGNAL_LABELS.get(key, key),
            points=points,
            detail=details.get(key),
            klass=SIGNAL_CLASS.get(key, "context"),
        )
        for key, points in sorted(
            user.breakdown.items(),
            key=lambda kv: (class_order.get(SIGNAL_CLASS.get(kv[0], "context"), 3), -kv[1]),
        )
        if points > 0
    ]


def _findings(user: UserReport, rules: dict[str, Any], session_known: bool = True) -> None:
    out: list[Msg] = []
    waste_warn = float(rules.get("waste_seconds_warn", 300.0))

    if user.flagged_waste_seconds >= waste_warn:
        share = user.flagged_waste_seconds / user.seconds * 100 if user.seconds else 0.0
        out.append(
            Msg(
                "f_waste",
                amount=_fmt_duration(user.flagged_waste_seconds),
                pct=f"{share:.0f}",
            )
        )
    if user.top_circuit_share >= float(rules.get("top_circuit_share_warn", 0.5)):
        out.append(Msg("f_top_circuit", pct=f"{user.top_circuit_share * 100:.0f}"))
    if (
        user.jobs_with_circuit
        and user.runs
        and user.unique_ratio < float(rules.get("unique_ratio_warn", 0.3))
    ):
        common = {
            "pct": f"{user.unique_ratio * 100:.0f}",
            "distinct": user.unique_exact,
            "runs": user.runs,
        }
        if user.unique_payloads <= user.unique_exact:
            out.append(Msg("f_unique", **common))
        else:
            out.append(Msg("f_unique_rt", payloads=user.unique_payloads, **common))
    cv_threshold = float(rules.get("interval_regularity_cv", 0.20))
    if (
        user.interval_cv is not None
        and user.interval_samples >= int(rules.get("interval_min_samples", 8))
        and user.interval_cv < cv_threshold
        and user.abuse_groups
    ):
        out.append(Msg("f_mechanical", cv=f"{user.interval_cv:.2f}"))
    if user.flagged_trivial_seconds > 0:
        out.append(Msg("f_trivial", amount=_fmt_duration(user.flagged_trivial_seconds)))
    if user.failure_resubmit_runs >= int(rules.get("min_repeats_for_flag", 5)):
        out.append(Msg("f_failure", n=user.failure_resubmit_runs))
    if session_known and user.flagged_no_session_runs >= int(
        rules.get("min_repeats_for_flag", 5)
    ):
        out.append(Msg("f_no_session", n=user.flagged_no_session_runs))
    if user.private_jobs:
        out.append(Msg("f_private", n=user.private_jobs))
    if user.jobs and user.coverage < 0.5:
        out.append(Msg("f_coverage", pct=f"{user.coverage * 100:.0f}"))
    user.findings = out


# ---------------------------------------------------------------------------
# per-user analysis
# ---------------------------------------------------------------------------

def _build_groups(runs: list[Run]) -> dict[str, CircuitGroup]:
    groups: dict[str, CircuitGroup] = {}
    last_seen: dict[str, datetime] = {}

    for run in sorted(runs, key=lambda r: r.created or datetime.min.replace(tzinfo=timezone.utc)):
        identity = run.identity
        if not identity:
            continue
        group = groups.get(identity)
        if group is None:
            group = CircuitGroup(
                exact_hash=run.exact_hash or identity,
                structural_hash=run.structural_hash or "",
                identity=identity,
                kind="intent" if run.intent_hash else "exact",
                name=run.name,
                sample_job_id=run.job_id,
                trivial=run.trivial,
                trivial_reason=run.trivial_reason,
                clifford_only=run.clifford_only,
                n_qubits=run.n_qubits,
                n_ops=run.n_ops,
                n_2q_ops=run.n_2q_ops,
            )
            groups[identity] = group
        else:
            # Everything after the first execution is a repeat.
            group.repeat_runs += 1
            group.repeat_seconds += run.seconds
            if not run.session_id:
                group.repeat_no_session += 1

        group.runs += 1
        group.seconds += run.seconds
        if run.exact_hash:
            group.exact_hashes.add(run.exact_hash)
        if run.structural_hash:
            group.structural_hashes.add(run.structural_hash)
        if len(group.param_vectors) < 400:
            group.param_vectors.append(run.param_vector)
        if run.backend:
            group.backends.add(run.backend)
        if run.shots is not None:
            group.shots.add(run.shots)
        if run.session_id:
            group.sessioned += 1
        if run.status in TERMINAL_FAILED:
            group.failed += 1
        if len(group.job_ids) < 50:
            group.job_ids.append(run.job_id)
        if run.created:
            group.timestamps.append(run.created)
            if group.first is None:
                group.first = run.created
            group.last = run.created
            prev = last_seen.get(identity)
            if prev:
                group.intervals.append((run.created - prev).total_seconds())
            last_seen[identity] = run.created

    return groups


def _build_structural(
    runs: list[Run], groups: dict[str, CircuitGroup], rules: dict[str, Any]
) -> dict[str, StructuralGroup]:
    structural: dict[str, StructuralGroup] = {}
    vectors: dict[str, list[list[float]]] = {}

    for run in sorted(runs, key=lambda r: r.created or datetime.min.replace(tzinfo=timezone.utc)):
        if not run.structural_hash:
            continue
        sgroup = structural.setdefault(
            run.structural_hash, StructuralGroup(structural_hash=run.structural_hash)
        )
        sgroup.runs += 1
        sgroup.seconds += run.seconds
        vectors.setdefault(run.structural_hash, []).append(run.param_vector)

    for shash, sgroup in structural.items():
        sgroup.distinct_exact = sum(1 for g in groups.values() if g.structural_hash == shash)
        vecs = vectors.get(shash, [])
        sgroup.param_dim = len(vecs[0]) if vecs and vecs[0] else 0
        if sgroup.distinct_exact > 1:
            sgroup.converging, sgroup.convergence_ratio = assess_convergence(
                vecs, float(rules.get("convergence_ratio", 0.6))
            )

    return structural


def _analyze_user(
    user_id: str,
    label: str,
    runs: list[Run],
    rules: dict[str, Any],
    weights: dict[str, Any],
    session_known: bool = True,
    month_ratio: float | None = None,
    instance_share: float = 0.0,
    instance_totals: dict[str, float] | None = None,
    instance_names: dict[str, str] | None = None,
) -> UserReport:
    report = UserReport(user_id=user_id, label=label)
    report.month_ratio = month_ratio
    report.instance_share = instance_share
    instance_totals = instance_totals or {}
    instance_names = instance_names or {}

    job_ids: set[str] = set()
    jobs_with_circuit: set[str] = set()
    for run in runs:
        job_ids.add(run.job_id)
        report.seconds += run.seconds
        report.runs += 1
        if run.backend:
            report.backends.add(run.backend)
        if run.instance:
            report.instances[run.instance] = report.instances.get(run.instance, 0.0) + run.seconds
        if run.exact_hash:
            jobs_with_circuit.add(run.job_id)

    # Share held inside each individual instance, and the worst of them.
    for crn, seconds in report.instances.items():
        total = instance_totals.get(crn, 0.0)
        if total <= 0:
            continue
        share = seconds / total
        if share > report.top_instance_share:
            report.top_instance_share = share
            report.top_instance = instance_names.get(crn, crn)
    report.jobs = len(job_ids)
    report.jobs_with_circuit = len(jobs_with_circuit)
    report.jobs_without_circuit = report.jobs - report.jobs_with_circuit

    groups = _build_groups(runs)
    structural = _build_structural(runs, groups, rules)

    threshold = float(rules.get("convergence_ratio", 0.6))
    for group in groups.values():
        converging = None
        if len(group.structural_hashes) == 1:
            sgroup = structural.get(next(iter(group.structural_hashes)))
            if sgroup and sgroup.distinct_exact > 1:
                converging = sgroup.converging
        if converging is None and group.distinct_exact > 1:
            converging, _ = assess_convergence(group.param_vectors, threshold)
        judge_group(group, rules, converging)

        report.duplicate_runs += group.repeat_runs
        report.wasted_seconds += group.repeat_seconds

        weight = group.weight
        if weight <= 0:
            continue
        report.flagged_waste_seconds += group.repeat_seconds * weight
        report.flagged_no_session_runs += int(group.repeat_no_session * weight)
        report.flagged_top_seconds = max(report.flagged_top_seconds, group.seconds * weight)
        if group.trivial:
            report.flagged_trivial_seconds += group.seconds * weight
        if group.failed >= int(rules.get("min_repeats_for_flag", 5)):
            report.failure_resubmit_runs += group.failed

    report.unique_exact = len(groups)
    report.unique_payloads = len({h for g in groups.values() for h in g.exact_hashes})
    report.intent_groups = sum(1 for g in groups.values() if g.kind == "intent")
    report.unique_structural = len(structural)
    # Bursts and intervals are per job — counting each pub separately double-counts.
    job_times = {r.job_id: r.created for r in runs if r.created}
    report.interval_cv, report.interval_samples = _interval_stats(list(job_times.values()))
    report.max_burst = _max_burst(list(job_times.values()))

    order = {"abuse": 0, "gray": 1, "benign": 2}
    report.groups = sorted(groups.values(), key=lambda g: (order.get(g.verdict, 3), -g.seconds))
    report.structural = sorted(structural.values(), key=lambda s: -s.seconds)

    _score(report, weights, rules, session_known)
    _findings(report, rules, session_known)
    return report


def _month_ratios(store: Any) -> dict[str, float]:
    """Month-over-month usage multiples per user.

    Read from the ledger, so it keeps working after IBM drops the original
    workloads, and a month in progress is scaled to a full-month estimate.
    """
    from .usage import load_ledger

    ledger = load_ledger(store, months=24)
    if len(ledger.months) < 2:
        return {}
    ratios: dict[str, float] = {}
    for user_id in ledger.users:
        change = ledger.change(user_id)
        if change is not None:
            ratios[user_id] = change.ratio
    return ratios


def analyze(store: Any, settings: Any, user_map: Any) -> Analysis:
    analyze_cfg = settings.section("analyze")
    rules = settings.section("rules")
    weights = settings.section("score")

    window_days = int(analyze_cfg.get("window_days", 30))
    whitelist = {str(x) for x in analyze_cfg.get("whitelist", [])}
    since = datetime.now(timezone.utc) - timedelta(days=window_days)

    runs = load_runs(store, since)

    # Session/batch usage is settled by workloads.mode. A user who never created a
    # session or batch container cannot have jobs inside one, regardless of whether
    # job-level session_id is populated.
    container_owners = {
        row["user_id"]
        for row in store.query(
            "SELECT DISTINCT user_id FROM workloads WHERE mode IN ('session','batch')"
        )
        if row["user_id"]
    }
    session_link_known = bool(
        store.query("SELECT SUM(session_id IS NOT NULL) AS n FROM jobs")[0]["n"]
    )

    by_user: dict[str, list[Run]] = {}
    for run in runs:
        by_user.setdefault(run.user_id, []).append(run)

    # Shares and month-over-month change must be settled before scoring.
    seconds_by_user = {
        user_id: sum(r.seconds for r in user_runs) for user_id, user_runs in by_user.items()
    }
    total_seconds = sum(seconds_by_user.values())
    instance_totals: dict[str, float] = {}
    for run in runs:
        if run.instance:
            instance_totals[run.instance] = instance_totals.get(run.instance, 0.0) + run.seconds
    instance_names = getattr(settings, "instance_names", None) or {}
    month_ratios = _month_ratios(store)

    reports: list[UserReport] = []
    for user_id, user_runs in by_user.items():
        label = user_map.label(user_id)
        if user_id in whitelist or label in whitelist:
            continue
        session_known = user_id not in container_owners or session_link_known
        share = seconds_by_user[user_id] / total_seconds if total_seconds else 0.0
        reports.append(
            _analyze_user(
                user_id, label, user_runs, rules, weights, session_known,
                month_ratios.get(user_id), share, instance_totals, instance_names,
            )
        )

    for report in reports:
        report.waste_share = (
            report.flagged_waste_seconds / total_seconds if total_seconds else 0.0
        )

    # Administrators need to see who actually burned time, not who has the worst
    # ratio. Sort by absolute waste, then by score.
    reports.sort(key=lambda r: (r.flagged_waste_seconds, r.score), reverse=True)

    total_jobs = sum(r.jobs for r in reports)
    with_circuit = sum(r.jobs_with_circuit for r in reports)

    notes: list[Msg] = []
    denied = store.query("SELECT COUNT(*) AS n FROM detail_errors WHERE status = 'denied'")[0]["n"]
    if denied:
        notes.append(Msg("n_denied", n=denied))
    missing = store.query("SELECT COUNT(*) AS n FROM detail_errors WHERE status = 'missing'")[0]["n"]
    if missing:
        notes.append(Msg("n_missing", n=missing))
    if container_owners and not session_link_known:
        notes.append(Msg("n_session_unknown", n=len(container_owners)))

    return Analysis(
        window_days=window_days,
        generated_at=datetime.now(timezone.utc),
        users=reports,
        total_seconds=total_seconds,
        total_jobs=total_jobs,
        total_runs=sum(r.runs for r in reports),
        coverage=with_circuit / total_jobs if total_jobs else 0.0,
        unmapped_users=[r.user_id for r in reports if not user_map.is_mapped(r.user_id)],
        notes=notes,
        session_data_available=not container_owners or session_link_known,
        instances=instance_totals,
        instance_names=instance_names,
    )


def abusive_groups(analysis: Analysis) -> Iterable[tuple[UserReport, CircuitGroup]]:
    for user in analysis.users:
        for group in user.groups:
            if group.verdict == "abuse":
                yield user, group
