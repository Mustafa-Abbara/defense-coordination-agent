"""Canonical JSON and SHA-256 (ST-02).

"Canonical" means: the same data always gives exactly the same text, whatever
the key order or the machine. That makes hashes comparable.

Used now for the policy version. Later: approval payload_hash (ADR-009, ST-11)
and the event-log hash chain (TH-06, ST-04).
"""

import hashlib
import json
from typing import Any


def canonical_json(data: Any) -> str:
    """Return one fixed JSON text for `data`.

    - sort_keys: {"b":1,"a":2} and {"a":2,"b":1} give the same text.
    - separators without spaces: no formatting differences.
    - ensure_ascii=False: non-ASCII text is kept as-is (UTF-8), not escaped.
    - allow_nan=False: NaN and Infinity are not valid JSON; refuse them.
    Only JSON types are accepted (dict, list, str, int, float, bool, None).
    Convert models first with model_dump(mode="json").
    """
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha256_hex(text: str) -> str:
    """Return the SHA-256 of `text` (encoded as UTF-8) as 64 lowercase hex characters."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
