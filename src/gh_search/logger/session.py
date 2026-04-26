"""SessionLogger — writes the canonical per-session log tree (LOGGING.md §2).

Layout under `log_root`:
    sessions/{session_id}/
      run.json
      turns.jsonl
      final_state.json
      artifacts/turn_XX_<tool>.json
"""
from __future__ import annotations

import json
from pathlib import Path

from gh_search.schemas import FinalState, RunLog, ToolName, TurnLog


class SessionLogger:
    """Write the canonical on-disk artifacts for one agent session."""
    def __init__(self, session_id: str, log_root: Path):
        self._session_id = session_id
        self._root = Path(log_root)
        self.session_dir = self._root / "sessions" / session_id
        self.artifacts_dir = self.session_dir / "artifacts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._turns_path = self.session_dir / "turns.jsonl"

    @property
    def session_id(self) -> str:
        """Expose the session id so callers can thread it into logs and state."""
        return self._session_id

    def append_turn(self, turn: TurnLog) -> None:
        """Append one `TurnLog` row to `turns.jsonl`."""
        if turn.session_id != self._session_id:
            raise ValueError(
                f"turn.session_id={turn.session_id!r} does not match "
                f"logger session_id={self._session_id!r}"
            )
        line = turn.model_dump_json()
        with self._turns_path.open("a", encoding="utf-8") as fp:
            fp.write(line + "\n")

    def write_turn_artifact(
        self, turn_index: int, tool_name: ToolName | str, payload: dict
    ) -> Path:
        """Write the verbose per-turn artifact JSON for later inspection."""
        tool_value = tool_name.value if isinstance(tool_name, ToolName) else tool_name
        artifact = self.artifacts_dir / f"turn_{turn_index:02d}_{tool_value}.json"
        artifact.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return artifact

    def write_retrieval_artifact(self, payload: dict) -> Path:
        """Persist the full retrieval payload for human audit (PHASE2_PLAN §3.1).

        Sibling to `run.json` / `turns.jsonl` so callers can reference it
        by a single path (`retrieved_repositories_path`) without touching
        session internals.
        """
        path = self.session_dir / "retrieved_repositories.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return path

    def finalize(self, run_log: RunLog, final_state: FinalState) -> None:
        """Write the session-level summary files once the loop is finished."""
        if run_log.session_id != self._session_id:
            raise ValueError("run_log.session_id must match logger session_id")
        if final_state.session_id != self._session_id:
            raise ValueError("final_state.session_id must match logger session_id")
        (self.session_dir / "run.json").write_text(run_log.model_dump_json(indent=2))
        (self.session_dir / "final_state.json").write_text(
            final_state.model_dump_json(indent=2)
        )
