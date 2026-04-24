"""Task 3.4 RED: GitHub client contract.

Covers:
- 200 path: correct params sent, response normalized to minimal fields
- auth header only when token present
- 401 / 422 / 403 rate-limit / network all raise distinct exception types
- transport error kept separate from logical error (EVAL_EXECUTION_SPEC §7)
"""
from __future__ import annotations

import pytest
import responses

from gh_search.github import (
    GitHubAuthError,
    GitHubClient,
    GitHubInvalidQueryError,
    GitHubRateLimitError,
    GitHubTransportError,
    Repository,
)

SEARCH_URL = "https://api.github.com/search/repositories"


def _sample_item(name="octo/repo", stars=100, language="Python"):
    return {
        "full_name": name,
        "html_url": f"https://github.com/{name}",
        "stargazers_count": stars,
        "language": language,
        "description": "anything",
        "unused_field": "ignored",
    }


def _success_body(*items):
    return {"total_count": len(items), "incomplete_results": False, "items": list(items)}


@responses.activate
def test_search_success_returns_normalized_repositories():
    responses.add(responses.GET, SEARCH_URL, json=_success_body(_sample_item()), status=200)
    client = GitHubClient(token=None)

    repos = client.search_repositories(query="python", sort=None, order=None, per_page=10)

    assert len(repos) == 1
    repo = repos[0]
    assert isinstance(repo, Repository)
    assert repo.name == "octo/repo"
    assert repo.url == "https://github.com/octo/repo"
    assert repo.stars == 100
    assert repo.language == "Python"


@responses.activate
def test_search_sends_all_params():
    responses.add(responses.GET, SEARCH_URL, json=_success_body(), status=200)
    client = GitHubClient(token=None)

    client.search_repositories(query="foo language:Go", sort="stars", order="desc", per_page=7)

    sent = responses.calls[0].request
    assert "q=foo+language%3AGo" in sent.url or "q=foo%20language%3AGo" in sent.url
    assert "sort=stars" in sent.url
    assert "order=desc" in sent.url
    assert "per_page=7" in sent.url


@responses.activate
def test_search_omits_sort_and_order_when_none():
    responses.add(responses.GET, SEARCH_URL, json=_success_body(), status=200)
    client = GitHubClient(token=None)

    client.search_repositories(query="foo", sort=None, order=None, per_page=10)

    sent = responses.calls[0].request
    assert "sort=" not in sent.url
    assert "order=" not in sent.url


@responses.activate
def test_token_sets_authorization_header():
    responses.add(responses.GET, SEARCH_URL, json=_success_body(), status=200)
    client = GitHubClient(token="ghp_abc")

    client.search_repositories(query="foo", sort=None, order=None, per_page=10)

    assert responses.calls[0].request.headers.get("Authorization") == "Bearer ghp_abc"


@responses.activate
def test_no_token_no_authorization_header():
    responses.add(responses.GET, SEARCH_URL, json=_success_body(), status=200)
    client = GitHubClient(token=None)

    client.search_repositories(query="foo", sort=None, order=None, per_page=10)

    assert "Authorization" not in responses.calls[0].request.headers


@responses.activate
def test_401_raises_auth_error():
    responses.add(responses.GET, SEARCH_URL, json={"message": "Bad credentials"}, status=401)
    client = GitHubClient(token="bad")

    with pytest.raises(GitHubAuthError):
        client.search_repositories(query="foo", sort=None, order=None, per_page=10)


@responses.activate
def test_422_raises_invalid_query_error():
    responses.add(
        responses.GET,
        SEARCH_URL,
        json={"message": "Validation Failed", "errors": [{"message": "malformed"}]},
        status=422,
    )
    client = GitHubClient(token=None)

    with pytest.raises(GitHubInvalidQueryError):
        client.search_repositories(query="!!!", sort=None, order=None, per_page=10)


@responses.activate
def test_403_rate_limit_raises_rate_limit_error():
    responses.add(
        responses.GET,
        SEARCH_URL,
        json={"message": "API rate limit exceeded"},
        status=403,
        headers={"X-RateLimit-Remaining": "0"},
    )
    client = GitHubClient(token=None)

    with pytest.raises(GitHubRateLimitError):
        client.search_repositories(query="foo", sort=None, order=None, per_page=10)


@responses.activate
def test_network_failure_raises_transport_error():
    import requests

    responses.add(responses.GET, SEARCH_URL, body=requests.ConnectionError("boom"))
    client = GitHubClient(token=None)

    with pytest.raises(GitHubTransportError):
        client.search_repositories(query="foo", sort=None, order=None, per_page=10)


@responses.activate
def test_response_normalization_handles_null_language():
    responses.add(
        responses.GET,
        SEARCH_URL,
        json=_success_body(_sample_item(language=None)),
        status=200,
    )
    client = GitHubClient(token=None)
    repos = client.search_repositories(query="foo", sort=None, order=None, per_page=10)
    assert repos[0].language is None


@responses.activate
def test_empty_result_set_returns_empty_list():
    responses.add(responses.GET, SEARCH_URL, json=_success_body(), status=200)
    client = GitHubClient(token=None)
    repos = client.search_repositories(query="foo", sort=None, order=None, per_page=10)
    assert repos == []
