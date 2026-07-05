import os
from pathlib import Path
from typing import Optional

from app.core.config import settings


class EmbeddingService:
    """Embedding generation using sentence-transformers."""

    _model = None
    _model_name: str = "BAAI/bge-large-zh-v1.5"

    def __init__(self, model_name: Optional[str] = None):
        self._model_name = model_name or self._model_name
        self._ensure_model()

    @classmethod
    def _ensure_model(cls) -> None:
        if cls._model is None:
            if settings.hf_endpoint and not os.environ.get("HF_ENDPOINT"):
                os.environ["HF_ENDPOINT"] = settings.hf_endpoint
            cls._ensure_valid_ssl_cert_file()

            from sentence_transformers import SentenceTransformer

            cls._model = SentenceTransformer(cls._model_name)

    @staticmethod
    def _ensure_valid_ssl_cert_file() -> None:
        ssl_cert_file = os.environ.get("SSL_CERT_FILE")
        if not ssl_cert_file or Path(ssl_cert_file).exists():
            return

        try:
            import certifi
        except ImportError:
            os.environ.pop("SSL_CERT_FILE", None)
            return

        certifi_path = certifi.where()
        if Path(certifi_path).exists():
            os.environ["SSL_CERT_FILE"] = certifi_path
        else:
            os.environ.pop("SSL_CERT_FILE", None)

    @property
    def model(self):
        self._ensure_model()
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        self._ensure_model()
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single query."""
        return self.embed([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for documents."""
        return self.embed(texts)

    @property
    def dim(self) -> int:
        """Return embedding dimension."""
        self._ensure_model()
        return self._model.get_sentence_embedding_dimension() or 1024
