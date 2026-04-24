"""compile_github_query tool (TOOLS.md §3, §8).

Thin application-layer wrapper around the domain compiler. Assumes
validation.is_valid — the loop guarantees this precondition.
"""
from __future__ import annotations

from gh_search.compiler import compile_github_query as _compile_domain
from gh_search.schemas import Control, SharedAgentState, ToolName


def compile_github_query(state: SharedAgentState) -> SharedAgentState:
    assert state.structured_query is not None, (
        "compile_github_query called with no structured_query; "
        "agent loop must gate on validation.is_valid"
    )
    q = _compile_domain(state.structured_query)
    return state.model_copy(
        update={
            "compiled_query": q,
            "control": Control(
                next_tool=ToolName.EXECUTE_GITHUB_SEARCH,
                should_terminate=False,
                terminate_reason=None,
            ),
        }
    )
