"""Measuring how much circuits in a family actually differ.

State tomography and similar experiments produce circuits that are identical except
for a few basis-rotation gates at the end. Side by side in a console they look the
same, and an administrator reasonably concludes someone is running one circuit in a
loop. This has happened.

This module lines up the gate sequences of a circuit family and counts how many
operations are shared at the head and tail, so the answer becomes a number:
"50 leading operations identical, only 4 differ".

Requires stored QPY payloads, so it works after ``collect``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import qpy


@dataclass
class FamilyDiff:
    """Comparison of circuits sharing one profile (circuit family)."""

    profile_hash: str
    sample_names: list[str] = field(default_factory=list)
    circuits_compared: int = 0
    runs: int = 0
    total_ops: int = 0
    common_prefix: int = 0
    common_suffix: int = 0
    differing_ops: int = 0
    identical: bool = False

    @property
    def diff_ratio(self) -> float:
        return self.differing_ops / self.total_ops if self.total_ops else 0.0

    @property
    def summary(self) -> str:
        if self.circuits_compared < 2:
            return "Only one circuit to compare."
        if self.identical:
            return (
                f"{self.circuits_compared} sampled circuits are identical down to the "
                f"gate sequence ({self.total_ops} operations)."
            )
        parts = []
        if self.common_prefix:
            parts.append(f"first {self.common_prefix} operations identical")
        if self.common_suffix:
            parts.append(f"last {self.common_suffix} identical")
        head = ", ".join(parts) if parts else "no shared region"
        return (
            f"{self.circuits_compared} sampled circuits: {head}, "
            f"{self.differing_ops} operations actually differ "
            f"({self.diff_ratio * 100:.1f}% of {self.total_ops})"
        )

    @property
    def verdict(self) -> str:
        """One-line answer an administrator can read directly."""
        if self.circuits_compared < 2:
            return "not comparable"
        if self.identical:
            return "identical circuit"
        if self.diff_ratio < 0.15:
            return "nearly identical (measurement basis or similar)"
        return "genuinely different circuits"


def _payload_for(store: Any, exact_hash: str) -> bytes | None:
    rows = store.query(
        """
        SELECT pp.payload
        FROM pubs p
        JOIN pub_payloads pp ON pp.job_id = p.job_id AND pp.pub_index = p.pub_index
        WHERE p.exact_hash = ? LIMIT 1
        """,
        (exact_hash,),
    )
    return rows[0]["payload"] if rows else None


def _ops_of(payload: bytes) -> list[str] | None:
    decoded = qpy.decode_bytes(payload)
    if decoded is None or not decoded.canonical:
        return None
    return decoded.canonical.split("\n")


def compare_family(store: Any, exact_hashes: list[str], profile_hash: str = "") -> FamilyDiff:
    """Line up gate sequences and count shared versus differing regions."""
    result = FamilyDiff(profile_hash=profile_hash)

    sequences: list[list[str]] = []
    for exact_hash in exact_hashes:
        payload = _payload_for(store, exact_hash)
        if payload is None:
            continue
        ops = _ops_of(payload)
        if ops:
            sequences.append(ops)

    result.circuits_compared = len(sequences)
    if not sequences:
        return result
    result.total_ops = max(len(s) for s in sequences)
    if len(sequences) < 2:
        return result

    if all(s == sequences[0] for s in sequences[1:]):
        result.identical = True
        result.common_prefix = result.common_suffix = len(sequences[0])
        result.differing_ops = 0
        return result

    shortest = min(len(s) for s in sequences)

    prefix = 0
    while prefix < shortest and all(s[prefix] == sequences[0][prefix] for s in sequences):
        prefix += 1

    suffix = 0
    while (
        suffix < shortest - prefix
        and all(s[-1 - suffix] == sequences[0][-1 - suffix] for s in sequences)
    ):
        suffix += 1

    result.common_prefix = prefix
    result.common_suffix = suffix
    result.differing_ops = max(result.total_ops - prefix - suffix, 0)
    return result


def user_families(store: Any, user_id: str, top_n: int = 3, sample: int = 12) -> list[FamilyDiff]:
    """Compare the circuit families a user ran most often.

    Families are grouped by ``profile_hash`` (bucketed qubit count, depth and gate
    composition), which collects the different measurement bases of one experiment.
    """
    families = store.query(
        """
        SELECT p.profile_hash AS profile_hash, COUNT(*) AS runs,
               COUNT(DISTINCT p.exact_hash) AS circuits
        FROM workloads w JOIN pubs p ON p.job_id = w.id
        WHERE w.user_id = ? AND p.profile_hash IS NOT NULL
        GROUP BY p.profile_hash
        ORDER BY runs DESC
        LIMIT ?
        """,
        (user_id, top_n),
    )

    out: list[FamilyDiff] = []
    for family in families:
        hashes = [
            row["exact_hash"]
            for row in store.query(
                """
                SELECT DISTINCT p.exact_hash
                FROM workloads w JOIN pubs p ON p.job_id = w.id
                WHERE w.user_id = ? AND p.profile_hash = ?
                LIMIT ?
                """,
                (user_id, family["profile_hash"], sample),
            )
        ]
        diff = compare_family(store, hashes, family["profile_hash"])
        diff.runs = family["runs"]
        if hashes:
            placeholders = ",".join("?" * len(hashes[:3]))
            diff.sample_names = [
                row["name"]
                for row in store.query(
                    f"SELECT name FROM circuits WHERE exact_hash IN ({placeholders}) "
                    "AND name IS NOT NULL AND name != ''",
                    hashes[:3],
                )
            ]
        out.append(diff)
    return out
