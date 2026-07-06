"""Shared in-memory dict store for lightweight persistence stubs."""

from __future__ import annotations


class DictStore:
    def __init__(self) -> None:
        self._records: list[dict] = []

    async def add(self, record: dict) -> None:
        self._records.append(record)

    async def all(self) -> list[dict]:
        return list(self._records)

    async def query(self, filters: dict) -> list[dict]:
        return [
            r for r in self._records
            if all(r.get(k) == v for k, v in filters.items())
        ]

    async def update(self, predicate, updates: dict) -> dict | None:
        for record in self._records:
            if predicate(record):
                record.update(updates)
                return record
        return None


_shared_store = DictStore()


def get_shared_store() -> DictStore:
    return _shared_store
