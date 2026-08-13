# Contributing

## The rule that matters

**Every change to detection logic needs a `selftest` scenario, and the important
scenario is the one proving legitimate research stays unflagged.**

This tool points at named people. A false positive is not a cosmetic bug — it is an
accusation. Three real false positives have already been found and fixed here, and
each one had a plausible-looking implementation behind it:

| Bug | What it did |
|---|---|
| Estimator pubs parsed positionally | read **observables** as parameter values, collapsing a legitimate observable scan into "identical repetition" |
| `has_measure == False` treated as waste | Estimator circuits have no measurement gates by design — flagged normal work |
| Span-before-burst rule ordering | a long overall time span excused bursts of identical submissions |

All three are now pinned by scenarios in `qpu_audit/selftest.py`.

```bash
python -m qpu_audit selftest
```

No credentials required. It builds a synthetic instance covering an abuser, a
trivial-circuit repeater, VQE, QAOA with repeated shots per parameter set, a drift
benchmark, an ordinary user, and an Estimator observable scan — then asserts which
ones must and must not be flagged.

The same run produces the sample report committed at `docs/sample-report.html`. If your
change alters the report, regenerate it in the same commit:

```bash
python -m qpu_audit selftest -o docs/sample-report.html
```

Because it comes from synthetic data, it never contains real users, instances, or
circuits. Never replace it with a report generated from a live instance.

## Setup

```bash
python -m venv .venv && .venv/bin/activate
```

```bash
pip install -r requirements-full.txt
```

Python 3.11+ is required (`tomllib`).

## Working against a real instance

`probe` first, always — it tells you what your key can reach before you spend time
debugging a permission error that looks like a parsing bug.

Once payloads are collected, `reindex` recomputes every fingerprint from local
storage with no API calls. Use it while iterating on fingerprint rules instead of
re-fetching thousands of jobs.

## Code conventions

- Standard library first. The only required dependency is `httpx`; `qiskit` is
  optional and every code path degrades gracefully without it.
- Comments explain *why*, especially where a rule exists to prevent a specific false
  positive. Those comments are the reason the rule survives future refactors.
- User-facing strings are English in this repository.
- No network calls in `selftest`.

## Adding a detection rule

1. Write the scenario in `selftest.py` first, including at least one case that must
   **not** trigger.
2. Implement in `rules.py`.
3. Add the weight to `config.example.toml` and the defaults in `config.py`.
4. Confirm every pre-existing scenario still passes.
5. Document it in the README's risk-signal table, and classify it honestly as
   *waste*, *queue* or *context*.

Choosing the class is the part worth thinking about:

- **waste** — the work itself is questionable
- **queue** — others are harmed regardless of whether the work is legitimate, and the
  remedy does not question the science
- **context** — fires in ordinary situations and justifies nothing alone

If a signal fires on legitimate large-scale experiments *and* the remedy would be to
stop doing the science, it is context. If it fires on legitimate work but the remedy
is a cheap change of habit, it is queue. Say so rather than tuning a threshold until
the inconvenient case disappears.

## Translations

All report strings live in `qpu_audit/i18n.py`, keyed message-first so every language
sits side by side in one file. English, Korean, Japanese and Spanish are present;
Japanese and Spanish have not been reviewed by a native speaker and are labelled as
such in the report's language selector.

Corrections to existing translations are as welcome as new languages — a term that
reads awkwardly to a domain expert is worth fixing.

To add a language: add the code to `LANGUAGES`, fill that key into every entry, then
regenerate the sample report. Missing keys fall back to English rather than breaking
the page, so a partial translation is still mergeable.

```python
python -c "from qpu_audit import i18n; print(i18n.missing_keys('de'))"
```

Do not translate circuit names, user IDs, backend names or numbers.

## Reporting a false positive

Open an issue with the pattern that was misjudged and, if possible, the shape of the
`params` payload (structure only — **no circuit contents, no user identifiers**).
The payload shape is usually the root cause.
