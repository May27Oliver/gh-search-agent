"""StructuredQuery — the MVP domain aggregate (SCHEMAS.md §1)."""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gh_search.schemas.enums import OrderDir, SortField

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if not _DATE_RE.match(value):
        raise ValueError(f"{field} must be YYYY-MM-DD, got {value!r}")
    return value


class StructuredQuery(BaseModel):
    """The canonical structured representation of a GitHub repository search.

    Invariants:
    - every field is required (null must be explicit)
    - no unknown fields permitted
    - keywords is a list, never null
    - sort=null implies order=null
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    keywords: list[str] = Field(...)
    language: str | None = Field(...)
    created_after: str | None = Field(...)
    created_before: str | None = Field(...)
    min_stars: int | None = Field(..., ge=0)
    max_stars: int | None = Field(..., ge=0)
    sort: SortField | None = Field(...)
    order: OrderDir | None = Field(...)
    limit: int = Field(..., ge=1, le=20)

    @model_validator(mode="after")
    def _check_invariants(self) -> "StructuredQuery":
        _validate_date(self.created_after, "created_after")
        _validate_date(self.created_before, "created_before")
        if self.sort is None and self.order is not None:
            raise ValueError("order must be null when sort is null")
        return self
