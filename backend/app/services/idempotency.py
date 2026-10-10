from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def canonical_payload_hash(payload: BaseModel, *, exclude: set[str] | dict[str, Any] | None = None) -> str:
    canonical_payload: Any = payload.model_dump(mode="json", exclude_none=False, exclude=exclude)
    serialized = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def normalize_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError("Idempotency-Key cannot be blank")
    if len(normalized) > 255:
        raise ValueError("Idempotency-Key must not exceed 255 characters")
    return normalized
