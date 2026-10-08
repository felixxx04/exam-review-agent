from __future__ import annotations

import pytest

from app.services.compatibility import compatible_call_kwargs


def test_compatible_call_kwargs_selects_legacy_only_when_modern_signature_does_not_bind():
    def legacy(*, user_id, chunk_ids):
        return None

    selected = compatible_call_kwargs(
        legacy,
        modern={"user_id": 1, "chunk_ids": ["chunk"], "course_id": 2},
        legacy={"user_id": "1", "chunk_ids": ["chunk"]},
    )

    assert selected == {"user_id": "1", "chunk_ids": ["chunk"]}


def test_compatible_call_kwargs_does_not_execute_callable_or_catch_body_errors():
    calls = 0

    def adapter(*, user_id, course_id):
        nonlocal calls
        calls += 1
        raise TypeError("course_id encoding failed inside adapter")

    selected = compatible_call_kwargs(
        adapter,
        modern={"user_id": 1, "course_id": 2},
        legacy={"user_id": "1"},
    )

    with pytest.raises(TypeError, match="course_id encoding"):
        adapter(**selected)

    assert calls == 1
