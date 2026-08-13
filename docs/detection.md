# Detection design

Notes on why the rules are shaped the way they are. Most of them exist because a
straightforward implementation produced a false positive against real data.

---

## 1. Circuits do not arrive as text

Qiskit Runtime sends:

```json
{"__type__": "QuantumCircuit", "__value__": "<base64(zlib(QPY))>"}
```

QPY is Qiskit's binary serialisation format. `qpu_audit/qpy.py` decodes it two ways:

- **header scrape** — circuit name, metadata, qubit/clbit counts, instruction count.
  Pure standard library, no qiskit needed, and unaffected by re-transpilation.
- **qiskit decode** — full gate sequence, depth, 2-qubit gate counts, histograms.

The header path is the fallback, not an afterthought: the fields it recovers are the
ones that identify *what experiment this is*.

## 2. Re-transpilation defeats byte comparison

A circuit re-transpiled at each submission produces different bytes every time.
Routing and gate ordering change with the layout chosen.

Measured on a real instance: one user's 13,997 circuit executions produced 13,975
distinct payloads. Byte-level deduplication reported ~100% unique. The truth was
2,187 distinct measurement bases, each run 11 times.

Hence four fingerprints:

| Name | Input | Survives re-transpilation? |
|---|---|---|
| `exact_hash` | gate sequence + parameters + observables + shots | no |
| `structural_hash` | gate sequence, rotation angles masked | no |
| `intent_hash` | circuit name + metadata | **yes** |
| `profile_hash` | bucketed qubits / depth / 2-qubit count | mostly |

### Why `intent_hash` works

Qiskit's experiment modules embed the experiment identity in the circuit name and
metadata:

```
StateTomography_(2, 2, 2, 1, 0, 1, 0)   metadata: {"m_idx":[2,2,2,1,0,1,0]}
meas_mit_cal_0000000                     metadata: {"state_label":"0000000"}
```

Both survive transpilation untouched.

### Why it is distrusted for generic names

Names like `circuit-61` are auto-assigned and counter-based per process. Different
jobs reuse the same name for completely unrelated circuits — confirmed on real data.
Any name matching `^(circuit|qc)[-_]?\d*$` sets `intent_hash` to `None`, and grouping
falls back to `exact_hash`.

This costs recall: re-transpiled repetition of generically named circuits is not
detected. That is the intended direction of error.

## 3. Primitives put different things in the same slot

```
sampler    pub = [circuit, parameter_values, shots]
estimator  pub = [circuit, observables, parameter_values, precision]
```

Reading slot 1 as parameter values means an Estimator's **observables** are ignored.
Every run of an observable scan then hashes identically, and a legitimate sweep is
reported as "the same execution repeated N times".

This happened. It flagged a real user before being caught.

`_classify_pub` therefore inspects content rather than position:

- circuit — a QPY payload or a QASM string
- observables — a dict keyed by Pauli strings (`^[IXYZ]{2,}$`)
- parameters — an `ndarray` payload or a nested numeric structure
- shots — a bare integer

Observables are folded into `exact_hash` through `observable_sig`.

## 4. Repetition is not the same as waste

VQE reruns one ansatz hundreds of times. Drift studies deliberately repeat identical
circuits for days. Sorting by repetition count ranks the most diligent users first.

Judgement per circuit group:

```
runs < min_repeats                          -> normal
parameter trajectory converging             -> normal   (optimizer loop)
short gaps + same shots + same backend      -> FLAGGED
short gaps + same shots + several backends  -> grey     (cross-backend comparison?)
long gaps, or spread across backends        -> normal   (drift / benchmark)
otherwise                                   -> grey
```

### Convergence test

Order a group's parameter vectors by time, take consecutive L2 distances, compare the
mean of the second half to the mean of the first. Shrinking steps mean an optimizer.
Constant or IID-random steps do not.

Needs ≥ 6 samples of equal dimension; otherwise it returns "unknown" and does not
influence the verdict.

### Burst detection precedes the time-span exemption

The exemption for work spread over days was originally checked first. A group of 29
identical runs spanning 141 hours was passed as a benchmark — its **median gap was
0.0 minutes**. It was bursts fired every few days.

Ordering now puts the short-gap test first. A long total span never excuses tightly
clustered identical submissions.

## 5. Content signals

Counted as waste:

- no 2-qubit gates at all — nothing is entangled, so the QPU adds nothing
- no measurement gates — **except for Estimator jobs**

Not counted:

- **Clifford-only.** Classically simulable in principle, but randomized benchmarking
  and calibration use Clifford circuits legitimately. Shown as context only.
- **Missing measurements on Estimator jobs.** Observables are supplied separately and
  the service applies basis rotations. Absent measurement gates are correct there.
  Treating this as waste flagged a normal user.

## 6. Scoring

Nine signals, weighted, capped at 100, in **three** classes. An earlier version used
two — actionable and context — and that turned out to conflate different questions.

**waste (60)**: unexplained repetition 30, single-circuit concentration 15,
non-entangling circuits 10, failed resubmission 5.
Questions the work itself.

**queue (20)**: burst submission 12, no session/batch grouping 8.
Harms other users whether or not the work is legitimate.

**context (20)**: suspected overuse 12, mechanical intervals 5, usage spike 3.
Information only.

The split between *waste* and *queue* matters because "is this work legitimate?" and
"does this behaviour harm others?" have different answers and different remedies. A
burst of a thousand jobs monopolises the queue even when the science is impeccable,
and the fix — batching — does not question the science at all. Filing that under
"context" understated it; filing it under "actionable" implied the work was suspect.

Usage spike carries the lowest weight deliberately. A new user, a return from leave,
or the start of a new project all produce large month-over-month ratios without
indicating anything wrong, and the same information already appears in the monthly
usage table.

Context signals fire on legitimate large-scale work. A 7-qubit state tomography needs
3⁷ = 2,187 circuits; running it maximises share, burst and interval regularity
simultaneously without anything being wrong. They are rendered distinctly and are
never sufficient grounds for action alone.

Waste signals derive only from groups that passed the verdict rules. Groups judged
normal contribute zero regardless of run count. Grey groups contribute half.

**Ranking uses absolute wasted seconds, not score.** Score is a ratio and a tiny user
with a bad ratio will otherwise outrank someone burning actual hours. Report tables
are sortable, so any other ordering is a click away.

### Overuse across instances and QPUs

The overuse signal takes whichever is worse: the share of the whole account, or the
largest share held inside any single instance. Scoring only the account-wide share
lets someone quietly monopolise a small instance; scoring only the per-instance share
misses someone who took over every instance at once.

The same asymmetry applies to backends, which is why the report ranks QPUs separately
and shows each machine's heaviest user. A backend where one person holds 97% is a
different operational fact from one shared by eight.

## 7. Queue impact

Consuming QPU time and delaying other people are different measurements.

The first implementation counted overlapping *queue presence* and concluded that a
single user with one pending job had blocked everyone for 329 hours. Queue presence
does not block anyone — a serial QPU is blocked by **occupancy**.

Now measured as: for each user, time spent executing on a backend while some other
user's job was waiting on that same backend.

```
execution = [ended - qpu_seconds, ended]
wait      = [created, ended - qpu_seconds]
```

Jobs without an end timestamp are excluded rather than extended to "now".

**Interpretation limit.** IBM backends are shared across organizations. Most observed
wait time typically comes from jobs outside your instance, which this tool cannot
see. Use the numbers to compare your own users, not as an absolute account of delay.

## 8. Determining session/batch usage

`jobs.session_id` came back empty for every job on the test instance — impossible to
tell "not used" from "not returned".

`workloads.mode` settles it. Sessions and batches appear as their own workload rows.
A user who created zero session/batch containers cannot have jobs inside one, so
"not used" is certain regardless of `session_id`. Only users who *do* own containers
have their session judgement suspended.

## 9. Known gaps

- Generically named, re-transpiled repetition is invisible (section 2).
- `private: true` jobs return no payload; those users are judged on behaviour only.
- Analytics endpoints need administrator rights; sections are omitted without them.
- Prorating a partial month assumes a uniform rate within the month.
