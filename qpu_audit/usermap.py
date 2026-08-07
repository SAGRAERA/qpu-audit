"""Mapping opaque user IDs to real people.

The Qiskit Runtime REST API never returns names or email addresses, not even for
administrators — ``UserFilter`` is ``{"id": ...}`` and ``usage_grouped`` keys are the
same opaque value. Names come from the IBM Cloud account instead (see accounts.py),
and anything that cannot be resolved automatically is filled in by hand here.

See docs/user-mapping.md.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

HEADER = ["user_id", "label", "note"]


@dataclass
class UserMap:
    entries: dict[str, tuple[str, str]]  # user_id -> (label, note)

    def label(self, user_id: str | None) -> str:
        if not user_id:
            return "(unknown)"
        entry = self.entries.get(user_id)
        return entry[0] if entry and entry[0] else short_id(user_id)

    def note(self, user_id: str | None) -> str:
        if not user_id:
            return ""
        entry = self.entries.get(user_id)
        return entry[1] if entry else ""

    def is_mapped(self, user_id: str | None) -> bool:
        return bool(user_id and user_id in self.entries and self.entries[user_id][0])


def short_id(user_id: str) -> str:
    """Compact display form used when no label has been set."""
    return f"{user_id[:8]}…" if len(user_id) > 10 else user_id


def load(path: Path) -> UserMap:
    entries: dict[str, tuple[str, str]] = {}
    if path.is_file():
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                uid = (row.get("user_id") or "").strip()
                if not uid or uid.startswith("#"):
                    continue
                entries[uid] = ((row.get("label") or "").strip(), (row.get("note") or "").strip())
    return UserMap(entries=entries)


def export_template(
    path: Path,
    user_ids: list[str],
    existing: UserMap,
    resolved: dict[str, tuple[str, str]] | None = None,
) -> tuple[int, int]:
    """Write the mapping file for every observed user ID.

    ``resolved`` holds {user_id: (name, note)} looked up from the IBM Cloud account.
    **Hand-written labels always win** — an automatic lookup must never overwrite
    what a person deliberately typed.

    Returns: (rows written, rows filled automatically)
    """
    resolved = resolved or {}
    path.parent.mkdir(parents=True, exist_ok=True)
    written = filled = 0
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        for uid in user_ids:
            label, note = existing.entries.get(uid, ("", ""))
            if not label and uid in resolved:
                label, auto_note = resolved[uid]
                note = note or auto_note
                filled += 1
            writer.writerow([uid, label, note])
            written += 1
    return written, filled
