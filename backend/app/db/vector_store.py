import uuid
from typing import Optional

import chromadb

from app.core.config import settings


class VectorStore:
    """ChromaDB vector store wrapper with collection-per-user pattern."""

    def __init__(self, persist_dir: Optional[str] = None):
        self._persist_dir = persist_dir or settings.chroma_persist_dir
        self._client = chromadb.PersistentClient(path=self._persist_dir)

    def _collection_name(self, user_id: str) -> str:
        return f"chunks_{user_id}"

    def _get_or_create_collection(self, user_id: str):
        name = self._collection_name(user_id)
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        user_id: str,
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
        ids: Optional[list[str]] = None,
    ) -> list[str]:
        """Add documents with embeddings. Returns list of chunk IDs."""
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in documents]
        collection = self._get_or_create_collection(user_id)
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        return ids

    def search(
        self,
        user_id: str,
        query_embedding: list[float],
        top_k: int = 10,
        metadata_filter: Optional[dict] = None,
    ) -> list[dict]:
        """Search for similar documents. Returns list of {id, document, metadata, distance}."""
        collection = self._get_or_create_collection(user_id)
        where_filter = metadata_filter if metadata_filter else None
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
        )
        items = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                item = {
                    "id": doc_id,
                    "document": (
                        results["documents"][0][i]
                        if results["documents"] and results["documents"][0]
                        else ""
                    ),
                    "metadata": (
                        results["metadatas"][0][i]
                        if results["metadatas"] and results["metadatas"][0]
                        else {}
                    ),
                    "distance": (
                        results["distances"][0][i]
                        if results["distances"] and results["distances"][0]
                        else 1.0
                    ),
                }
                items.append(item)
        return items

    def delete(self, user_id: str, ids: list[str]) -> None:
        """Delete documents by ID."""
        collection = self._get_or_create_collection(user_id)
        collection.delete(ids=ids)

    def delete_collection(self, user_id: str) -> None:
        """Delete entire user collection."""
        name = self._collection_name(user_id)
        try:
            self._client.delete_collection(name)
        except Exception:
            pass

    def count(self, user_id: str) -> int:
        """Get count of documents in user collection."""
        collection = self._get_or_create_collection(user_id)
        return collection.count()
