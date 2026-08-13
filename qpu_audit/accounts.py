"""Looking up IBM Cloud account users.

The Runtime API never returns real names. Those live in the IBM Cloud account (the
User Management service), and conveniently the two ID schemes match::

    workloads.user_id  ==  IAM iam_id  ==  "IBMid-XXXXXXXX"

so the join is automatic. The account ID is already inside the CRN, so there is
nothing extra to configure::

    crn:v1:bluemix:public:quantum-computing:us-east:a/<ACCOUNT_ID>:<INSTANCE>::

**Permissions note**: this call uses *IBM Cloud account* permissions, not quantum
instance permissions. Without the right role — or when the account restricts user
visibility — it returns HTTP 200 with only the caller in the list. Ask the account
administrator for the Viewer role on User Management.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger(__name__)

USER_MANAGEMENT_URL = "https://user-management.cloud.ibm.com/v2/accounts/{account}/users"
_ACCOUNT_IN_CRN = re.compile(r":a/([0-9a-fA-F]{32}):")

RESOURCE_CONTROLLER = "https://resource-controller.cloud.ibm.com"
# Catalogue id of the Qiskit Runtime service, used to filter server-side rather than
# walking every resource in the account.
QISKIT_RUNTIME_RESOURCE_ID = "b6049020-80f4-11eb-a0f7-e35ec9b4054f"


class AccountLookupError(RuntimeError):
    """The account user listing could not be retrieved."""


@dataclass
class DiscoveredInstance:
    """A Qiskit Runtime instance found in the IBM Cloud account."""

    name: str
    crn: str
    state: str = ""
    region: str = ""


@dataclass
class AccountUser:
    iam_id: str
    email: str = ""
    firstname: str = ""
    lastname: str = ""
    state: str = ""

    @property
    def display_name(self) -> str:
        name = f"{self.firstname} {self.lastname}".strip()
        return name or self.email or self.iam_id


def account_id_from_crn(crn: str) -> str:
    """Extract the account ID from a CRN."""
    match = _ACCOUNT_IN_CRN.search(crn or "")
    if not match:
        raise AccountLookupError(
            "Could not find an account ID in the CRN. Check IBM_QUANTUM_CRN in .env\n"
            "Expected: crn:v1:bluemix:public:quantum-computing:<region>:"
            "a/<32-hex account id>:<instance>::"
        )
    return match.group(1)


def _iam_token(settings: Settings, http: httpx.Client) -> str:
    resp = http.post(
        settings.iam_url,
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": settings.api_key,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code != 200:
        raise AccountLookupError(
            f"IAM token request failed ({resp.status_code}): {resp.text[:200]}"
        )
    return resp.json()["access_token"]


def discover_instances(settings: Settings, max_pages: int = 20) -> list[DiscoveredInstance]:
    """List every Qiskit Runtime instance in the IBM Cloud account.

    The Runtime API has no "list instances" endpoint — everything there is scoped to
    the CRN in the request header. The catalogue of instances lives in IBM Cloud's
    Resource Controller instead, which also carries the console name.

    **This only sees instances belonging to your account.** An instance in someone
    else's account that you have been granted access to will not appear, so discovery
    adds to the configured list and never replaces it.

    Note on pagination: the Resource Controller's ``next_url`` has been observed to
    return the same page indefinitely, so this stops as soon as a page yields no CRN
    it has not already seen.
    """
    settings.ensure_credentials()

    found: dict[str, DiscoveredInstance] = {}
    with httpx.Client(timeout=30) as http:
        token = _iam_token(settings, http)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        url = f"{RESOURCE_CONTROLLER}/v2/resource_instances"
        params: dict[str, Any] = {
            "resource_id": QISKIT_RUNTIME_RESOURCE_ID,
            "limit": 100,
        }
        for _ in range(max_pages):
            resp = http.get(url, headers=headers, params=params)
            if resp.status_code in (401, 403):
                raise AccountLookupError(
                    f"Not authorised to list account resources ({resp.status_code}).\n"
                    "Ask the account administrator for the Viewer role on the resource "
                    "group, or keep listing instances by hand in config/instances.toml."
                )
            if resp.status_code != 200:
                raise AccountLookupError(
                    f"Resource listing failed ({resp.status_code}): {resp.text[:300]}"
                )

            body = resp.json()
            rows = body.get("resources", []) or []
            new = 0
            for row in rows:
                crn = str(row.get("crn") or "")
                if ":quantum-computing:" not in crn or crn in found:
                    continue
                parts = crn.split(":")
                found[crn] = DiscoveredInstance(
                    name=str(row.get("name") or "").strip() or crn.split(":")[-2][:12],
                    crn=crn,
                    state=str(row.get("state") or ""),
                    region=parts[5] if len(parts) > 5 else "",
                )
                new += 1

            next_url = body.get("next_url")
            if not rows or not next_url or new == 0:
                break
            url = f"{RESOURCE_CONTROLLER}{next_url}"
            params = {}

    return sorted(found.values(), key=lambda i: i.name.lower())


def lookup_instance(settings: Settings, crn: str) -> DiscoveredInstance | None:
    """Look one instance up directly by its GUID.

    This matters for instances someone granted you access to individually. The
    Resource Controller *listing* only returns resources in resource groups you can
    enumerate, so a shared instance is invisible there — but a direct lookup still
    succeeds, which is how a configured CRN gets verified and given its console name.
    """
    settings.ensure_credentials()
    guid = crn.rstrip(":").split(":")[-1]
    if not guid:
        return None

    with httpx.Client(timeout=30) as http:
        token = _iam_token(settings, http)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        resp = http.get(
            f"{RESOURCE_CONTROLLER}/v2/resource_instances",
            headers=headers,
            params={"guid": guid},
        )
        if resp.status_code != 200:
            return None
        for row in resp.json().get("resources", []) or []:
            row_crn = str(row.get("crn") or "")
            if ":quantum-computing:" not in row_crn:
                continue
            parts = row_crn.split(":")
            return DiscoveredInstance(
                name=str(row.get("name") or "").strip() or guid[:12],
                crn=row_crn,
                state=str(row.get("state") or ""),
                region=parts[5] if len(parts) > 5 else "",
            )
    return None


def list_accounts(settings: Settings) -> list[tuple[str, str]]:
    """Accounts this identity belongs to, as (name, guid).

    An API key is bound to one account and its token carries no usable refresh token,
    so instances in a *second* account need their own API key — this listing exists to
    say so plainly rather than leaving the gap unexplained.
    """
    settings.ensure_credentials()
    out: list[tuple[str, str]] = []
    with httpx.Client(timeout=30) as http:
        token = _iam_token(settings, http)
        resp = http.get(
            "https://accounts.cloud.ibm.com/v1/accounts",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code != 200:
            return out
        for row in resp.json().get("resources", []) or []:
            name = (row.get("entity") or {}).get("name") or ""
            guid = (row.get("metadata") or {}).get("guid") or ""
            if guid:
                out.append((str(name), str(guid)))
    return out


def fetch_account_users(settings: Settings) -> list[AccountUser]:
    """Fetch every user in the account, following pagination."""
    settings.ensure_credentials()
    account_id = account_id_from_crn(settings.crn)

    users: list[AccountUser] = []
    with httpx.Client(timeout=30) as http:
        token = _iam_token(settings, http)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        url = USER_MANAGEMENT_URL.format(account=account_id)
        params: dict[str, Any] = {"limit": 100}

        while True:
            resp = http.get(url, headers=headers, params=params)
            if resp.status_code in (401, 403):
                raise AccountLookupError(
                    f"Not authorised to list account users ({resp.status_code}).\n"
                    "Ask the account administrator for the Viewer role on the IBM Cloud "
                    "User Management service. It is separate from quantum instance access."
                )
            if resp.status_code != 200:
                raise AccountLookupError(
                    f"Account user listing failed ({resp.status_code}): {resp.text[:300]}"
                )

            body = resp.json()
            for item in body.get("resources", []):
                users.append(
                    AccountUser(
                        iam_id=str(item.get("iam_id") or ""),
                        email=str(item.get("email") or ""),
                        firstname=str(item.get("firstname") or ""),
                        lastname=str(item.get("lastname") or ""),
                        state=str(item.get("state") or ""),
                    )
                )

            next_url = body.get("next_url")
            if not next_url:
                break
            url = f"https://user-management.cloud.ibm.com{next_url}"
            params = {}

    return [u for u in users if u.iam_id]
