"""Qiskit Runtime REST API client.

Supports both authentication schemes defined in the OpenAPI spec (v0.48.x):

  - apikey: ``Authorization: apikey <KEY>``      (default)
  - iam:    exchange for a bearer token          (used automatically on a 401)

Every request also carries ``Service-CRN`` and ``IBM-API-Version``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

import httpx

from .config import Settings

log = logging.getLogger(__name__)

# Per-endpoint page size caps from the OpenAPI spec. Exceeding them returns 400.
MAX_WORKLOADS_LIMIT = 50
MAX_JOBS_LIMIT = 200


class AccessDenied(RuntimeError):
    """No permission for this resource (401/403)."""


class NotFound(RuntimeError):
    """Resource is gone or past its retention window (404)."""


@dataclass
class ApiResult:
    """Shallow result wrapper used by the permission probe."""

    ok: bool
    status: int
    detail: str
    payload: Any = None


class RuntimeClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        collect = settings.section("collect")
        self._timeout = float(collect.get("request_timeout", 30))
        self._max_retries = int(collect.get("max_retries", 5))
        self._auth_mode = settings.auth_mode
        self._bearer: str | None = None
        self._bearer_expires_at: float = 0.0
        self._http = httpx.Client(timeout=self._timeout, follow_redirects=True)

    # -- context manager ---------------------------------------------------
    def __enter__(self) -> "RuntimeClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # -- authentication ----------------------------------------------------
    def _iam_token(self) -> str:
        now = time.time()
        if self._bearer and now < self._bearer_expires_at - 120:
            return self._bearer
        resp = self._http.post(
            self.settings.iam_url,
            data={
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": self.settings.api_key,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        body = resp.json()
        self._bearer = body["access_token"]
        self._bearer_expires_at = now + float(body.get("expires_in", 3600))
        return self._bearer

    def _headers(self) -> dict[str, str]:
        if self._auth_mode == "iam":
            auth = f"Bearer {self._iam_token()}"
        else:
            auth = f"apikey {self.settings.api_key}"
        return {
            "Authorization": auth,
            "Service-CRN": self.settings.crn,
            "IBM-API-Version": self.settings.api_version,
            "Accept": "application/json",
        }

    # -- low level ---------------------------------------------------------
    def request(self, method: str, path_or_url: str, **kwargs: Any) -> httpx.Response:
        """One request with retries and auth fallback. Status is not checked here."""
        url = (
            path_or_url
            if path_or_url.startswith("http")
            else f"{self.settings.base_url}{path_or_url}"
        )
        attempt = 0
        tried_iam_fallback = False
        while True:
            attempt += 1
            resp = self._http.request(method, url, headers=self._headers(), **kwargs)

            # If apikey auth is rejected, switch to IAM tokens once and retry.
            if resp.status_code == 401 and self._auth_mode == "apikey" and not tried_iam_fallback:
                log.info("apikey auth returned 401; switching to IAM bearer tokens.")
                self._auth_mode = "iam"
                tried_iam_fallback = True
                continue

            if resp.status_code in (429, 500, 502, 503, 504) and attempt <= self._max_retries:
                delay = self._retry_delay(resp, attempt)
                log.warning(
                    "%s %s -> %s, retrying in %.1fs (%d/%d)",
                    method, url, resp.status_code, delay, attempt, self._max_retries,
                )
                time.sleep(delay)
                continue

            return resp

    @staticmethod
    def _retry_delay(resp: httpx.Response, attempt: int) -> float:
        header = resp.headers.get("Retry-After")
        if header:
            try:
                return min(float(header), 120.0)
            except ValueError:
                pass
        return min(2.0 ** attempt, 60.0)

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = self.request("GET", path, params=params)
        if resp.status_code in (401, 403):
            raise AccessDenied(f"{resp.status_code} {path}: {resp.text[:300]}")
        if resp.status_code == 404:
            raise NotFound(f"404 {path}")
        if resp.status_code >= 400:
            # raise_for_status discards the body, which is where the cause is.
            raise httpx.HTTPStatusError(
                f"{resp.status_code} {path} params={params} -> {resp.text[:400]}",
                request=resp.request,
                response=resp,
            )
        return resp.json()

    def probe(self, path: str, params: dict[str, Any] | None = None) -> ApiResult:
        """For permission checks: returns a result instead of raising."""
        try:
            resp = self.request("GET", path, params=params)
        except Exception as exc:  # noqa: BLE001 - the probe swallows everything
            return ApiResult(False, 0, f"request failed: {type(exc).__name__}: {exc}")
        if resp.status_code == 200:
            try:
                return ApiResult(True, 200, "OK", resp.json())
            except ValueError:
                return ApiResult(True, 200, "OK (not JSON)", resp.text[:500])
        return ApiResult(False, resp.status_code, resp.text[:300])

    # -- endpoints ---------------------------------------------------------
    def instance(self) -> Any:
        return self.get_json("/v1/instance")

    def instance_usage(self) -> Any:
        return self.get_json("/v1/instances/usage")

    def instance_configuration(self) -> Any:
        return self.get_json("/v1/instances/configuration")

    def job(self, job_id: str, exclude_params: bool = False) -> Any:
        params = {"exclude_params": "true"} if exclude_params else None
        return self.get_json(f"/v1/jobs/{job_id}", params=params)

    def job_metrics(self, job_id: str) -> Any:
        return self.get_json(f"/v1/jobs/{job_id}/metrics")

    def analytics_usage_grouped(self, group_by: str, **filters: Any) -> Any:
        params: dict[str, Any] = {"group_by": group_by}
        params.update({k: v for k, v in filters.items() if v is not None})
        return self.get_json("/v1/analytics/usage_grouped", params=params)

    def analytics_filters(self) -> Any:
        return self.get_json("/v1/analytics/filters")

    # -- pagination --------------------------------------------------------
    def iter_workloads(
        self,
        created_after: str | None = None,
        limit: int = 50,
        max_items: int | None = None,
        **filters: Any,
    ) -> Iterator[dict[str, Any]]:
        """Walk GET /v1/workloads by cursor.

        Omitting ``user`` returns every workload on the instance; the spec only
        allows ``user=me``, which narrows the result to your own.
        """
        # This endpoint caps limit at 50. Anything larger returns 400.
        limit = max(1, min(int(limit), MAX_WORKLOADS_LIMIT))
        params: dict[str, Any] = {"limit": limit, "sort": "-createdAt"}
        if created_after:
            params["created_after"] = created_after
        params.update({k: v for k, v in filters.items() if v is not None})

        seen = 0
        cursor: str | None = None
        while True:
            page_params = dict(params)
            if cursor:
                page_params["next"] = cursor
            body = self.get_json("/v1/workloads", params=page_params)
            items = body.get("workloads") or []
            if not items:
                return
            for item in items:
                yield item
                seen += 1
                if max_items is not None and seen >= max_items:
                    return
            cursor = _next_cursor(body)
            if not cursor:
                return

    def iter_jobs(
        self,
        created_after: str | None = None,
        limit: int = 200,
        max_items: int | None = None,
        exclude_params: bool = True,
        **filters: Any,
    ) -> Iterator[dict[str, Any]]:
        """Walk GET /v1/jobs by offset (your own jobs)."""
        limit = max(1, min(int(limit), MAX_JOBS_LIMIT))
        offset = 0
        seen = 0
        while True:
            params: dict[str, Any] = {"limit": limit, "offset": offset, "sort": "DESC"}
            if created_after:
                params["created_after"] = created_after
            if exclude_params:
                params["exclude_params"] = "true"
            params.update({k: v for k, v in filters.items() if v is not None})

            body = self.get_json("/v1/jobs", params=params)
            items = body.get("jobs") or []
            if not items:
                return
            for item in items:
                yield item
                seen += 1
                if max_items is not None and seen >= max_items:
                    return
            offset += len(items)
            if len(items) < limit:
                return


def _next_cursor(body: dict[str, Any]) -> str | None:
    """Pull the cursor value out of the workloads 'next' link."""
    nxt = body.get("next")
    if not nxt:
        return None
    href = nxt.get("href") if isinstance(nxt, dict) else nxt
    if not href:
        return None
    values = parse_qs(urlparse(str(href)).query).get("next")
    return values[0] if values else None
