"""Shared in-memory dict store for lightweight persistence stubs."""

from __future__ import annotations


class DictStore:
    def __init__(self) -> None:
        self._records: list[dict] = []

    async def add(self, record: dict) -> None:
        self._records.append(record)

    async def query(self, filters: dict) -> list[dict]:
        return [
            r for r in self._records
            if all(r.get(k) == v for k, v in filters.items())
        ]


_shared_store = DictStore()


def get_shared_store() -> DictStore:
    return _shared_store
