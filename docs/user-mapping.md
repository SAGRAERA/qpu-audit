# Mapping user IDs to real people

## Why this is needed

The Qiskit Runtime REST API never returns names or email addresses — not even for
administrators. From the OpenAPI specification:

| Endpoint | Field | Contains a name? |
|---|---|---|
| `GET /v1/workloads` | `WorkloadResponse.user_id` | no — ID only |
| `GET /v1/analytics/filters` | `UserFilter` = `{ "id": string }` | no |
| `GET /v1/analytics/usage_grouped?group_by=user_id` | `data[].key` | no — same ID |

You can tell *whether two jobs came from the same person*, but not *who that is*.
The IDs are stable per person, so mapping them once is enough.

> You do not strictly need names. Reports carry job IDs, and looking one up in the
> console identifies the submitter. Any real enforcement happens in the console
> anyway. Mapping just makes reports readable.

---

## Method 0 — automatic (try this first)

```bash
python -m qpu_audit users --sync
```

Runtime `user_id` values are IAM `iam_id` values (`IBMid-XXXXXXXX`), so they join
directly against the IBM Cloud account user list. The account ID is extracted from
your CRN, so there is nothing to configure. Labels you typed by hand are never
overwritten.

If it works, you are done.

### When it returns only yourself

A common outcome — HTTP 200, one row:

```
Fetched 1 user(s) from the IBM Cloud account; 1 matched users seen on this instance.
  ! 10 of 11 observed users are missing from the account listing.
```

Two possible causes:

1. **Account-level user visibility is restricted.** IBM Cloud has a setting that
   hides users from each other unless they hold IAM permissions.
   → ask the account owner to check it
2. **Missing role.** Your key has no Viewer role on the User Management service.
   → ask for **Viewer on User Management** only. It is unrelated to quantum
   instance permissions, so it is an easy request. Do not ask for an admin key.

Either fix, then re-run `--sync`.

---

## The file

`config/user_map.csv` (UTF-8, git-ignored):

```csv
user_id,label,note
IBMid-EXAMPLE001,Jane Doe,tomography group
IBMid-EXAMPLE002,John Smith,visiting researcher
IBMid-EXAMPLE003,,unidentified so far
```

- `user_id` — exactly as the API returns it
- `label` — shown in reports; falls back to a shortened ID when empty
- `note` — internal memo

Regenerate the file any time; existing labels are preserved and new users are
appended:

```bash
python -m qpu_audit users --export
```

---

## Fallbacks when automatic lookup is blocked

### 1. Confirm your own ID

```bash
python -m qpu_audit probe
```

Prints your `user_id` from a `user=me` query, so it is certain. Everyone else is
someone else — a useful starting point.

### 2. Tag anchoring (most reliable, no extra permissions)

Ask each colleague to submit one job carrying a unique tag:

```python
job.update_tags(["whoami-jane"])
```

Then collect and read the mapping straight out of the database:

```sql
SELECT user_id, tags FROM workloads WHERE tags LIKE '%whoami-%';
```

This gives an exact one-to-one mapping. If you are investigating someone in
particular, map everyone *else* first and identify the remaining ID by elimination
rather than tipping them off.

### 3. Console cross-reference

Reports list job IDs for every flagged circuit group. Copy one, search for it in the
IBM Quantum console under Workloads, and the submitter is shown — assuming account
visibility is not restricted.

### 4. Ask the administrator for a listing

No key exchange required. Have them run:

```bash
ibmcloud account users --output json
```

Copy `resources[].iam_id` into `user_id` and the name or email into `label`.

---

## Operational care

- `config/user_map.csv` names individuals. It is git-ignored — keep it that way.
- Reports with labels filled in also name individuals. Think about who receives
  them. For wider circulation, clear the `label` column so output stays ID-only.
- Put only what is needed for the judgement in `note`. It is not an HR record.
- Verdicts are heuristics with known false-positive modes. Attaching a name turns a
  heuristic into a statement about a person — read the evidence first.
