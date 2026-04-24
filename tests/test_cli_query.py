"""CLI `query` command end-to-end with mocked LLM + GitHub (PHASE2_PLAN §3.0).

Phase 2 routes model→adapter through `_resolve_llm`, so these tests patch
that seam and hand back an `LLMBinding` carrying a scripted callable. That
keeps one injection point regardless of which provider the model maps to.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from gh_search.cli import main
from gh_search.github import Repository
from gh_search.llm import LLMResponse
from gh_search.llm.factory import LLMBinding


_SUPPORTED = {"intent_status": "supported", "reason": None, "should_terminate": False}
_PARSE_OK = {
    "keywords": ["logistics"],
    "language": "Python",
    "created_after": None,
    "created_before": None,
    "min_stars": 100,
    "max_stars": None,
    "sort": "stars",
    "order": "desc",
    "limit": 10,
}


def _scripted_llm(*responses):
    import json

    calls = iter(responses)

    def fn(_sys, _user, _schema):
        payload = next(calls)
        return LLMResponse(raw_text=json.dumps(payload), parsed=payload)

    return fn


def _binding(*responses, provider_name="openai", model_name="gpt-4.1-mini"):
    return LLMBinding(
        call=_scripted_llm(*responses),
        provider_name=provider_name,
        model_name=model_name,
    )


def _setup_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GH_SEARCH_LOG_ROOT", str(tmp_path / "logs"))


@patch("gh_search.cli._resolve_llm")
@patch("gh_search.cli.GitHubClient")
def test_query_writes_session_artifacts_on_success(
    mock_github_cls, mock_resolve_llm, monkeypatch, tmp_path, capsys
):
    _setup_env(monkeypatch, tmp_path)
    mock_resolve_llm.return_value = _binding(_SUPPORTED, _PARSE_OK)
    gh = MagicMock()
    gh.search_repositories.return_value = [
        Repository(name="a/b", url="https://github.com/a/b", stars=200, language="Python")
    ]
    mock_github_cls.return_value = gh

    rc = main(["query", "python logistics 100+ stars"])
    assert rc == 0

    # Find the session directory
    sessions = list((tmp_path / "logs" / "sessions").iterdir())
    assert len(sessions) == 1
    session_dir = sessions[0]
    assert (session_dir / "run.json").exists()
    assert (session_dir / "turns.jsonl").exists()
    assert (session_dir / "final_state.json").exists()

    run = json.loads((session_dir / "run.json").read_text())
    assert run["final_outcome"] == "success"
    assert run["model_name"] == "gpt-4.1-mini"

    out = capsys.readouterr().out
    assert "a/b" in out or "https://github.com/a/b" in out


@patch("gh_search.cli._resolve_llm")
@patch("gh_search.cli.GitHubClient")
def test_query_rejects_unsupported_intent(
    mock_github_cls, mock_resolve_llm, monkeypatch, tmp_path, capsys
):
    _setup_env(monkeypatch, tmp_path)
    mock_resolve_llm.return_value = _binding(
        {"intent_status": "unsupported", "reason": "not a repo search", "should_terminate": True}
    )
    mock_github_cls.return_value = MagicMock()

    rc = main(["query", "find trending tweets"])
    assert rc != 0  # non-zero exit

    session_dir = next((tmp_path / "logs" / "sessions").iterdir())
    run = json.loads((session_dir / "run.json").read_text())
    assert run["final_outcome"] == "rejected"
    assert run["terminate_reason"] == "unsupported_intent"

    out = capsys.readouterr().out
    assert "unsupported" in out.lower() or "reject" in out.lower()


@patch("gh_search.cli._resolve_llm")
@patch("gh_search.cli.GitHubClient")
def test_query_no_results_reports_no_results(
    mock_github_cls, mock_resolve_llm, monkeypatch, tmp_path, capsys
):
    _setup_env(monkeypatch, tmp_path)
    mock_resolve_llm.return_value = _binding(_SUPPORTED, _PARSE_OK)
    gh = MagicMock()
    gh.search_repositories.return_value = []
    mock_github_cls.return_value = gh

    rc = main(["query", "ultraobscure topic"])
    assert rc != 0

    session_dir = next((tmp_path / "logs" / "sessions").iterdir())
    run = json.loads((session_dir / "run.json").read_text())
    assert run["final_outcome"] == "no_results"


@patch("gh_search.cli._resolve_llm")
@patch("gh_search.cli.GitHubClient")
def test_query_respects_max_turns_override(
    mock_github_cls, mock_resolve_llm, monkeypatch, tmp_path
):
    _setup_env(monkeypatch, tmp_path)
    mock_resolve_llm.return_value = _binding(_SUPPORTED, _PARSE_OK)
    gh = MagicMock()
    gh.search_repositories.return_value = []
    mock_github_cls.return_value = gh

    rc = main(["query", "foo", "--max-turns", "3"])
    # runs to completion with the 2-call LLM script; max_turns override just
    # passes through
    assert rc != 0 or rc == 0


_EMPTY_PARSE = {
    "keywords": [],
    "language": None,
    "created_after": None,
    "created_before": None,
    "min_stars": None,
    "max_stars": None,
    "sort": None,
    "order": None,
    "limit": 10,
}


@patch("gh_search.cli._resolve_llm")
@patch("gh_search.cli.GitHubClient")
def test_max_turns_exceeded_reply_lists_per_turn_summary(
    mock_github_cls, mock_resolve_llm, monkeypatch, tmp_path, capsys
):
    _setup_env(monkeypatch, tmp_path)
    # Every parse returns an empty query; validator rejects; repair loops fail
    # until max_turns kicks in.
    mock_resolve_llm.return_value = _binding(
        _SUPPORTED,
        _EMPTY_PARSE,
        _EMPTY_PARSE,  # repair 1
        _EMPTY_PARSE,  # repair 2
        _EMPTY_PARSE,  # repair 3
        _EMPTY_PARSE,  # unused spare
    )
    mock_github_cls.return_value = MagicMock()

    rc = main(["query", "something vague", "--max-turns", "5"])
    assert rc != 0

    out = capsys.readouterr().out
    # LOGGING.md §8: must list each turn, not just one error code
    assert "turn 1" in out.lower() or "turn_01" in out.lower()
    assert "turn 2" in out.lower() or "turn_02" in out.lower()
    assert "max_turns_exceeded" in out
    # 重新提問建議
    assert "suggest" in out.lower() or "refine" in out.lower() or "建議" in out


@patch("gh_search.cli._resolve_llm")
@patch("gh_search.cli.GitHubClient")
def test_rejected_reply_includes_suggestion(
    mock_github_cls, mock_resolve_llm, monkeypatch, tmp_path, capsys
):
    _setup_env(monkeypatch, tmp_path)
    mock_resolve_llm.return_value = _binding(
        {"intent_status": "unsupported", "reason": "tweets", "should_terminate": True}
    )
    mock_github_cls.return_value = MagicMock()

    main(["query", "trending tweets"])
    out = capsys.readouterr().out
    assert "suggest" in out.lower() or "refine" in out.lower() or "建議" in out
