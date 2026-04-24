"""Task 3.1 verification: CLI scaffold boots, --help works, missing config fails clearly."""
from __future__ import annotations

import pytest

from gh_search.cli import main
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
