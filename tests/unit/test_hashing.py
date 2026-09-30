"""Canonical JSON and SHA-256 helpers (ST-02).

The same helpers will hash approval payloads (ST-11) and event-log rows (ST-04),
so "same data gives the same hash" must hold on every machine.
"""

import math

import pytest

from app.core.hashing import canonical_json, sha256_hex


def test_key_order_does_not_change_the_text() -> None:
    assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json({"a": [1, 2], "b": 1})


def test_canonical_text_has_no_spaces() -> None:
    assert canonical_json({"a": 1, "b": [1, 2]}) == '{"a":1,"b":[1,2]}'


def test_non_ascii_text_is_kept_readable() -> None:
    assert canonical_json({"name": "Beyrouth é"}) == '{"name":"Beyrouth é"}'


def test_sha256_of_known_text() -> None:
    # Reference value from the SHA-256 standard test vectors.
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert sha256_hex("abc") == expected


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_nan_and_infinity_are_rejected(bad: float) -> None:
    # NaN is not valid JSON and NaN != NaN, so two "equal" payloads could differ.
    with pytest.raises(ValueError):
        canonical_json({"x": bad})


def test_non_json_types_are_rejected() -> None:
    # Callers must convert first (for example model_dump(mode="json")), so that
    # the hash never depends on Python's str() of an object.
    with pytest.raises(TypeError):
        canonical_json({"x": object()})
