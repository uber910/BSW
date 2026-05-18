from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    """Standard error envelope for FastAPI HTTPException responses.

    Used in route ``responses={...}`` declarations so Swagger UI renders the
    exact JSON shape under 4xx/5xx branches. Mirrors FastAPI's default
    ``{"detail": "..."}`` payload from ``HTTPException(detail=...)``.

    D-09 / P5 D-28 duplication policy: this schema is duplicated byte-for-byte
    in ``src/bet_maker/schemas/errors.py``. No cross-service imports.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    detail: str
