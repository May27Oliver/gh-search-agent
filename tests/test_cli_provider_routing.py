"""CLI --model routes to the right adapter (PHASE2_PLAN §3.0).

Exercises the CLI path where a non-openai model name must reach the
anthropic / deepseek adapter without the caller supplying extra flags. The
factory is patched so no real network / SDK calls occur.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from gh_search.cli import main
from gh_search.github import Repository
from gh_search.llm import LLMResponse


_SUPPORTED = {"intent_status": "supported", "reason": None, "should_terminate": False}
_PARSE_OK = {
    "keywords": ["rails"],
    "language": "Ruby",
    "created_after": None,
    "created_before": None,
    "min_stars": 100,
    "max_stars": None,
    "sort": "stars",
    "order": "desc",
    "limit": 10,
}


def _scripted_llm(*responses):
    calls = iter(responses)

    def fn(_sys, _user, _schema):
        payload = next(calls)
        return LLMResponse(raw_text=json.dumps(payload), parsed=payload)

    return fn


def _setup_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GH_SEARCH_LOG_ROOT", str(tmp_path / "logs"))


@patch("gh_search.cli.make_llm")
@patch("gh_search.cli.GitHubClient")
def test_query_routes_claude_sonnet_4_to_anthropic(
    mock_github_cls, mock_make_llm, monkeypatch, tmp_path
):
    _setup_env(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")

    from gh_search.llm.factory import LLMBinding

    mock_make_llm.return_value = LLMBinding(
        call=_scripted_llm(_SUPPORTED, _PARSE_OK),
        provider_name="anthropic",
        model_name="claude-sonnet-4",
    )
    gh = MagicMock()
    gh.search_repositories.return_value = [
        Repository(name="r/s", url="https://github.com/r/s", stars=500, language="Ruby")
    ]
    mock_github_cls.return_value = gh

    rc = main(["query", "rails ecosystem repos", "--model", "claude-sonnet-4"])
    assert rc == 0

    # make_llm must have been called with the canonical name and the anthropic key.
    assert mock_make_llm.call_args.kwargs["model_name"] == "claude-sonnet-4"
    assert mock_make_llm.call_args.kwargs["anthropic_api_key"] == "ant-test"

    session_dir = next((tmp_path / "logs" / "sessions").iterdir())
    run = json.loads((session_dir / "run.json").read_text())
    assert run["model_name"] == "claude-sonnet-4"
    assert run["provider_name"] == "anthropic"
    assert run["prompt_version"].startswith("core-v1")
    assert "appendix-claude-sonnet-4" in run["prompt_version"]


@patch("gh_search.cli.make_llm")
@patch("gh_search.cli.GitHubClient")
def test_query_routes_deepseek_r1_to_deepseek(
    mock_github_cls, mock_make_llm, monkeypatch, tmp_path
):
    _setup_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")

    from gh_search.llm.factory import LLMBinding

    mock_make_llm.return_value = LLMBinding(
        call=_scripted_llm(_SUPPORTED, _PARSE_OK),
        provider_name="deepseek",
        model_name="deepseek-r1",
    )
    gh = MagicMock()
    gh.search_repositories.return_value = [
        Repository(name="r/s", url="https://github.com/r/s", stars=500, language="Ruby")
    ]
    mock_github_cls.return_value = gh

    rc = main(["query", "rails ecosystem repos", "--model", "DeepSeek-R1"])
    assert rc == 0
    assert mock_make_llm.call_args.kwargs["model_name"] == "deepseek-r1"
    assert mock_make_llm.call_args.kwargs["deepseek_api_key"] == "ds-test"

    session_dir = next((tmp_path / "logs" / "sessions").iterdir())
    run = json.loads((session_dir / "run.json").read_text())
    assert run["model_name"] == "deepseek-r1"
    assert run["provider_name"] == "deepseek"
    assert "appendix-deepseek-r1" in run["prompt_version"]


@patch("gh_search.cli.make_llm")
@patch("gh_search.cli.GitHubClient")
def test_query_fails_cleanly_when_anthropic_key_missing(
    mock_github_cls, mock_make_llm, monkeypatch, tmp_path, capsys
):
    _setup_env(monkeypatch, tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    mock_github_cls.return_value = MagicMock()

    rc = main(["query", "rails ecosystem", "--model", "claude-sonnet-4"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" in err
    # Factory must not be reached if required env var is absent.
    mock_make_llm.assert_not_called()


@patch("gh_search.cli.make_llm")
@patch("gh_search.cli.GitHubClient")
def test_query_rejects_unknown_model(
    mock_github_cls, mock_make_llm, monkeypatch, tmp_path, capsys
):
    _setup_env(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_github_cls.return_value = MagicMock()

    rc = main(["query", "x", "--model", "llama-moo-moo-v42"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "unknown model" in err.lower()
    mock_make_llm.assert_not_called()


@patch("gh_search.cli.GitHubClient")
def test_query_rejects_bogus_provider_override(
    mock_github_cls, monkeypatch, tmp_path, capsys
):
    """Regression: `GH_SEARCH_PROVIDER=anthorpic` (typo) used to escape as
    a bare UnknownModelError traceback. Phase 2 must normalise it to a
    clean config-error exit (1) so the CLI stays boringly predictable."""
    _setup_env(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("GH_SEARCH_PROVIDER", "anthorpic")  # sic
    mock_github_cls.return_value = MagicMock()

    rc = main(["query", "rails ecosystem"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "config error" in err
    assert "unknown provider" in err.lower()
    # Traceback must not leak through.
    assert "Traceback" not in err


def test_check_rejects_bogus_provider_override(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GH_SEARCH_PROVIDER", "gemini")  # unsupported

    rc = main(["check"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "config error" in err
    assert "unknown provider" in err.lower()
    assert "Traceback" not in err
