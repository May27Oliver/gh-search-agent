"""GitHub Search Repositories client.

Infrastructure layer: wraps the HTTP call, normalizes responses, and classifies
failures into distinct exception types so callers can separate transport errors
from logical errors (EVAL_EXECUTION_SPEC §7).
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

SEARCH_ENDPOINT = "https://api.github.com/search/repositories"
DEFAULT_TIMEOUT_SECONDS = 15


class GitHubError(Exception):
    """Base class for all client-level failures."""


class GitHubAuthError(GitHubError):
    """401 — bad or missing credentials."""


class GitHubInvalidQueryError(GitHubError):
    """422 — query failed GitHub-side validation."""


class GitHubRateLimitError(GitHubError):
    """403 with rate-limit signal."""


class GitHubTransportError(GitHubError):
    """Network / 5xx / timeout — failure is not attributable to the query itself."""


@dataclass(frozen=True)
class Repository:
    name: str
    url: str
    stars: int
    language: str | None
    description: str | None = None


class GitHubClient:
    def __init__(self, token: str | None, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
        self._token = token
        self._timeout = timeout_seconds

    def search_repositories(
        self,
        query: str,
        sort: str | None,
        order: str | None,
        per_page: int,
    ) -> list[Repository]:
        params: dict[str, str | int] = {"q": query, "per_page": per_page}
        if sort is not None:
            params["sort"] = sort
        if order is not None:
            params["order"] = order

        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            resp = requests.get(
                SEARCH_ENDPOINT,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise GitHubTransportError(f"network failure: {exc}") from exc

        if resp.status_code == 200:
            return _normalize(resp.json())
        if resp.status_code == 401:
            raise GitHubAuthError(_message(resp))
        if resp.status_code == 422:
            raise GitHubInvalidQueryError(_message(resp))
        if resp.status_code == 403 and _is_rate_limited(resp):
            raise GitHubRateLimitError(_message(resp))
        if 500 <= resp.status_code < 600:
            raise GitHubTransportError(f"server error {resp.status_code}: {_message(resp)}")
        raise GitHubError(f"unexpected status {resp.status_code}: {_message(resp)}")


def _normalize(payload: dict) -> list[Repository]:
    items = payload.get("items") or []
    return [
        Repository(
            name=item["full_name"],
            url=item["html_url"],
            stars=int(item["stargazers_count"]),
            language=item.get("language"),
            description=item.get("description"),
        )
        for item in items
    ]


def _message(resp: requests.Response) -> str:
    try:
        return str(resp.json().get("message") or resp.text)
    except ValueError:
        return resp.text


def _is_rate_limited(resp: requests.Response) -> bool:
    remaining = resp.headers.get("X-RateLimit-Remaining")
    if remaining == "0":
        return True
    try:
        body = resp.json()
    except ValueError:
        return False
    message = str(body.get("message", "")).lower()
    return "rate limit" in message
