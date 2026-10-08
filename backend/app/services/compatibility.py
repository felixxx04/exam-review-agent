"""Helpers for adapting call signatures without retrying executed side effects."""

from __future__ import annotations

import inspect
from typing import Any, Callable


def compatible_call_kwargs(
    callable_obj: Callable[..., Any],
    *,
    modern: dict[str, Any],
    legacy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Choose kwargs by binding signatures before invoking ``callable_obj``.

    This helper deliberately never invokes the callable.  A ``TypeError`` from
    an adapter body therefore cannot trigger a second side-effecting attempt.
    If introspection is unavailable, the modern contract is used and any
    execution error is allowed to propagate.
    """
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return modern

    try:
        signature.bind(**modern)
    except TypeError as modern_error:
        if legacy is None:
            raise modern_error
        try:
            signature.bind(**legacy)
        except TypeError:
            raise modern_error
        return legacy
    return modern
