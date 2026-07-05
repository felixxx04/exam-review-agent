import sys
import types
from pathlib import Path

from app.services.embedding_service import EmbeddingService


def test_embedding_service_replaces_missing_ssl_cert_file(monkeypatch):
    EmbeddingService._model = None
    missing_cert = Path("missing-cacert.pem")
    observed_ssl_cert_file = {}

    class FakeSentenceTransformer:
        def __init__(self, model_name):
            observed_ssl_cert_file["value"] = sys.modules["os"].environ.get(
                "SSL_CERT_FILE"
            )
            self.model_name = model_name

        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            return []

        def get_sentence_embedding_dimension(self):
            return 1024

    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    monkeypatch.setenv("SSL_CERT_FILE", str(missing_cert))

    EmbeddingService(model_name="fake-model")

    repaired_cert_file = observed_ssl_cert_file["value"]
    assert repaired_cert_file != str(missing_cert)
    assert repaired_cert_file is not None
    assert Path(repaired_cert_file).exists()

    EmbeddingService._model = None
