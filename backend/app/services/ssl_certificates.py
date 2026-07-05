import os
from pathlib import Path


def ensure_valid_ssl_cert_file() -> None:
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
