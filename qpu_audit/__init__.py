"""qpu-audit — audit QPU usage patterns on an IBM Quantum instance.

Answers, with evidence: who is running which circuits, how often, and how much of
that repetition has no explanation. Collects workloads and circuits from the Qiskit
Runtime REST API into a local SQLite database and renders an HTML report.
"""

__version__ = "0.1.0"
