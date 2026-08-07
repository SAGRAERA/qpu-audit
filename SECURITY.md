# Security and privacy

## Credentials

Credentials live in `.env`, which is git-ignored. `.env.example` ships with the
repository and must stay empty.

Before your first push:

```bash
git status --porcelain --ignored | grep -E '\.env$|user_map\.csv|data/|reports/'
```

Anything listed there must show as ignored, not staged. If an API key has ever been
committed — even in a commit you later amended — revoke it at
<https://cloud.ibm.com/iam/apikeys> and issue a new one. Rewriting history does not
help once the object exists in a pushed repository.

An IBM Cloud API key inherits the full IAM permissions of the identity that created
it. Prefer a Service ID key scoped to what this tool needs over a personal key.

## What this tool collects about other people

Running `collect` writes to `data/audit.db`:

- which user submitted which job, when, on which backend, and for how long
- circuit fingerprints and decoded structure
- **raw QPY circuit payloads**

The last item is a local copy of colleagues' research circuits. It exists so that
fingerprint rules can change without re-fetching, and so evidence outlives IBM's
retention window — but it is real data about real people.

Consider:

- Is copying circuit contents proportionate to the problem you are investigating?
  Clearing `pub_payloads` leaves every other feature working.
- Who can read the database file and generated reports?
- `config/user_map.csv` and any report containing labels name individuals. Both are
  git-ignored; keep them that way and think about distribution before sharing a
  report outside the admin group.

Reports are self-contained HTML with no telemetry and no external requests.

## Reporting a vulnerability

Open a GitHub issue for anything that does not itself expose a secret. For issues
that would leak credentials or personal data if described publicly, use GitHub's
private vulnerability reporting on this repository instead.

## Scope note

This tool reads. It does not cancel jobs, modify instance configuration, or change
anyone's access. Any enforcement is a human action taken elsewhere, deliberately.
