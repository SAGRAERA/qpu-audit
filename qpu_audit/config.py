"""Configuration loading.

Credentials come from .env (or real environment variables); tuning comes from
config/config.toml. The two are kept strictly apart: .env is git-ignored, while
config.toml is a shareable tuning file.
"""

from __future__ import annotations

import copy
import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: dict[str, Any] = {
    "collect": {
        "lookback_days": 30,
        "job_detail_max_per_run": 500,
        "request_timeout": 30,
        "max_retries": 5,
        "page_size": 200,
    },
    "analyze": {
        "window_days": 30,
        "whitelist": [],
    },
    "rules": {
        "min_repeats_for_flag": 5,
        "short_interval_minutes": 30,
        "interval_regularity_cv": 0.20,
        "interval_min_samples": 8,
        "convergence_ratio": 0.60,
        "waste_seconds_warn": 300.0,
        "top_circuit_share_warn": 0.50,
        "unique_ratio_warn": 0.30,
        "overuse_share_floor": 0.30,
        "overuse_share_full": 0.50,
        "usage_spike_ratio": 2.0,
        "burst_size_warn": 10,
    },
    "score": {
        # waste (60) — QPU burned on nothing
        "duplicate_waste": 30,
        "top_circuit_share": 15,
        "trivial_circuit": 10,
        "failure_resubmit": 5,
        # queue (20) — harm to others regardless of whether the work is legitimate
        "burst_submission": 12,
        "no_session": 8,
        # context (20) — information only
        "overuse": 12,
        "regular_interval": 5,
        "usage_spike": 3,
    },
    "report": {
        "top_users": 20,
        "top_circuits_per_user": 5,
        "qasm_snippet_lines": 40,
    },
}


class ConfigError(RuntimeError):
    """Configuration is missing or invalid."""


def _parse_env_file(path: Path) -> dict[str, str]:
    """Read .env without a dependency. Supports KEY=value, # comments, quotes."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass
class Instance:
    """One Qiskit Runtime service instance.

    A Premium account typically holds several, each with its own CRN. The API selects
    one per request through the ``Service-CRN`` header, so auditing all of them means
    iterating over CRNs with the same key.
    """

    name: str
    crn: str

    @property
    def short(self) -> str:
        """Last CRN segment — enough to tell instances apart when unnamed."""
        parts = [p for p in self.crn.split(":") if p]
        return parts[-1][:12] if parts else self.crn[:12]


def write_instances(root: Path, instances: list[Instance], header: str = "") -> Path:
    """Rewrite config/instances.toml.

    Names already present are the caller's responsibility to preserve — a name typed
    by a person always beats one fetched from an API.
    """
    path = root / "config" / "instances.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Qiskit Runtime instances audited by qpu-audit.",
        "# git-ignored: a CRN contains your IBM Cloud account ID.",
        "#",
        "# `name` is yours to choose - it appears in reports and in --instance <name>.",
    ]
    if header:
        lines += ["#", *(f"# {line}" for line in header.splitlines())]
    lines.append("")
    for inst in instances:
        lines += ["[[instance]]", f'name = "{inst.name}"', f'crn  = "{inst.crn}"', ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _load_instances(root: Path, fallback_crn: str) -> list[Instance]:
    """Read config/instances.toml, falling back to the single CRN from .env."""
    path = root / "config" / "instances.toml"
    instances: list[Instance] = []
    if path.is_file():
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        for entry in data.get("instance", []) or []:
            crn = str(entry.get("crn", "")).strip()
            if not crn:
                continue
            name = str(entry.get("name", "")).strip() or crn.split(":")[-2][:12]
            instances.append(Instance(name=name, crn=crn))
    if not instances and fallback_crn:
        instances.append(Instance(name="default", crn=fallback_crn))
    return instances


@dataclass
class Settings:
    api_key: str
    crn: str
    base_url: str = "https://quantum.cloud.ibm.com/api"
    api_version: str = "2025-05-01"
    auth_mode: str = "apikey"
    iam_url: str = "https://iam.cloud.ibm.com/identity/token"
    root: Path = PROJECT_ROOT
    tuning: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULTS))
    instances: list[Instance] = field(default_factory=list)

    @property
    def instance_names(self) -> dict[str, str]:
        """CRN -> friendly name, for reports."""
        return {i.crn: i.name for i in self.instances}

    def for_instance(self, instance: Instance) -> "Settings":
        """A copy pointed at one instance. Only the CRN header differs."""
        return replace(self, crn=instance.crn)

    # -- derived paths -----------------------------------------------------
    @property
    def db_path(self) -> Path:
        return self.root / "data" / "audit.db"

    @property
    def user_map_path(self) -> Path:
        return self.root / "config" / "user_map.csv"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    def section(self, name: str) -> dict[str, Any]:
        return self.tuning.get(name, {})

    def ensure_credentials(self) -> None:
        if not self.api_key:
            raise ConfigError(
                "Missing credentials: IBM_QUANTUM_API_KEY\n"
                "Copy .env.example to .env and fill it in.\n"
                f"  Path: {self.root / '.env'}"
            )
        if not self.instances:
            raise ConfigError(
                "No instance configured. Set IBM_QUANTUM_CRN in .env, or list several "
                "instances in config/instances.toml (see config/instances.example.toml).\n"
                f"  Path: {self.root / 'config' / 'instances.toml'}"
            )


def load_settings(root: Path | None = None) -> Settings:
    """Assemble settings from .env, real environment variables, and config.toml."""
    root = root or PROJECT_ROOT
    file_env = _parse_env_file(root / ".env")

    def pick(key: str, default: str = "") -> str:
        # Real environment variables take precedence over .env
        return os.environ.get(key) or file_env.get(key) or default

    tuning = copy.deepcopy(DEFAULTS)
    toml_path = root / "config" / "config.toml"
    if toml_path.is_file():
        with toml_path.open("rb") as fh:
            tuning = _deep_merge(tuning, tomllib.load(fh))

    auth_mode = pick("IBM_QUANTUM_AUTH_MODE", "apikey").strip().lower()
    if auth_mode not in {"apikey", "iam"}:
        raise ConfigError(
            f"IBM_QUANTUM_AUTH_MODE must be 'apikey' or 'iam' (got {auth_mode!r})"
        )

    crn = pick("IBM_QUANTUM_CRN").strip()
    instances = _load_instances(root, crn)

    return Settings(
        api_key=pick("IBM_QUANTUM_API_KEY").strip(),
        # Default request CRN. Multi-instance commands iterate over `instances`.
        crn=crn or (instances[0].crn if instances else ""),
        base_url=pick("IBM_QUANTUM_BASE_URL", "https://quantum.cloud.ibm.com/api").rstrip("/"),
        api_version=pick("IBM_QUANTUM_API_VERSION", "2025-05-01").strip(),
        auth_mode=auth_mode,
        iam_url=pick("IBM_IAM_URL", "https://iam.cloud.ibm.com/identity/token").strip(),
        root=root,
        tuning=tuning,
        instances=instances,
    )
