# qpu-audit

**Audit IBM Quantum instance usage workload and circuit-level evidence.**

`qpu-audit` collects workloads and circuit data from the Qiskit Runtime REST API, stores
them locally, and helps identify repeated or potentially wasteful QPU usage.

The main challenge is avoiding false positivies. Legitimate workloads such as tomography, VQE, calibration, and drift studies can look highly repetitive in the IBM Quantum console. This tool compares the underlying circuit data and execution patterns before assigning a risk signal.


## Why this exists

Consider two jobs from a state-tomography sweep.

In the IBM Quantum console, they may look almost identical. Most of the circuit is the same, with only a few `rz` or `sx` gates changing before measurement. Looking through jobs manually, it is easy to conclude that the same circuit is being submitted repeatedly.

But those jobs may be different tomography circuits.

At the same time, a user repeatedly submitting the same experiment can look very similar in the console.

Distinguishing these cases requires decoding the circuit payload and comparing circuits structurally rather than visually. `qpu-audit` automates that process.

## What it does not do

- It does not cancel jobs, modify quotas, or restrict users. It produces reports.
- It does not determine whether a user is "guilty" of misuse. It reports observed signals and their confidence.
- It cannot see workloads outside your IBM Quantum instance, so it cannot account for queue time caused by other organizations sharing the same backend.


## Quick start

Requires **Python 3.11+** (uses `tomllib` from the standard library).

```bash
git clone https://github.com/sagraera/qpu-audit.git && cd qpu-audit
```

```bash
python -m venv .venv && .venv/bin/activate
```

```bash
pip install -r requirements-full.txt
```

`requirements.txt` is just `httpx`. 

`requirements-full.txt` adds `qiskit`, which is
strongly recommended - circuits arrive as QPY binary, and without qiskit the tool
falls back to header-level metadata only.

### Credentials

```bash
cp .env.example .env
```

Set the following two values:


| Variable | Where to get it |
|---|---|
| `IBM_QUANTUM_API_KEY` | <https://cloud.ibm.com/iam/apikeys> → Create |
| `IBM_QUANTUM_CRN` | IBM Quantum Platform console → Instances → your instance → copy CRN |

Do not put credentials in `.env.example`; that file is committed to the repository. `.env` is git-ignored.

An IBM Cloud API key inherits the IAM permissions of whoever created it. There is no
way to attach permissions to a key directly.

### Multiple instances

A Premium account usually holds several instances, each with its own CRN. Instead of switching `IBM_QUANTUM_CRN` by hand, list them:

```bash
cp config/instances.example.toml config/instances.toml
```

```toml
[[instance]]
name = "research"
crn  = "crn:v1:bluemix:public:quantum-computing:us-east:a/<account>:<instance>::"

[[instance]]
name = "teaching"
crn  = "crn:v1:bluemix:public:quantum-computing:us-east:a/<account>:<instance>::"
```

The same API key is used throughout; the API selects an instance per request through the `Service-CRN` header. Every command then covers all of them, and `--instance <name>` narrows to one.

`config/instances.toml` is git-ignored, because a CRN contains your IBM Cloud account ID.

With a single instance, keep using `IBM_QUANTUM_CRN` and ignore this file. Permissions can differ between instances, so `probe` reports each one separately.

Rather than collecting CRNs by hand, ask the account:

```bash
python -m qpu_audit instances --discover
```

This lists the Qiskit Runtime instances in your IBM Cloud account and appends any that are missing, using their console names. Existing entries are never renamed and **never removed** — an instance you were granted access to individually does not appear in the account listing at all, and deleting it would orphan everything already collected against it. Those are verified by direct lookup instead and reported separately.

Use `--dry-run` to see what it would add. Being listed does not imply you can read a given instance's workloads, so run `probe` afterwards.

One limit worth knowing: an API key belongs to a single account. If your identity is a member of several, instances in the others need their own key — `--discover` says so when it detects this.

### Run it

```bash
python -m qpu_audit probe
```

Checks which API endpoints and permissions are available to the current key.

The two most important checks are:

- whether you can see workloads submitted by other users
- whether job details include circuit payloads

The remaining checks are optional.

```bash
python -m qpu_audit collect
```

Incrementally collects workloads, job details, and circuit payloads.

Fetching a circuit payload requires one API call per job, so collection is capped per run. The default limit is 500 jobs.

Run it several times initially to catch up on existing jobs, then schedule it periodically.

```bash
python -m qpu_audit report --csv
```

Generates: 
`reports/qpu-audit-<timestamp>.html`

The report is a self-contained HTML file with no external dependencies. It can be opened directly in a browser or shared as a standalone file.

Every ranking table is sortable — click a column heading to re-rank by it. Which QPU is "busiest" depends on whether you mean hours, job count, or number of users, and those give different answers, so the ordering is the reader's choice rather than a fixed one. Sorting runs on the underlying values, not the displayed text, so units, thousands separators and the language switcher do not disturb it.

A sample is committed at [`docs/sample-report.html`](docs/sample-report.html), generated entirely from the synthetic `selftest` scenarios. It contains no real user IDs, instances, or circuits. Regenerate it with:

```bash
python -m qpu_audit selftest -o docs/sample-report.html
```

### Report languages

Reports are read by people who did not generate them, so the reader picks the language rather than the person running the tool.

Every string ships inside the single HTML file in **English, Korean, Japanese, and Spanish**, with a selector in the top-right corner. Only the active language is displayed; the choice is remembered per browser and the first visit follows the browser's own language setting. No network access and no regeneration are involved.

Circuit names, user IDs, backends, and numbers are of course not translated.

**Translations are contributed, not authoritative.** Japanese and Spanish have not been reviewed by a native speaker and are marked as such in the selector. If a term reads wrong in your language, a pull request correcting it is genuinely welcome.

**Adding a language** means editing one file, [`qpu_audit/i18n.py`](qpu_audit/i18n.py). Strings are keyed message-first, so each entry shows every language side by side:

```python
"h_queue": {
    "en": "Queue impact",
    "ko": "큐 점유 영향",
    "ja": "キューへの影響",
    "es": "Impacto en la cola",
},
```

1. add your code to `LANGUAGES`
2. add that key to every entry (anything missing falls back to English rather than breaking)
3. `python -m qpu_audit selftest -o docs/sample-report.html` and check it renders

`i18n.missing_keys("de")` lists what a language still needs.

### Choosing a period

By default `analyze` and `report` cover a rolling window (`analyze.window_days`, 30 by default). Any explicit period works instead:

```bash
python -m qpu_audit report --from 2026-07-01 --to 2026-07-31
```

`--to` is inclusive: a bare date means the end of that day, in UTC.

Two periods can be compared directly:

```bash
python -m qpu_audit analyze --from 2026-07-16 --to 2026-07-31 --vs-from 2026-07-01 --vs-to 2026-07-15
```

```bash
python -m qpu_audit report --from 2026-08-01 --vs prev
```

`--vs prev` uses the equally long stretch immediately before the analysed window.

Both periods go through the same analysis, so the change column reflects verdicts rather than raw usage. A user present in only one period still appears — somebody starting or stopping is exactly the change worth seeing.

One caveat: a period that predates your first `collect` shows as empty, not as zero usage. The tool cannot distinguish "nobody ran anything" from "nothing was collected yet".

```bash
python -m qpu_audit usage --csv
```

Shows monthly QPU usage per user.

```bash
python -m qpu_audit usage --by-instance
```

Shows QPU usage per user per instance, with the share of each instance alongside the account-wide total.

Both views are needed. Per-instance figures reveal someone monopolising a single instance; the total column reveals someone spread across all of them who nevertheless dominates the account. Neither is visible from the other.

```bash
python -m qpu_audit usage --by-backend
```

Ranks the QPUs by absorbed time and shows who took it:

```
 #  backend                  hours   share    jobs  users  heaviest user
 1  ibm_yonsei               10.76   40.5%     249      3  ... (62%)
 2  ibm_miami                 6.97   26.2%      45      8  ... (94%)
 3  ibm_marrakesh             5.49   20.7%     736      4  ... (91%)
```

Followed by the same user × backend matrix. A high *heaviest user* share means one person effectively owns that machine, which is worth knowing before anyone else plans work on it. Reading a row shows whether someone spreads across machines or camps on one; reading a column shows whether a machine serves the group or one person.

> **Start collecting early.** 
> IBM does not retain job payloads indefinitely. Once a circuit payload has aged out, it cannot be recovered through the API.
> 
> From the first `collect` onward, retrieved data is stored locally, including raw circuit payloads.

### Scheduling

Any scheduler can be used.

For example, on Windows, Task Scheduler can run the following command every 15 minutes:

```bash
.venv\Scripts\python.exe -m qpu_audit collect
```


## Commands

| Command | What it does |
|---|---|
| `probe` | Reports which API endpoints and permissions are available, per instance |
| `collect` | Incrementally syncs workloads, job details, and circuit payloads (`--instance` limits it to one) |
| `reindex` | Recompute fingerprints from stored payloads — **no API calls** |
| `analyze` | Prints a console summary of risk ranking and queue impact (`--from`/`--to`/`--vs`) |
| `report` | Generates the full HTML report (`--csv` also writes CSV output; same period flags) |
| `instances` | Lists configured instances; `--discover` finds more in your IBM Cloud account |
| `usage` | Monthly usage ledger per user (`--by-instance`, `--by-backend` break it down further) |
| `users` | List observed user IDs; `--sync` resolves names when possible|
| `status` | Shows local database state and collection backlog |
| `selftest` | Tests detection logic using synthetic scenarios - no credentials required |

Run `selftest` after changing detection thresholds or classification logic.

A particularly important check is that legitimate research workloads remain unflagged. False positives are more damaging here than missed detections.


## How circuits are compared

Qiskit Runtime does not send circuits as OpenQASM.

Circuit data is encoded in a structure similar to:

```json
{"__type__": "QuantumCircuit", "__value__": "<base64(zlib(QPY))>"}
```

One complication is that **re-transpiling the same logical circuit can produce different binary payloads.**

Submitting the same experiment 100 times may therefore result in 100 different payloads. A byte-level comparison alone is not sufficient.

To handle this, `qpu-audit` computes four fingerprints for each circuit:

| Fingerprint | Built from | Catches |
|---|---|---|
| `exact_hash` | gate sequence + parameters + observables + shots | identical executions |
| `structural_hash` | gate sequence with rotation angles masked | same circuit structure with different parameters, such as VQE |
| `intent_hash` | circuit name + metadata | the same experiment after **re-transpilation** |
| `profile_hash` | bucketed qubit count, depth, 2-qubit gate count | broadly similar circuit families; weak signal only |

In practice, `intent_hash`is particularly useful.

Qiskit experiment modules often generate descriptive circuit names such as:

 `StateTomography_(2, 2, 2, 1, 0, 1, 0)`,
`meas_mit_cal_0000000`. 

These names can preserve experiment identity even when transpilation changes the underlying circuit representation.

Generic auto-generated names such as:

`circuit-61`

are not reliable because they may be reused across unrelated circuits. These names are explicitly ignored and produce `intent_hash = None`.

For grouping purposes, the identity of a circuit is:

- `intent_hash`, when the name and metadata are considered trustworthy
- otherwise `exact_hash`

The report's *payloads* column distinguishes between:

- `identical` : exactly the same payload was submitted repeatedly
- `N variants` : multiple payloads correspond to the same inferred experiment, usually because of re-transpilation

### Primitive-specific payload shapes

Sampler and Estimator PUBs do not use the same field layout:

```
sampler    pub = [circuit, parameter_values, shots]
estimator  pub = [circuit, observables, parameter_values, precision]
```

In particular, the second element has a different meaning.

If an Estimator's **observables** are incorrectly interpreted as parameter values, a legitimate observable scan can collapse into what appears to be repeated execution of the same circuit.

`qpu_audit` therefore classifies PUB elements by content rather than by position and includes observables in `exact_hash`.


## How repetition is classified

Repetition by itself is not evidence of waste.

VQE may evaluate the same ansatz hundreds of times with different parameters. Drift studies may intentionally run identical circuits over several days. Calibration and tomography can also produce highly repetitive-looking workloads.

The classifier therefore considers the execution pattern as well as the circuit identity.

| Observation | Interpretation | Verdict |
|---|---|---|
| Identical circuit, shots, and backend at short intervals | no meaningful variation between runs | **flagged** |
| Same skeleton, different parameters, **converging trajectory** | optimizer loop | normal |
| Identical circuit spread over days, or multiple backends | drift / calibration benchmark | normal |
| Short-interval repetition across multiple backends | possibly cross-backend comparison | grey |
| Other repetitive patterns | insufficient evidence | grey |

### Parameter convergence

For parameterized circuit groups, parameter vectors are ordered by submission time.

The tool computes the L2 distance between consecutive vectors and compares the average step size in the first half of the trajectory with the average step size in the second half.

A decreasing step size is treated as evidence of optimizer convergence.


### Burst precedence

Burst detection takes precedence over the "spread over time" exemption.

Without this rule, a user could submit a burst of identical jobs every few days and still appear similar to a periodic benchmark workload.

### Content signals

The tool also records several circuit-level properties:

- No two-qubit gates
  The circuit contains no entangling operation, so running it on a QPU may provide limited value depending on the experiment.
- No measurement gates 
  Potentially suspicious for Sampler-style execution, but normal for Estimator workloads.

Clifford-only circuits are not treated as waste.

Randomized benchmarking, calibration, and related workflows legitimately use Clifford circuits, so this property is included only as contextual information.


## Risk signals

The risk score ranges from 0 to 100 and combines nine signals in three classes.

Signals are divided into three classes, because *"is this work legitimate?"* and *"does this behaviour harm others?"* are separate questions:

- `waste`: QPU time spent on nothing. Questions the work itself.
- `queue`: harms other users whether or not the work is legitimate. A burst of a thousand jobs monopolises the queue even when the science is impeccable, and the usual remedy - batching - does not question the science at all.
- `context`: information only. Occurs during entirely ordinary situations and justifies nothing on its own.

| Signal | Weight | Class |
|---|---|---|
| Unexplained repeated execution | 30 | waste |
| Single-circuit concentration | 15 | waste |
| Non-entangling circuits | 10 | waste |
| Failed-payload resubmission | 5 | waste |
| **Burst submission** (many jobs in 60s) | 12 | queue |
| No session/batch grouping | 8 | queue |
| **Suspected overuse** (share of QPU time) | 12 | context |
| Mechanical submission intervals | 5 | context |
| **Usage spike** (vs. previous month) | 3 | context |

Totals: waste 60, queue 20, context 20.

Context signals are intentionally not sufficient for action on their own.

For example, seven-qubit state tomography requires:

3^7 = 2,187 circuits.

A valid tomography workload may therefore trigger instance-share, burst-submission, and submission-regularity signals simultaneously.

Usage spike is weighted lowest deliberately. A new user, a return from leave, or the start of a new project all produce large month-over-month ratios without indicating anything wrong. The same information is already shown directly in the monthly usage table.

In the report, the three classes are shown as separate totals so the distinction stays visible. A user with high `queue` and near-zero `waste` needs a conversation about batching; a user with high `waste` needs a conversation about the repetition itself.

A circuit group classified as normal contributes no `waste` score regardless of how many times it ran.

Users are ranked primarily by `estimated wasted QPU seconds`, not by risk score alone.

This prevents a user with very low absolute usage but a poor waste ratio from ranking above someone consuming a substantial amount of QPU time.

### Share across instances

The overuse signal uses whichever is worse: the share of the entire account, or the largest share held inside any single instance.

Scoring only the account-wide share lets someone quietly monopolise one small instance. Scoring only the per-instance share misses someone who took over every instance at once. The report shows both columns.


## Queue impact

QPU time consumed and queue delay caused to other users are related but not identical.

Because a QPU executes work serially, the relevant quantity is **backend occupancy while another user's job is waiting**.

For each user, the tool estimates how long that user's jobs were executing on a backend while jobs from another user were waiting on the same backend.

Execution and waiting intervals are approximated as:

`execution = [ended − qpu_seconds, ended]`

`wait = [created, ended − qpu_seconds]`

Jobs without an end timestamp are excluded.

Including unfinished jobs can severely distort queue-impact estimates. For example, one job that remains pending for days could otherwise appear to have been blocked by every execution during that period.

The report also includes:

- maximum concurrent pending jobs
- largest 60-second submission burst
- median submission gap
- number of session/batch containers

### Queue-impact Caveat.

IBM Quantum backends may be shared across organizations.

The tool only sees jobs visible within your instance, so a substantial fraction of real queue time may be caused by workloads it cannot observe.

Queue-impact values should therefore be interpreted mainly as **relative comparisons between users within the same instance**, not as a complete explanation of backend queue time.


## Identifying users

The Runtime API returns opaque user IDs rather than names or email addresses.

Even administrators receive IDs rather than identity fields. In the OpenAPI schema, `UserFilter` is effectively:

{"id": string}

These IDs correspond to IBM Cloud IAM `iam_id` values such as:

IBMid-XXXXXXXX

They can therefore be joined against the IBM Cloud account user list.

Run: 

```bash
python -m qpu_audit users --sync
```

The account ID is extracted automatically from the configured CRN.

Manually assigned labels are never overwritten during synchronization.

If synchronization returns only your own identity, one of the following may apply:
- account-level user visibility is restricted
- the API key owner does not have the User Management Viewer role

This role is separate from IBM Quantum permissions.

See: [docs/user-mapping.md](docs/user-mapping.md)

for fallback approaches, including a tag-based identification method that does not require additional IAM permissions.

---

## What is stored

Data is stored in: `data/audit.db`.

The SQLite database is git-ignored.

Stored data includes:

- workload metadata
  - user
  - backend
  - status
  - QPU seconds
- circuit fingerprints and decoded statistics
- **raw QPY payloads**
  - allows fingerprints to be recomputed with `reindex`
  - preserves evidence after IBM's payload-retention window expires
- `usage_monthly`
  - the monthly per-user usage ledger


### Data-handling note

Storing raw QPY payloads means that **research circuits submitted by other users may be copied to the local machine running** `qpu-audit`.

Before enabling long-term collection, consider whether retaining those payloads is appropriate for your environment and restrict access to the database accordingly.

If raw payload retention is not acceptable, clearing the pub_payloads table leaves the remaining reporting functionality available.


## Limitations

- Generic auto-generated circuit names disable `intent_hash`. If such a circuit is re-transpiled before every submission, repeated execution may not be detected.
- The classifier is intentionally conservative. It prefers false negatives over incorrectly flagging legitimate research.
- Jobs marked `private: true` do not expose their circuit payloads. Those jobs can only be analyzed using workload-level behavior.
- Analytics endpoints under `/v1/analytics/*` and instance-limit information require administrator permissions. Other features continue to work without them; unavailable sections are omitted.
- All verdicts are heuristic. Review the underlying evidence before taking administrative action.


## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). 

Any change to detection logic should include a corresponding `selftest` scenario.

Tests that confirm legitimate research workloads remain unflagged are especially important.

## License

MIT — see [LICENSE](LICENSE).
