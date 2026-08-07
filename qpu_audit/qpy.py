"""Decoding QPY (Qiskit serialisation) payloads.

Qiskit Runtime does not send OpenQASM. It sends::

    {"__type__": "QuantumCircuit", "__value__": "<base64(zlib(QPY))>"}

Hashing those bytes is useless on its own: **a circuit re-transpiled at each
submission produces different bytes every time**, because routing and gate ordering
follow whatever layout was chosen. So decoding happens at two levels.

  header scrape   circuit name, metadata, qubit/clbit and instruction counts.
                  No qiskit required, and **unaffected by re-transpilation**, which
                  makes it the reliable way to identify *what experiment this is*.

  qiskit decode   full gate sequence, depth, 2-qubit gate counts, histograms.
                  Used when qiskit is installed; everything degrades to the header
                  path when it is not.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any

QPY_MAGIC = b"QISKIT"
_FILE_HEADER = struct.Struct("!6sBBBBQ")  # preface, qpy_ver, major, minor, patch, num_circuits

# The CIRCUIT_HEADER tail differs by QPY version. Try each layout and let the
# metadata JSON parse decide which one is correct.
_CIRCUIT_HEADERS = (
    struct.Struct("!HcHIIQIQI"),  # v12+ (includes num_vars)
    struct.Struct("!HcHIIQIQ"),   # v5..v11
)

# Auto-generated names get reused across unrelated circuits, so they identify
# nothing. Confirmed against real data.
_GENERIC_NAME = re.compile(r"^(circuit|qc)[-_]?\d*$", re.IGNORECASE)


@dataclass
class DecodedCircuit:
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    n_qubits: int = 0
    n_clbits: int = 0
    n_instructions: int = 0
    depth: int = 0
    n_2q_ops: int = 0
    has_measure: bool = False
    gate_histogram: dict[str, int] = field(default_factory=dict)
    qasm: str | None = None
    source: str = "qpy-header"   # qpy-header | qiskit | raw
    # Normalised gate sequence. Only populated on the qiskit path.
    canonical: str = ""          # with parameter values
    masked: str = ""             # rotation angles replaced by a placeholder

    @property
    def name_is_generic(self) -> bool:
        """True when the name says nothing about which experiment this is."""
        return not self.name or bool(_GENERIC_NAME.match(self.name))

    @property
    def parsed(self) -> bool:
        return self.source in ("qpy-header", "qiskit")


def looks_like_payload(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("__value__"), str)
        and "Circuit" in str(value.get("__type__", ""))
    )


def _raw_bytes(blob: str) -> bytes | None:
    try:
        raw = base64.b64decode(blob, validate=False)
    except (binascii.Error, ValueError):
        return None
    if raw[:6] == QPY_MAGIC:
        return raw
    try:
        data = zlib.decompress(raw)
    except zlib.error:
        return raw or None
    return data


def _scrape_header(data: bytes) -> DecodedCircuit | None:
    """Read the file header and the first circuit header. Gates are not touched."""
    if len(data) < _FILE_HEADER.size or data[:6] != QPY_MAGIC:
        return None
    try:
        _, _qpy_version, _maj, _min, _patch, num_circuits = _FILE_HEADER.unpack_from(data, 0)
    except struct.error:
        return None
    if num_circuits < 1:
        return None

    offset = _FILE_HEADER.size
    for layout in _CIRCUIT_HEADERS:
        try:
            fields = layout.unpack_from(data, offset)
        except struct.error:
            continue
        name_size, _gp_type, gp_size, n_qubits, n_clbits, metadata_size = fields[:6]
        n_instructions = fields[7]

        # Implausible values mean this is the wrong layout.
        if name_size > 4096 or metadata_size > 1 << 20 or n_qubits > 100_000:
            continue

        cursor = offset + layout.size
        name_bytes = data[cursor : cursor + name_size]
        cursor += name_size + gp_size
        metadata_bytes = data[cursor : cursor + metadata_size]
        if len(metadata_bytes) < metadata_size:
            continue

        metadata: dict[str, Any] = {}
        if metadata_size:
            try:
                loaded = json.loads(metadata_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue  # layout mismatch — try the next one
            metadata = loaded if isinstance(loaded, dict) else {"_": loaded}

        return DecodedCircuit(
            name=name_bytes.decode("utf-8", errors="replace"),
            metadata=metadata,
            n_qubits=n_qubits,
            n_clbits=n_clbits,
            n_instructions=n_instructions,
            source="qpy-header",
        )
    return None


def _render_param(value: Any) -> str:
    """Stable string form of a gate parameter, with float noise truncated."""
    if isinstance(value, (int, float)):
        return f"{float(value):.9g}"
    return str(value)


def _decode_with_qiskit(data: bytes) -> DecodedCircuit | None:
    """Full gate-level decode. Returns None when qiskit is absent or the load fails."""
    try:
        import io

        from qiskit import qpy as qiskit_qpy
    except ImportError:
        return None

    try:
        circuits = qiskit_qpy.load(io.BytesIO(data))
    except Exception:  # noqa: BLE001 - version mismatches fall back to the header path
        return None
    if not circuits:
        return None

    circuit = circuits[0]
    histogram: dict[str, int] = {}
    n_2q = 0
    has_measure = False

    # find_bit has a per-call cost; build the index once per circuit.
    qubit_index = {bit: i for i, bit in enumerate(circuit.qubits)}
    canonical_lines: list[str] = []
    masked_lines: list[str] = []

    for instruction in circuit.data:
        op_name = instruction.operation.name
        histogram[op_name] = histogram.get(op_name, 0) + 1
        if op_name == "measure":
            has_measure = True
        elif op_name != "barrier" and len(instruction.qubits) >= 2:
            n_2q += 1

        targets = ",".join(str(qubit_index.get(q, -1)) for q in instruction.qubits)
        params = instruction.operation.params
        if params:
            rendered = ",".join(_render_param(p) for p in params)
            canonical_lines.append(f"{op_name}({rendered}) {targets}")
            masked_lines.append(f"{op_name}(*) {targets}")
        else:
            canonical_lines.append(f"{op_name} {targets}")
            masked_lines.append(f"{op_name} {targets}")

    metadata = circuit.metadata if isinstance(circuit.metadata, dict) else {}
    try:
        depth = int(circuit.depth())
    except Exception:  # noqa: BLE001
        depth = 0

    return DecodedCircuit(
        name=str(circuit.name or ""),
        metadata=metadata,
        n_qubits=int(circuit.num_qubits),
        n_clbits=int(circuit.num_clbits),
        n_instructions=len(circuit.data),
        depth=depth,
        n_2q_ops=n_2q,
        has_measure=has_measure,
        gate_histogram=histogram,
        source="qiskit",
        canonical="\n".join(canonical_lines),
        masked="\n".join(masked_lines),
    )


def payload_bytes(value: Any) -> bytes | None:
    """Raw QPY bytes for storage, so fingerprints can be recomputed without the API."""
    blob = value.get("__value__") if isinstance(value, dict) else value
    if not isinstance(blob, str):
        return None
    return _raw_bytes(blob)


def _combine(rich: DecodedCircuit | None, header: DecodedCircuit | None) -> DecodedCircuit | None:
    if rich and header:
        # qiskit is more precise, but name and metadata are closest to the wire in
        # the header.
        rich.name = rich.name or header.name
        if not rich.metadata:
            rich.metadata = header.metadata
        return rich
    return rich or header


def decode(value: Any) -> DecodedCircuit | None:
    """Decode a circuit payload. Returns None on failure."""
    blob = value.get("__value__") if isinstance(value, dict) else value
    if not isinstance(blob, str):
        return None
    data = _raw_bytes(blob)
    if not data:
        return None
    return _combine(_decode_with_qiskit(data), _scrape_header(data))


def decode_bytes(data: bytes) -> DecodedCircuit | None:
    """Decode already-extracted QPY bytes (the reindex path)."""
    if not data:
        return None
    return _combine(_decode_with_qiskit(data), _scrape_header(data))


def qasm3_of(value: Any) -> str | None:
    """QASM3 snippet for evidence. Requires qiskit."""
    blob = value.get("__value__") if isinstance(value, dict) else value
    if not isinstance(blob, str):
        return None
    data = _raw_bytes(blob)
    if not data:
        return None
    try:
        import io

        from qiskit import qasm3, qpy as qiskit_qpy

        circuits = qiskit_qpy.load(io.BytesIO(data))
        if not circuits:
            return None
        return qasm3.dumps(circuits[0])
    except Exception:  # noqa: BLE001 - evidence is nice to have, not required
        return None


def qiskit_available() -> bool:
    try:
        import qiskit  # noqa: F401
    except ImportError:
        return False
    return True
