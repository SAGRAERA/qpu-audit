"""SQLite storage.

IBM does not retain job payloads indefinitely, so the value of this tool comes from
accumulating data locally starting now. The schema is built for incremental upserts.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS workloads (
    id                  TEXT PRIMARY KEY,
    created             TEXT,
    ended               TEXT,
    backend             TEXT,
    instance            TEXT,
    user_id             TEXT,
    mode                TEXT,
    status              TEXT,
    status_reason       TEXT,
    tags                TEXT,
    usage_seconds       REAL,
    usage_status        TEXT,
    estimated_seconds   REAL,
    first_seen          TEXT NOT NULL,
    last_seen           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id                  TEXT PRIMARY KEY,
    created             TEXT,
    backend             TEXT,
    user_id             TEXT,
    session_id          TEXT,
    program             TEXT,
    status              TEXT,
    cost                REAL,
    usage_seconds       REAL,
    estimated_seconds   REAL,
    tags                TEXT,
    private             INTEGER DEFAULT 0,
    params_available    INTEGER DEFAULT 0,
    pub_count           INTEGER DEFAULT 0,
    caller              TEXT,
    exec_time_ns        REAL,
    detail_fetched_at   TEXT
);

CREATE TABLE IF NOT EXISTS pubs (
    job_id              TEXT NOT NULL,
    pub_index           INTEGER NOT NULL,
    exact_hash          TEXT NOT NULL,
    structural_hash     TEXT NOT NULL,
    intent_hash         TEXT,
    profile_hash        TEXT,
    shots               INTEGER,
    param_vector        TEXT,
    PRIMARY KEY (job_id, pub_index)
);

-- Raw QPY bytes. Keeping them means fingerprint rules can change without
-- re-fetching, and evidence outlives IBM's retention window.
CREATE TABLE IF NOT EXISTS pub_payloads (
    job_id              TEXT NOT NULL,
    pub_index           INTEGER NOT NULL,
    payload             BLOB,
    shots               INTEGER,
    param_vector        TEXT,
    param_sig           TEXT,
    observable_sig      TEXT,
    PRIMARY KEY (job_id, pub_index)
);

CREATE TABLE IF NOT EXISTS circuits (
    exact_hash          TEXT PRIMARY KEY,
    structural_hash     TEXT,
    intent_hash         TEXT,
    profile_hash        TEXT,
    qasm                TEXT,
    name                TEXT,
    metadata            TEXT,
    source              TEXT,
    n_qubits            INTEGER,
    n_clbits            INTEGER,
    n_ops               INTEGER,
    n_2q_ops            INTEGER,
    depth               INTEGER,
    has_measure         INTEGER,
    clifford_only       INTEGER,
    parsed              INTEGER,
    gate_histogram      TEXT,
    first_seen          TEXT,
    sample_job_id       TEXT
);

-- Failed job detail fetches. 403 means no permission, 404 means it aged out.
CREATE TABLE IF NOT EXISTS detail_errors (
    job_id              TEXT PRIMARY KEY,
    status              TEXT,
    message             TEXT,
    attempts            INTEGER DEFAULT 1,
    last_attempt_at     TEXT
);

-- Monthly usage ledger. Survives IBM deleting the underlying workloads.
CREATE TABLE IF NOT EXISTS usage_monthly (
    month               TEXT NOT NULL,        -- YYYY-MM
    user_id             TEXT NOT NULL,
    jobs                INTEGER,
    qpu_seconds         REAL,
    backends            INTEGER,
    first_seen          TEXT,
    last_seen           TEXT,
    updated_at          TEXT,
    PRIMARY KEY (month, user_id)
);

-- Same ledger, split by instance. A Premium account has several, and a user who
-- takes over every one of them looks unremarkable in any single instance's numbers.
CREATE TABLE IF NOT EXISTS usage_monthly_instance (
    month               TEXT NOT NULL,        -- YYYY-MM
    user_id             TEXT NOT NULL,
    instance            TEXT NOT NULL,        -- CRN
    jobs                INTEGER,
    qpu_seconds         REAL,
    updated_at          TEXT,
    PRIMARY KEY (month, user_id, instance)
);

CREATE TABLE IF NOT EXISTS meta (
    key                 TEXT PRIMARY KEY,
    value               TEXT
);
"""

# Indexes are created after migration, because CREATE TABLE IF NOT EXISTS will not
# add new columns to an existing table.
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_workloads_user    ON workloads(user_id);
CREATE INDEX IF NOT EXISTS idx_workloads_created ON workloads(created);
CREATE INDEX IF NOT EXISTS idx_jobs_user         ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_pubs_exact        ON pubs(exact_hash);
CREATE INDEX IF NOT EXISTS idx_pubs_structural   ON pubs(structural_hash);
CREATE INDEX IF NOT EXISTS idx_pubs_intent       ON pubs(intent_hash);
CREATE INDEX IF NOT EXISTS idx_usage_month       ON usage_monthly(month);
CREATE INDEX IF NOT EXISTS idx_usage_inst_month  ON usage_monthly_instance(month);
CREATE INDEX IF NOT EXISTS idx_workloads_inst    ON workloads(instance);
"""


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.executescript(INDEXES)
        self.conn.commit()

    def _migrate(self) -> None:
        """Add columns to databases created by older versions."""
        additions = {
            "pubs": [("intent_hash", "TEXT"), ("profile_hash", "TEXT")],
            "circuits": [
                ("intent_hash", "TEXT"), ("profile_hash", "TEXT"), ("name", "TEXT"),
                ("metadata", "TEXT"), ("source", "TEXT"), ("n_clbits", "INTEGER"),
                ("depth", "INTEGER"),
            ],
            "jobs": [("caller", "TEXT"), ("exec_time_ns", "REAL")],
            "pub_payloads": [("param_sig", "TEXT"), ("observable_sig", "TEXT")],
        }
        for table, columns in additions.items():
            existing = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
            for name, sql_type in columns:
                if name not in existing:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # -- meta --------------------------------------------------------------
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    # -- upserts -----------------------------------------------------------
    def upsert_workload(self, row: dict[str, Any], now: str) -> bool:
        """Store one workload. Returns True when it is new."""
        usage = row.get("usage") or {}
        existing = self.conn.execute("SELECT 1 FROM workloads WHERE id = ?", (row["id"],)).fetchone()
        self.conn.execute(
            """
            INSERT INTO workloads (
                id, created, ended, backend, instance, user_id, mode, status,
                status_reason, tags, usage_seconds, usage_status, estimated_seconds,
                first_seen, last_seen
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                ended             = excluded.ended,
                status            = excluded.status,
                status_reason     = excluded.status_reason,
                tags              = excluded.tags,
                usage_seconds     = COALESCE(excluded.usage_seconds, workloads.usage_seconds),
                usage_status      = excluded.usage_status,
                estimated_seconds = COALESCE(excluded.estimated_seconds, workloads.estimated_seconds),
                last_seen         = excluded.last_seen
            """,
            (
                row["id"],
                row.get("created"),
                row.get("ended"),
                row.get("backend"),
                row.get("instance"),
                row.get("user_id"),
                row.get("mode"),
                row.get("status"),
                row.get("status_reason"),
                json.dumps(row.get("tags") or [], ensure_ascii=False),
                usage.get("qpu_charge_time_seconds"),
                usage.get("status"),
                row.get("estimated_running_time_seconds"),
                now,
                now,
            ),
        )
        return existing is None

    def upsert_job_detail(
        self,
        job: dict[str, Any],
        pubs: Sequence[Any],
        params_available: bool,
        now: str,
    ) -> None:
        usage = job.get("usage") or {}
        status = job.get("status")
        if isinstance(status, dict):
            status = status.get("status") or status.get("state")
        program = job.get("program")
        if isinstance(program, dict):
            program = program.get("id")

        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, created, backend, user_id, session_id, program, status,
                    cost, usage_seconds, estimated_seconds, tags, private,
                    params_available, pub_count, detail_fetched_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    status            = excluded.status,
                    usage_seconds     = COALESCE(excluded.usage_seconds, jobs.usage_seconds),
                    params_available  = excluded.params_available,
                    pub_count         = excluded.pub_count,
                    detail_fetched_at = excluded.detail_fetched_at
                """,
                (
                    job.get("id"),
                    job.get("created"),
                    job.get("backend"),
                    job.get("user_id"),
                    job.get("session_id"),
                    program,
                    status,
                    job.get("cost"),
                    usage.get("qpu_charge_time_seconds"),
                    job.get("estimated_running_time_seconds"),
                    json.dumps(job.get("tags") or [], ensure_ascii=False),
                    1 if job.get("private") else 0,
                    1 if params_available else 0,
                    len(pubs),
                    now,
                ),
            )
            job_id = job.get("id")
            conn.execute("DELETE FROM pubs WHERE job_id = ?", (job_id,))
            for pub in pubs:
                self._write_pub(conn, job_id, pub, now)
                if pub.payload is not None:
                    conn.execute(
                        "INSERT OR REPLACE INTO pub_payloads "
                        "(job_id, pub_index, payload, shots, param_vector, param_sig, "
                        " observable_sig) VALUES (?,?,?,?,?,?,?)",
                        (
                            job_id,
                            pub.index,
                            pub.payload,
                            pub.shots,
                            json.dumps(pub.param_vector),
                            pub.param_sig,
                            pub.observable_sig,
                        ),
                    )
            conn.execute("DELETE FROM detail_errors WHERE job_id = ?", (job_id,))

    @staticmethod
    def _write_pub(conn: sqlite3.Connection, job_id: str, pub: Any, now: str) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO pubs "
            "(job_id, pub_index, exact_hash, structural_hash, intent_hash, profile_hash, "
            " shots, param_vector) VALUES (?,?,?,?,?,?,?,?)",
            (
                job_id,
                pub.index,
                pub.exact_hash,
                pub.structural_hash,
                pub.intent_hash,
                pub.profile_hash,
                pub.shots,
                json.dumps(pub.param_vector),
            ),
        )
        conn.execute(
            """
            INSERT INTO circuits (
                exact_hash, structural_hash, intent_hash, profile_hash, qasm, name, metadata,
                source, n_qubits, n_clbits, n_ops, n_2q_ops, depth, has_measure,
                clifford_only, parsed, gate_histogram, first_seen, sample_job_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(exact_hash) DO NOTHING
            """,
            (
                pub.exact_hash,
                pub.structural_hash,
                pub.intent_hash,
                pub.profile_hash,
                pub.qasm,
                pub.stats.name,
                json.dumps(pub.stats.metadata, ensure_ascii=False, default=str),
                pub.stats.source,
                pub.stats.n_qubits,
                pub.stats.n_clbits,
                pub.stats.n_ops,
                pub.stats.n_2q_ops,
                pub.stats.depth,
                1 if pub.stats.has_measure else 0,
                1 if pub.stats.clifford_only else 0,
                1 if pub.stats.parsed else 0,
                json.dumps(pub.stats.gate_histogram, ensure_ascii=False),
                now,
                job_id,
            ),
        )

    def record_detail_error(self, job_id: str, status: str, message: str, now: str) -> None:
        self.conn.execute(
            """
            INSERT INTO detail_errors (job_id, status, message, attempts, last_attempt_at)
            VALUES (?,?,?,1,?)
            ON CONFLICT(job_id) DO UPDATE SET
                status          = excluded.status,
                message         = excluded.message,
                attempts        = detail_errors.attempts + 1,
                last_attempt_at = excluded.last_attempt_at
            """,
            (job_id, status, message[:500], now),
        )
        self.conn.commit()

    # -- queries -----------------------------------------------------------
    def jobs_needing_detail(self, limit: int, max_attempts: int = 3) -> list[str]:
        """Workload IDs with no detail yet, newest first, skipping repeated failures."""
        rows = self.conn.execute(
            """
            SELECT w.id
            FROM workloads w
            LEFT JOIN jobs j          ON j.id = w.id
            LEFT JOIN detail_errors e ON e.job_id = w.id
            WHERE w.mode = 'job'
              AND j.detail_fetched_at IS NULL
              AND COALESCE(e.attempts, 0) < ?
            ORDER BY w.created DESC
            LIMIT ?
            """,
            (max_attempts, limit),
        ).fetchall()
        return [r["id"] for r in rows]

    def jobs_needing_refresh(self, limit: int) -> list[str]:
        """Jobs already fetched but not yet terminal — usage is finalised later."""
        rows = self.conn.execute(
            """
            SELECT id FROM jobs
            WHERE detail_fetched_at IS NOT NULL
              AND LOWER(COALESCE(status, '')) NOT IN ('completed','cancelled','canceled','failed')
            ORDER BY created DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [r["id"] for r in rows]

    def update_metrics(self, job_id: str, caller: str | None, exec_time_ns: float | None) -> None:
        self.conn.execute(
            "UPDATE jobs SET caller = COALESCE(?, caller), exec_time_ns = COALESCE(?, exec_time_ns) "
            "WHERE id = ?",
            (caller, exec_time_ns, job_id),
        )
        self.conn.commit()

    # -- reindexing (recompute fingerprints without API calls) -------------
    def payload_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS n FROM pub_payloads").fetchone()["n"]

    def iter_payloads(self) -> Iterator[sqlite3.Row]:
        cursor = self.conn.execute(
            "SELECT job_id, pub_index, payload, shots, param_vector, param_sig, observable_sig "
            "FROM pub_payloads ORDER BY job_id, pub_index"
        )
        while True:
            rows = cursor.fetchmany(200)
            if not rows:
                return
            yield from rows

    def reset_derived(self) -> None:
        """Clear fingerprint tables only. Raw payloads and workloads are kept."""
        with self.tx() as conn:
            conn.execute("DELETE FROM circuits")
            conn.execute("DELETE FROM pubs")

    def write_pub(self, job_id: str, pub: Any, now: str) -> None:
        self._write_pub(self.conn, job_id, pub, now)

    def clear_details(self) -> int:
        """Mark every job detail for re-fetching (used when fingerprint rules change).

        The workload listing is left alone, so no list re-sync happens.
        """
        with self.tx() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE detail_fetched_at IS NOT NULL"
            ).fetchone()["n"]
            conn.execute("UPDATE jobs SET detail_fetched_at = NULL")
            conn.execute("DELETE FROM detail_errors")
        return count

    def jobs_missing_payloads(self, limit: int) -> list[str]:
        """Jobs with details but no stored payload (collected by an older version)."""
        rows = self.conn.execute(
            """
            SELECT j.id FROM jobs j
            LEFT JOIN pub_payloads p ON p.job_id = j.id
            WHERE j.detail_fetched_at IS NOT NULL AND j.pub_count > 0 AND p.job_id IS NULL
            ORDER BY j.created DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [r["id"] for r in rows]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for table in ("workloads", "jobs", "pubs", "circuits", "detail_errors"):
            out[table] = self.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        out["users"] = self.conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS n FROM workloads WHERE user_id IS NOT NULL"
        ).fetchone()["n"]
        return out

    def query(self, sql: str, args: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, args).fetchall()
