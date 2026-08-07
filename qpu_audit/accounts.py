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


class AccountLookupError(RuntimeError):
    """The account user listing could not be retrieved."""


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
