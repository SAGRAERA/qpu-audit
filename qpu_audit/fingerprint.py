"""Circuit fingerprinting.

Deciding whether someone is repeating a circuit requires defining "the same circuit"
at several levels. Bytes alone are useless: when a circuit is re-transpiled on each
submission the gate sequence changes every time.

  exact_hash       gate sequence + parameters + observables + shots.
                   The identical execution. Repeats mean nothing was changed.

  structural_hash  gate sequence with rotation angles masked.
                   Groups a VQE ansatz across its parameter sweep.

  intent_hash      circuit name + metadata.
                   **Unaffected by re-transpilation.** Qiskit's experiment modules
                   name circuits after what they are (StateTomography_(...),
                   meas_mit_cal_0000000), which identifies a re-run of the same
                   experiment. Auto-generated names like 'circuit-61' are reused
                   across unrelated circuits and are distrusted (value: None).

  profile_hash     bucketed qubit count, depth and 2-qubit gate count.
                   Survives small re-transpilation differences. Weak evidence, used
                   for grouping similar circuits only.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

from . import qpy

CLIFFORD_GATES = {
    "i", "id", "x", "y", "z", "h", "s", "sdg", "sx", "sxdg",
    "cx", "cz", "cy", "swap", "barrier", "measure", "reset",
}
PARAM_ROTATIONS = {"rx", "ry", "rz", "p", "u1", "crz", "cp"}

_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"//[^\n]*")
_DECL = re.compile(
    r"\b(qubit|bit|qreg|creg)\b\s*(?:\[\s*(\d+)\s*\])?\s*([A-Za-z_]\w*)\s*(?:\[\s*(\d+)\s*\])?"
)
_STMT_HEAD = re.compile(r"^([A-Za-z_]\w*)")
_INNER_PARENS = re.compile(r"\(([^()]*)\)")
_QASM_MARKER = re.compile(r"\bOPENQASM\b", re.IGNORECASE)

NON_GATE_KEYWORDS = {
    "openqasm", "include", "qubit", "bit", "qreg", "creg", "gate", "def",
    "input", "output", "const", "let", "int", "uint", "float", "bool",
    "angle", "complex", "duration", "stretch", "extern", "pragma", "defcalgrammar",
}

# Bucket width for profile_hash. 1.15 groups values into roughly 15% bands.
_BUCKET_BASE = 1.15

_PAULI = re.compile(r"^[IXYZ]{2,}$")


@dataclass
class CircuitStats:
    n_qubits: int = 0
    n_clbits: int = 0
    n_ops: int = 0
    n_2q_ops: int = 0
    depth: int = 0
    has_measure: bool = False
    clifford_only: bool = False
    gate_histogram: dict[str, int] = field(default_factory=dict)
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "unparsed"
    parsed: bool = False


@dataclass
class Pub:
    """One execution unit (pub) inside a job.

    The pub layout differs per primitive::

        sampler    [circuit, parameter_values, shots]
        estimator  [circuit, observables, parameter_values, precision]

    The second slot is **observables** for estimator, not parameters. Reading it as
    parameters collapses distinct observable measurements into one execution, which
    turns a legitimate observable scan into apparent repetition.
    """

    index: int
    exact_hash: str
    structural_hash: str
    profile_hash: str
    intent_hash: str | None
    shots: int | None
    param_vector: list[float]
    stats: CircuitStats
    qasm: str | None = None
    payload: bytes | None = None
    # Stored alongside the payload so reindexing reproduces identical hashes.
    param_sig: str = ""
    observable_sig: str = ""


# ---------------------------------------------------------------------------
# hashing helpers
# ---------------------------------------------------------------------------

def _sha(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _bucket(value: int) -> int:
    """Collapse similar magnitudes into one bucket."""
    if value <= 0:
        return 0
    return int(math.log(value) / math.log(_BUCKET_BASE))


def _profile(stats: CircuitStats) -> str:
    return _sha(
        str(stats.n_qubits),
        str(stats.n_clbits),
        str(int(stats.has_measure)),
        str(_bucket(stats.depth)),
        str(_bucket(stats.n_2q_ops)),
        str(_bucket(stats.n_ops)),
        ",".join(sorted(stats.gate_histogram)),
    )


def _intent(stats: CircuitStats) -> str | None:
    """Experiment-identity fingerprint. None when it cannot be trusted."""
    probe = qpy.DecodedCircuit(name=stats.name)
    has_useful_name = bool(stats.name) and not probe.name_is_generic
    if not has_useful_name and not stats.metadata:
        return None
    return _sha(stats.name if has_useful_name else "", _canonical(stats.metadata))


def _flatten_floats(value: Any, out: list[float], limit: int = 256) -> None:
    if len(out) >= limit:
        return
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        out.append(float(value))
    elif isinstance(value, dict):
        for key in sorted(value):
            _flatten_floats(value[key], out, limit)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _flatten_floats(item, out, limit)


# ---------------------------------------------------------------------------
# QASM path (circuits submitted as text)
# ---------------------------------------------------------------------------

def _strip_comments(text: str) -> str:
    return _COMMENT_LINE.sub("", _COMMENT_BLOCK.sub("", text))


def _register_map(text: str) -> dict[str, str]:
    """Rename registers in declaration order, so renaming cannot disguise a circuit."""
    mapping: dict[str, str] = {}
    q_index = c_index = 0
    for kind, _size_a, name, _size_b in _DECL.findall(text):
        if name in mapping:
            continue
        if kind in ("qubit", "qreg"):
            mapping[name] = f"__q{q_index}"
            q_index += 1
        else:
            mapping[name] = f"__c{c_index}"
            c_index += 1
    return mapping


def _apply_register_map(text: str, mapping: dict[str, str]) -> str:
    if not mapping:
        return text
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)) + r")\b"
    )
    return pattern.sub(lambda m: mapping[m.group(1)], text)


def _mask_angles(text: str) -> str:
    prev = None
    out = text
    while prev != out:
        prev = out
        out = _INNER_PARENS.sub("(*)", out)
    return out


def _is_clifford_angle(arg: str) -> bool:
    """An rz(pi/2)-style angle is Clifford when it is a multiple of pi/2."""
    expr = arg.strip().lower().replace(" ", "")
    if expr in {"0", "0.0"}:
        return True
    m = re.fullmatch(r"([-+]?\d*\.?\d*)\*?pi(?:/(\d+))?", expr)
    if not m:
        return False
    coeff_raw, denom_raw = m.group(1), m.group(2)
    try:
        coeff = float(coeff_raw) if coeff_raw not in ("", "+", "-") else float(f"{coeff_raw}1")
        denom = float(denom_raw) if denom_raw else 1.0
    except ValueError:
        return False
    multiples = coeff / denom * 2.0
    return abs(multiples - round(multiples)) < 1e-9


def _statements(text: str) -> list[str]:
    return [s.strip() for s in text.split(";") if s.strip()]


def normalize_qasm(qasm: str) -> tuple[str, str, CircuitStats]:
    """QASM text -> (normalised, angle-masked, statistics)."""
    text = _strip_comments(qasm)
    mapping = _register_map(text)
    stats = CircuitStats(parsed=True, source="qasm")

    for kind, size_a, _name, size_b in _DECL.findall(text):
        size = size_a or size_b or "1"
        try:
            count = int(size)
        except ValueError:
            count = 1
        if kind in ("qubit", "qreg"):
            stats.n_qubits += count
        else:
            stats.n_clbits += count

    kept: list[str] = []
    non_clifford = False
    for stmt in _statements(_apply_register_map(text, mapping)):
        head_match = _STMT_HEAD.match(stmt)
        head = head_match.group(1).lower() if head_match else ""
        if head in ("openqasm", "include"):
            continue
        kept.append(re.sub(r"\s+", " ", stmt))
        if head in NON_GATE_KEYWORDS or not head:
            continue

        stats.n_ops += 1
        stats.gate_histogram[head] = stats.gate_histogram.get(head, 0) + 1
        if head == "measure":
            stats.has_measure = True
            continue
        if head == "barrier":
            continue

        operand_part = _INNER_PARENS.sub("", stmt)
        if len(re.findall(r"__q\d+", operand_part)) >= 2:
            stats.n_2q_ops += 1

        if head in PARAM_ROTATIONS:
            args = _INNER_PARENS.search(stmt)
            if not args or not all(_is_clifford_angle(a) for a in args.group(1).split(",")):
                non_clifford = True
        elif head not in CLIFFORD_GATES:
            non_clifford = True

    normalized = "\n".join(kept)
    stats.clifford_only = stats.n_ops > 0 and not non_clifford
    stats.depth = stats.n_ops  # true depth is unknown on the QASM path
    return normalized, _mask_angles(normalized), stats


# ---------------------------------------------------------------------------
# pub extraction
# ---------------------------------------------------------------------------

def _find_qasm(value: Any) -> str | None:
    if isinstance(value, str):
        return value if _QASM_MARKER.search(value) else None
    if isinstance(value, dict):
        for key in ("circuit", "qasm", "value"):
            if key in value:
                found = _find_qasm(value[key])
                if found:
                    return found
        for item in value.values():
            found = _find_qasm(item)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _find_qasm(item)
            if found:
                return found
    return None


def _find_payload(value: Any) -> Any:
    """Locate a QPY-serialised circuit element."""
    if qpy.looks_like_payload(value):
        return value
    if isinstance(value, dict):
        for item in value.values():
            found = _find_payload(item)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _find_payload(item)
            if found is not None:
                return found
    return None


def _looks_like_observables(value: Any) -> bool:
    """A mapping keyed by Pauli strings."""
    if isinstance(value, dict) and value:
        keys = [k for k in value if isinstance(k, str)]
        if not keys:
            return False
        return all(_PAULI.match(k) for k in keys[:8])
    if isinstance(value, (list, tuple)) and value:
        return all(_looks_like_observables(v) for v in value[:4])
    return False


def _is_ndarray(value: Any) -> bool:
    return isinstance(value, dict) and str(value.get("__type__", "")).lower() == "ndarray"


def _numeric_container(value: Any) -> bool:
    if isinstance(value, (list, tuple)):
        return bool(value) and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) or _numeric_container(v)
            for v in value[:8]
        )
    return False


def _classify_pub(element: Any) -> tuple[Any, Any, Any, int | None]:
    """Split a pub into (circuit, observables, parameters, shots).

    Classification is by content, not slot position — layouts differ per primitive
    and may change again.
    """
    circuit = observables = parameters = None
    shots: int | None = None

    items = list(element) if isinstance(element, (list, tuple)) else [element]
    for item in items:
        if circuit is None and (qpy.looks_like_payload(item) or _find_qasm(item)):
            circuit = item
        elif observables is None and _looks_like_observables(item):
            observables = item
        elif parameters is None and (_is_ndarray(item) or _numeric_container(item)):
            parameters = item
        elif shots is None and isinstance(item, int) and not isinstance(item, bool):
            shots = item

    if isinstance(element, dict):
        for key in ("parameter_values", "parameter_bindings", "params", "bindings"):
            if key in element:
                parameters = element[key]
                break
        for key in ("observables", "observable"):
            if key in element:
                observables = element[key]
                break
        if isinstance(element.get("shots"), int):
            shots = element["shots"]

    return circuit, observables, parameters, shots


def _signature(value: Any) -> str:
    """Stable signature for hashing. ndarray payloads use their serialised form."""
    if value is None:
        return ""
    if _is_ndarray(value):
        return _sha("ndarray", str(value.get("__value__", "")))
    return _sha(_canonical(value))


def _default_shots(params: dict[str, Any]) -> int | None:
    options = params.get("options")
    if isinstance(options, dict):
        for key in ("default_shots", "shots"):
            value = options.get(key)
            if isinstance(value, int):
                return value
        execution = options.get("execution")
        if isinstance(execution, dict) and isinstance(execution.get("shots"), int):
            return execution["shots"]
    if isinstance(params.get("shots"), int):
        return params["shots"]
    return None


def _pub_elements(params: dict[str, Any]) -> list[Any]:
    for key in ("pubs", "circuits", "tasks"):
        value = params.get(key)
        if isinstance(value, list) and value:
            return value
    if _find_qasm(params) or _find_payload(params):
        return [params]
    return []


def _stats_from_decoded(decoded: qpy.DecodedCircuit) -> CircuitStats:
    # Transpiled circuits contain rz with arbitrary angles and are rarely Clifford.
    # Angles are not inspected here, so this stays conservative.
    gates = set(decoded.gate_histogram)
    clifford_only = bool(gates) and gates <= CLIFFORD_GATES
    return CircuitStats(
        n_qubits=decoded.n_qubits,
        n_clbits=decoded.n_clbits,
        n_ops=decoded.n_instructions,
        n_2q_ops=decoded.n_2q_ops,
        depth=decoded.depth,
        has_measure=decoded.has_measure,
        clifford_only=clifford_only,
        gate_histogram=decoded.gate_histogram,
        name=decoded.name,
        metadata=decoded.metadata,
        source=decoded.source,
        parsed=decoded.parsed,
    )


def _strip_numeric(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return "*"
    if isinstance(value, dict):
        return {k: _strip_numeric(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_strip_numeric(v) for v in value]
    return value


def _build_pub(index: int, element: Any, fallback_shots: int | None, keep_payload: bool) -> Pub:
    circuit_holder, observables, param_source, pub_shots = _classify_pub(element)
    shots = pub_shots if pub_shots is not None else fallback_shots

    param_vector: list[float] = []
    _flatten_floats(param_source, param_vector)
    param_sig = _signature(param_source)
    observable_sig = _signature(observables)

    payload_holder = _find_payload(circuit_holder if circuit_holder is not None else element)
    qasm_text = None if payload_holder is not None else _find_qasm(element)
    payload_bytes: bytes | None = None

    if payload_holder is not None:
        payload_bytes = qpy.payload_bytes(payload_holder)
        decoded = qpy.decode(payload_holder)
        if decoded is not None:
            stats = _stats_from_decoded(decoded)
            if decoded.canonical:
                normalized, masked = decoded.canonical, decoded.masked
            else:
                # Header-only decode: the gate sequence is unknown, so fall back to
                # the raw bytes.
                digest = hashlib.sha256(payload_bytes or b"").hexdigest()
                normalized = digest
                masked = _canonical([stats.name, stats.metadata, stats.n_qubits, stats.n_ops])
        else:
            stats = CircuitStats(source="undecodable")
            normalized = hashlib.sha256(payload_bytes or b"").hexdigest()
            masked = normalized
    elif qasm_text:
        normalized, masked, stats = normalize_qasm(qasm_text)
    else:
        stats = CircuitStats(source="unknown")
        normalized = _canonical(element)
        masked = _canonical(_strip_numeric(element))

    return Pub(
        index=index,
        # Different observables mean a different execution. Leaving them out turns
        # a normal estimator observable scan into apparent repetition.
        exact_hash=_sha(normalized, param_sig, observable_sig, str(shots)),
        structural_hash=_sha(masked),
        profile_hash=_profile(stats),
        intent_hash=_intent(stats),
        shots=shots,
        param_vector=param_vector,
        stats=stats,
        qasm=qasm_text,
        payload=payload_bytes if keep_payload else None,
        param_sig=param_sig,
        observable_sig=observable_sig,
    )


def fingerprint_params(params: Any, keep_payload: bool = False) -> list[Pub]:
    """Fingerprint every pub in a job's ``params``.

    Returns an empty list when params are absent (for example a private job).
    """
    if not isinstance(params, dict) or not params:
        return []
    fallback_shots = _default_shots(params)
    return [
        _build_pub(index, element, fallback_shots, keep_payload)
        for index, element in enumerate(_pub_elements(params))
    ]


def fingerprint_payload(
    index: int,
    data: bytes,
    shots: int | None,
    param_vector: list[float],
    param_sig: str = "",
    observable_sig: str = "",
) -> Pub:
    """Rebuild a fingerprint from stored QPY bytes (reindex path, no API calls)."""
    decoded = qpy.decode_bytes(data)
    if decoded is not None:
        stats = _stats_from_decoded(decoded)
        if decoded.canonical:
            normalized, masked = decoded.canonical, decoded.masked
        else:
            normalized = hashlib.sha256(data).hexdigest()
            masked = _canonical([stats.name, stats.metadata, stats.n_qubits, stats.n_ops])
    else:
        stats = CircuitStats(source="undecodable")
        normalized = hashlib.sha256(data).hexdigest()
        masked = normalized

    return Pub(
        index=index,
        exact_hash=_sha(normalized, param_sig, observable_sig, str(shots)),
        structural_hash=_sha(masked),
        profile_hash=_profile(stats),
        intent_hash=_intent(stats),
        shots=shots,
        param_vector=param_vector,
        stats=stats,
        param_sig=param_sig,
        observable_sig=observable_sig,
    )
