"""Task 3.7 RED: execute_github_search tool (TOOLS.md §3 execute_github_search)."""
from __future__ import annotations

from unittest.mock import MagicMock

from gh_search.github import (
    GitHubAuthError,
    GitHubInvalidQueryError,
    GitHubRateLimitError,
    GitHubTransportError,
    Repository,
)
from gh_search.schemas import (
    Control,
    Execution,
    ExecutionStatus,
    IntentStatus,
    IntentionJudge,
    SharedAgentState,
    StructuredQuery,
    TerminateReason,
    ToolName,
    Validation,
)
from gh_search.tools import execute_github_search


def _compiled_state(limit=10, sort="stars", order="desc"):
    sq = StructuredQuery.model_validate(
        {
            "keywords": ["logistics"],
            "language": "Python",
            "created_after": None,
            "created_before": None,
            "min_stars": 100,
            "max_stars": None,
            "sort": sort,
            "order": order,
            "limit": limit,
        }
    )
    return SharedAgentState(
        run_id="r1",
        turn_index=4,
        max_turns=5,
        user_query="...",
        intention_judge=IntentionJudge(
            intent_status=IntentStatus.SUPPORTED, reason=None, should_terminate=False
        ),
        structured_query=sq,
        validation=Validation(is_valid=True, errors=[], missing_required_fields=[]),
        compiled_query="logistics language:Python stars:>=100",
        execution=Execution(
            status=ExecutionStatus.NOT_STARTED, response_status=None, result_count=None
        ),
        control=Control(
            next_tool=ToolName.EXECUTE_GITHUB_SEARCH,
            should_terminate=False,
            terminate_reason=None,
        ),
    )


def _repo(name="a/b", stars=100):
    return Repository(name=name, url=f"https://github.com/{name}", stars=stars, language="Python")


def test_success_terminates_with_success_outcome():
    github = MagicMock()
    github.search_repositories.return_value = [_repo("a/b"), _repo("c/d")]

    new_state = execute_github_search(_compiled_state(), github=github)

    assert new_state.execution.status is ExecutionStatus.SUCCESS
    assert new_state.execution.response_status == 200
    assert new_state.execution.result_count == 2
    assert new_state.control.next_tool is ToolName.FINALIZE
    assert new_state.control.should_terminate is True
    assert new_state.control.terminate_reason is None


def test_empty_result_set_routes_to_no_results():
    github = MagicMock()
    github.search_repositories.return_value = []

    new_state = execute_github_search(_compiled_state(), github=github)

    assert new_state.execution.status is ExecutionStatus.NO_RESULTS
    assert new_state.execution.result_count == 0
    assert new_state.control.next_tool is ToolName.FINALIZE
    assert new_state.control.should_terminate is True


def test_github_client_called_with_structured_query_params():
    github = MagicMock()
    github.search_repositories.return_value = []
    state = _compiled_state(limit=15, sort="forks", order="asc")

    execute_github_search(state, github=github)

    github.search_repositories.assert_called_once_with(
        query="logistics language:Python stars:>=100",
        sort="forks",
        order="asc",
        per_page=15,
    )


def test_results_sink_receives_repositories():
    github = MagicMock()
    github.search_repositories.return_value = [_repo("a/b")]
    sink: list = []

    execute_github_search(_compiled_state(), github=github, results_sink=sink)

    assert len(sink) == 1
    assert sink[0].name == "a/b"


def test_no_sink_default_does_not_raise():
    github = MagicMock()
    github.search_repositories.return_value = [_repo()]
    # No sink argument; must not raise.
    execute_github_search(_compiled_state(), github=github)


def test_auth_error_marks_execution_failed():
    github = MagicMock()
    github.search_repositories.side_effect = GitHubAuthError("bad token")

    new_state = execute_github_search(_compiled_state(), github=github)

    assert new_state.execution.status is ExecutionStatus.FAILED
    assert new_state.control.terminate_reason is TerminateReason.EXECUTION_FAILED
    assert new_state.control.should_terminate is True


def test_invalid_query_error_marks_execution_failed():
    github = MagicMock()
    github.search_repositories.side_effect = GitHubInvalidQueryError("422")

    new_state = execute_github_search(_compiled_state(), github=github)

    assert new_state.execution.status is ExecutionStatus.FAILED
    assert new_state.control.terminate_reason is TerminateReason.EXECUTION_FAILED


def test_rate_limit_error_marks_execution_failed():
    github = MagicMock()
    github.search_repositories.side_effect = GitHubRateLimitError("limit")

    new_state = execute_github_search(_compiled_state(), github=github)

    assert new_state.execution.status is ExecutionStatus.FAILED
    assert new_state.control.terminate_reason is TerminateReason.EXECUTION_FAILED


def test_transport_error_marks_execution_failed():
    github = MagicMock()
    github.search_repositories.side_effect = GitHubTransportError("connection")

    new_state = execute_github_search(_compiled_state(), github=github)

    assert new_state.execution.status is ExecutionStatus.FAILED
    assert new_state.control.terminate_reason is TerminateReason.EXECUTION_FAILED
