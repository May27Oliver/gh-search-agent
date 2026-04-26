"""CLI entrypoint for the gh-search agent."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from gh_search import __version__
from gh_search.agent import run_agent_loop
from gh_search.config import Config, ConfigError, load_config
from gh_search.github import GitHubClient, Repository
from gh_search.llm.factory import (
    LLMBinding,
    ProviderConfigError,
    UnknownModelError,
    canonical_model_name,
    make_llm,
    provider_for,
)
from gh_search.logger import SessionLogger
from gh_search.retrieval import (
    build_retrieval_artifact,
    has_retrieval_data,
)
from gh_search.normalizers import KEYWORD_RULES_VERSION
from gh_search.schemas import (
    ExecutionStatus,
    FinalState,
    IntentStatus,
    RunLog,
    SharedAgentState,
    TerminateReason,
)

QUERY_DEFAULT_MODEL = "gpt-4.1-mini"


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser and its three subcommands."""
    parser = argparse.ArgumentParser(
        prog="gh-search",
        description=(
            "Natural-language to GitHub repository search. "
            "Runs a bounded agent loop that parses, validates, compiles, "
            "and executes a repo search."
        ),
    )
    parser.add_argument("--version", action="version", version=f"gh-search {__version__}")

    sub = parser.add_subparsers(dest="command", required=False, metavar="COMMAND")

    q = sub.add_parser("query", help="Run a single natural-language query")
    q.add_argument("text", help="The natural-language query, wrapped in quotes")
    q.add_argument("--max-turns", type=int, default=None, help="Override max agent turns")
    q.add_argument(
        "--model",
        default=QUERY_DEFAULT_MODEL,
        help=f"Parser model to use (default: {QUERY_DEFAULT_MODEL})",
    )

    sub.add_parser("check", help="Validate .env config and exit")

    s = sub.add_parser("smoke", help="Run smoke / baseline eval for one model")
    s.add_argument(
        "--dataset",
        default="datasets/smoke_eval_dataset.json",
        help="Path to smoke dataset (default: datasets/smoke_eval_dataset.json)",
    )
    s.add_argument(
        "--eval-run-id",
        default=None,
        help="Explicit eval_run_id (default: auto-generated)",
    )
    s.add_argument(
        "--artifacts-root",
        default="artifacts/eval",
        help="Where to write eval-level artifacts",
    )
    s.add_argument(
        "--model",
        default=None,
        help=(
            "Canonical model name. Defaults to GH_SEARCH_MODEL. "
            "Supported: gpt-4.1-mini, claude-sonnet-4, deepseek-r1."
        ),
    )

    return parser


def _cmd_query(args: argparse.Namespace) -> int:
    """Run one end-to-end agent session for a user query."""
    cfg = load_config()
    cfg.require(["github_token"])

    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    model = args.model
    max_turns = args.max_turns or cfg.max_turns

    binding = _resolve_llm(cfg, model)
    prompt_version = f"core + appendix-{binding.model_name}"
    llm = binding.call
    github = GitHubClient(token=cfg.github_token)
    logger = SessionLogger(session_id=session_id, log_root=cfg.log_root)

    results_sink: list[Repository] = []
    started_at = _now()

    final_state = run_agent_loop(
        user_query=args.text,
        run_id=run_id,
        llm=llm,
        github=github,
        max_turns=max_turns,
        results_sink=results_sink,
        session_logger=logger,
    )

    ended_at = _now()
    outcome = _derive_final_outcome(final_state)

    if has_retrieval_data(final_state.execution):
        logger.write_retrieval_artifact(
            build_retrieval_artifact(
                repos=results_sink,
                compiled_query=final_state.compiled_query,
                execution=final_state.execution,
            )
        )

    run_log = RunLog(
        session_id=session_id,
        run_id=run_id,
        run_type="cli",
        user_query=args.text,
        model_name=binding.model_name,
        provider_name=binding.provider_name,
        prompt_version=prompt_version,
        keyword_rules_version=KEYWORD_RULES_VERSION,
        final_outcome=outcome,
        terminate_reason=(
            final_state.control.terminate_reason.value
            if final_state.control.terminate_reason is not None
            else None
        ),
        started_at=started_at,
        ended_at=ended_at,
        log_version="1",
    )
    final_state_log = FinalState(
        session_id=session_id,
        run_id=run_id,
        state_type="final",
        turn_index=final_state.turn_index,
        state_payload=final_state,
        created_at=ended_at,
    )
    logger.finalize(run_log=run_log, final_state=final_state_log)

    print(
        _render(
            final_state,
            results_sink,
            session_id=session_id,
            run_id=run_id,
            session_dir=logger.session_dir,
        )
    )
    return 0 if outcome == "success" else 1


def _cmd_smoke(args: argparse.Namespace) -> int:
    """Run the eval runner against the smoke dataset for one model."""
    from pathlib import Path

    from gh_search.eval.runner import run_smoke_eval

    cfg = load_config()
    cfg.require(["github_token"])

    binding = _resolve_llm(cfg, args.model or cfg.model)
    eval_run_id = args.eval_run_id or _default_eval_run_id(binding.model_name)
    prompt_version = f"core + appendix-{binding.model_name}"
    github = GitHubClient(token=cfg.github_token)

    summary = run_smoke_eval(
        dataset_path=Path(args.dataset),
        llm=binding.call,
        github=github,
        log_root=cfg.log_root,
        eval_artifacts_root=Path(args.artifacts_root),
        eval_run_id=eval_run_id,
        model_name=binding.model_name,
        provider_name=binding.provider_name,
        prompt_version=prompt_version,
        max_turns=cfg.max_turns,
    )

    print(
        f"[{eval_run_id}] model={summary.model_name} "
        f"accuracy={summary.accuracy:.2%} "
        f"correct={summary.correct}/{summary.total} "
        f"outcomes={summary.outcome_counts}"
    )
    return 0 if summary.correct == summary.total else 1


def _cmd_check(_: argparse.Namespace) -> int:
    """Validate the active config for the default provider and exit."""
    cfg = load_config()
    try:
        canonical = canonical_model_name(cfg.model)
        provider = provider_for(canonical)
    except UnknownModelError as exc:
        raise ConfigError(str(exc)) from exc

    cfg.require(["github_token", _required_key_for(provider)])
    print(
        f"config ok (model={canonical}, provider={provider}, "
        f"max_turns={cfg.max_turns}, log_root={cfg.log_root})"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI args, dispatch the selected command, and return a process exit code.

    Exit-code contract:
    - `0`: successful execution, including bare `gh-search` help output
    - `1`: config or runtime failure reported by this CLI layer
    - `2`: command-line usage error detected by argparse
    """
    # Opt-in, cwd-scoped .env load. Never walks up — tests that monkeypatch
    # cwd to a scratch dir will see an empty environment.
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        load_dotenv(cwd_env, override=False)

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    try:
        if args.command == "query":
            return _cmd_query(args)
        if args.command == "check":
            return _cmd_check(args)
        if args.command == "smoke":
            return _cmd_smoke(args)
    except ConfigError as exc:
        sys.stderr.write(f"config error: {exc}\n")
        return 1

    # argparse treats an unknown subcommand as a usage error and exits with
    # status 2. The explicit return is only a defensive fallback.
    parser.error(f"unknown command: {args.command}")
    return 2


def _resolve_llm(cfg: Config, model_name: str) -> LLMBinding:
    """Route a raw model name to the right provider adapter (PHASE2_PLAN §3.0)."""
    try:
        canonical = canonical_model_name(model_name)
        provider = provider_for(canonical)
    except UnknownModelError as exc:
        raise ConfigError(str(exc)) from exc

    cfg.require([_required_key_for(provider)])

    try:
        return make_llm(
            model_name=canonical,
            openai_api_key=cfg.openai_api_key,
            anthropic_api_key=cfg.anthropic_api_key,
            deepseek_api_key=cfg.deepseek_api_key,
            deepseek_endpoint=cfg.deepseek_endpoint,
        )
    except (ProviderConfigError, UnknownModelError) as exc:
        raise ConfigError(str(exc)) from exc


def _required_key_for(provider: str) -> str:
    """Map a provider name to the config field that must be present."""
    required = {
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "deepseek": "deepseek_api_key",
    }.get(provider)
    if required is None:
        raise ConfigError(f"unknown provider mapping for {provider!r}")
    return required


def _now() -> str:
    """Return the current UTC timestamp in ISO 8601 form."""
    return datetime.now(tz=timezone.utc).isoformat()


def _default_eval_run_id(model_name: str, now: datetime | None = None) -> str:
    """Build a stable default smoke-eval run id from model name and UTC time."""
    timestamp = (now or datetime.now(tz=timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"{model_name}_{timestamp}"


def _derive_final_outcome(state: SharedAgentState) -> str:
    """Collapse the final agent state into the CLI/eval outcome label."""
    if state.intention_judge.intent_status is IntentStatus.UNSUPPORTED:
        return "rejected"
    if state.intention_judge.intent_status is IntentStatus.AMBIGUOUS:
        return "rejected"
    if state.control.terminate_reason is TerminateReason.VALIDATION_FAILED:
        return "validation_failed"
    if state.control.terminate_reason is TerminateReason.EXECUTION_FAILED:
        return "execution_failed"
    if state.control.terminate_reason is TerminateReason.MAX_TURNS_EXCEEDED:
        return "max_turns_exceeded"
    if state.execution.status is ExecutionStatus.SUCCESS:
        return "success"
    if state.execution.status is ExecutionStatus.NO_RESULTS:
        return "no_results"
    return "unknown"


def _render(
    state: SharedAgentState,
    repos: list[Repository],
    session_id: str,
    run_id: str,
    session_dir: Path | None = None,
) -> str:
    """Render a human-facing summary of the finished session."""
    outcome = _derive_final_outcome(state)
    header = f"[{outcome}] session_id={session_id} run_id={run_id}"
    terminate_val = (
        state.control.terminate_reason.value
        if state.control.terminate_reason is not None
        else None
    )

    if outcome == "success":
        lines = [header, f"compiled query: {state.compiled_query}", ""]
        for r in repos:
            lang = r.language or "-"
            lines.append(f"  {r.name}  ★{r.stars}  [{lang}]  {r.url}")
        return "\n".join(lines)

    # All failure paths below get a trailing suggestion per LOGGING.md §8.
    suggestion = _suggestion_for(outcome)

    if outcome == "no_results":
        return "\n".join(
            [header, f"no repositories matched: {state.compiled_query}", f"suggestion: {suggestion}"]
        )
    if outcome == "rejected":
        reason = state.intention_judge.reason or "query was rejected"
        return "\n".join(
            [header, f"rejected ({terminate_val}): {reason}", f"suggestion: {suggestion}"]
        )
    if outcome == "validation_failed":
        errs = "; ".join(issue.message for issue in state.validation.errors) or "unknown validation failure"
        return "\n".join([header, f"validation failed: {errs}", f"suggestion: {suggestion}"])
    if outcome == "execution_failed":
        return "\n".join(
            [header, "GitHub search failed; see session logs for details", f"suggestion: {suggestion}"]
        )
    if outcome == "max_turns_exceeded":
        lines = [header, f"reached max_turns={state.max_turns} without producing a result"]
        lines.extend(_per_turn_summary(session_dir))
        lines.append(f"final reason: {terminate_val}")
        lines.append(f"suggestion: {suggestion}")
        return "\n".join(lines)
    return f"{header}\nunknown outcome"


def _suggestion_for(outcome: str) -> str:
    """Return the canned next-step hint for a non-success outcome."""
    mapping = {
        "no_results": "try broader keywords or relax star / date constraints",
        "rejected": "refine your question to describe a specific GitHub repository search",
        "validation_failed": "restate your query with consistent numeric and date ranges",
        "execution_failed": "retry in a moment; check GITHUB_TOKEN if the error persists",
        "max_turns_exceeded": "refine the query to be more specific; the agent could not converge",
    }
    return mapping.get(outcome, "try rephrasing your query")


def _per_turn_summary(session_dir: Path | None) -> list[str]:
    """Summarize turn transitions from `turns.jsonl` for max-turn failures."""
    if session_dir is None:
        return []
    turns_path = session_dir / "turns.jsonl"
    if not turns_path.is_file():
        return []
    out: list[str] = ["per-turn summary:"]
    for raw in turns_path.read_text().splitlines():
        if not raw.strip():
            continue
        t = json.loads(raw)
        tool = t.get("tool_name")
        next_action = t.get("next_action")
        errors = t.get("validation_errors") or []
        err_codes = [e["code"] for e in errors]
        err_str = f" errors={err_codes}" if err_codes else ""
        out.append(
            f"  turn_{int(t['turn_index']):02d}: {tool} -> {next_action}{err_str}"
        )
    return out
