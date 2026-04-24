"""Enumerations shared across schemas, tools, and logger.

DRY anchor: every place that checks or emits one of these values must import
from here. Never rewrite the string literals inline.
"""
from __future__ import annotations

from enum import Enum


class IntentStatus(str, Enum):
    SUPPORTED = "supported"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


class SortField(str, Enum):
    STARS = "stars"
    FORKS = "forks"
    UPDATED = "updated"


class OrderDir(str, Enum):
    ASC = "asc"
    DESC = "desc"


class ExecutionStatus(str, Enum):
    NOT_STARTED = "not_started"
    SUCCESS = "success"
    NO_RESULTS = "no_results"
    FAILED = "failed"


class ToolName(str, Enum):
    INTENTION_JUDGE = "intention_judge"
    PARSE_QUERY = "parse_query"
    VALIDATE_QUERY = "validate_query"
    REPAIR_QUERY = "repair_query"
    COMPILE_GITHUB_QUERY = "compile_github_query"
    EXECUTE_GITHUB_SEARCH = "execute_github_search"
    FINALIZE = "finalize"


class TerminateReason(str, Enum):
    AMBIGUOUS_QUERY = "ambiguous_query"
    UNSUPPORTED_INTENT = "unsupported_intent"
    VALIDATION_FAILED = "validation_failed"
    MAX_TURNS_EXCEEDED = "max_turns_exceeded"
    EXECUTION_FAILED = "execution_failed"
