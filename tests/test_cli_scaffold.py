"""Task 3.1 verification: CLI scaffold boots, --help works, missing config fails clearly."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from gh_search.cli import _default_eval_run_id, main
from gh_search.config import ConfigError, load_config


def test_help_does_not_require_env(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "gh-search" in captured.out
    assert "query" in captured.out


def test_no_args_prints_help(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert main([]) == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower() or "gh-search" in captured.out


def test_check_reports_missing_config(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    rc = main(["check"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "OPENAI_API_KEY" in err
    assert "GITHUB_TOKEN" in err
    assert "config error" in err


def test_check_passes_with_config(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")

    rc = main(["check"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "config ok" in out


def test_config_require_raises_for_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "x")

    cfg = load_config()
    with pytest.raises(ConfigError) as exc:
        cfg.require(["openai_api_key", "github_token"])
    assert "OPENAI_API_KEY" in str(exc.value)
    assert "GITHUB_TOKEN" not in str(exc.value)


def test_load_config_never_walks_up_for_dotenv(monkeypatch, tmp_path):
    # Regression: python-dotenv's default find_dotenv() walks up from the
    # CALLER'S file location, which silently picks up the repo's own .env
    # even when the test has chdir'd elsewhere and cleared the env. The only
    # way .env should be loaded is via an explicit path or the CLI's opt-in.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    cfg = load_config()
    assert cfg.openai_api_key is None
    assert cfg.github_token is None


def test_default_eval_run_id_uses_model_name_and_utc_timestamp():
    run_id = _default_eval_run_id(
        "gpt-4.1-mini",
        now=datetime(2026, 4, 25, 1, 2, 3, tzinfo=timezone.utc),
    )

    assert run_id == "gpt-4.1-mini_20260425T010203Z"


@patch("gh_search.cli._resolve_llm")
@patch("gh_search.cli.GitHubClient")
@patch("gh_search.eval.runner.run_smoke_eval")
def test_smoke_defaults_eval_run_id_to_model_plus_timestamp(
    mock_run_smoke_eval, mock_github_cls, mock_resolve_llm, monkeypatch, tmp_path, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    mock_resolve_llm.return_value = MagicMock(
        call=MagicMock(),
        provider_name="openai",
        model_name="gpt-4.1-mini",
    )
    mock_github_cls.return_value = MagicMock()
    mock_run_smoke_eval.return_value = MagicMock(
        model_name="gpt-4.1-mini",
        accuracy=1.0,
        correct=3,
        total=3,
        outcome_counts={"success": 3},
    )

    with patch("gh_search.cli._default_eval_run_id", return_value="gpt-4.1-mini_20260425T010203Z"):
        rc = main(["smoke"])

    assert rc == 0
    assert mock_run_smoke_eval.call_args.kwargs["eval_run_id"] == "gpt-4.1-mini_20260425T010203Z"
    assert "gpt-4.1-mini_20260425T010203Z" in capsys.readouterr().out
