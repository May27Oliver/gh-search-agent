"""execute_github_search tool (TOOLS.md §3 execute_github_search).

Calls the GitHub client, classifies the outcome, and updates state.execution
and state.control. Results are not stored in state (SCHEMAS.md §2 does not
include them); callers that want to render repos pass `results_sink`.
"""
from __future__ import annotations

from gh_search.github import GitHubClient, GitHubError, Repository
from gh_search.schemas import (
    Control,
    Execution,
    ExecutionStatus,
    SharedAgentState,
    TerminateReason,
    ToolName,
)


def execute_github_search(
    state: SharedAgentState,
    github: GitHubClient,
    results_sink: list[Repository] | None = None,
) -> SharedAgentState:
    assert state.structured_query is not None
    assert state.compiled_query is not None

    sort = state.structured_query.sort.value if state.structured_query.sort else None
    order = state.structured_query.order.value if state.structured_query.order else None
    per_page = state.structured_query.limit

    try:
        repos = github.search_repositories(
            query=state.compiled_query, sort=sort, order=order, per_page=per_page
        )
    except GitHubError:
        execution = Execution(
            status=ExecutionStatus.FAILED, response_status=None, result_count=0
        )
        control = Control(
            next_tool=ToolName.FINALIZE,
            should_terminate=True,
            terminate_reason=TerminateReason.EXECUTION_FAILED,
        )
        return state.model_copy(update={"execution": execution, "control": control})

    if results_sink is not None:
        results_sink.extend(repos)

    status = ExecutionStatus.SUCCESS if repos else ExecutionStatus.NO_RESULTS
    execution = Execution(status=status, response_status=200, result_count=len(repos))
    control = Control(
        next_tool=ToolName.FINALIZE, should_terminate=True, terminate_reason=None
    )
    return state.model_copy(update={"execution": execution, "control": control})
