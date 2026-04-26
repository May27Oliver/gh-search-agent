"""Environment-based config loading.

Loaded lazily so that `--help` never requires any env var to be set.
Phase 2 extends the surface with provider-specific keys so `make_llm(...)`
can route `gpt-4.1-mini`, `claude-sonnet-4`, and `deepseek-r1`
without the CLI hard-coding a single provider.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    pass


_ENV_NAMES: dict[str, str] = {
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "deepseek_endpoint": "DEEPSEEK_ENDPOINT",
    "github_token": "GITHUB_TOKEN",
}


@dataclass(frozen=True)
class Config:
    openai_api_key: str | None
    anthropic_api_key: str | None
    deepseek_api_key: str | None
    deepseek_endpoint: str | None
    github_token: str | None
    model: str
    max_turns: int
    log_root: Path

    def require(self, keys: Iterable[str]) -> None:
        missing = [k for k in keys if getattr(self, k, None) in (None, "")]
        if missing:
            pretty = ", ".join(_ENV_NAMES.get(k, k.upper()) for k in missing)
            raise ConfigError(
                f"Missing required environment variable(s): {pretty}. "
                f"Copy .env.example to .env and fill in the values."
            )


def load_config(env_file: Path | None = None) -> Config:
    # NEVER call load_dotenv() without an explicit path: python-dotenv's
    # find_dotenv() walks up the filesystem from THIS module's location, which
    # silently picks up the repo's own .env regardless of the caller's cwd or
    # monkeypatched env vars. Explicit path only.
    if env_file is not None and Path(env_file).exists():
        load_dotenv(env_file, override=False)

    try:
        max_turns = int(os.getenv("GH_SEARCH_MAX_TURNS", "5"))
    except ValueError as exc:
        raise ConfigError(f"GH_SEARCH_MAX_TURNS must be an integer: {exc}") from exc

    return Config(
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
        deepseek_endpoint=os.getenv("DEEPSEEK_ENDPOINT") or None,
        github_token=os.getenv("GITHUB_TOKEN") or None,
        model=os.getenv("GH_SEARCH_MODEL", "gpt-4.1-mini"),
        max_turns=max_turns,
        log_root=Path(os.getenv("GH_SEARCH_LOG_ROOT", "artifacts/logs")),
    )
