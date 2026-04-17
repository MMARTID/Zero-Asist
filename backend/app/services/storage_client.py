"""Google Cloud Storage client for persisting document originals.

The bucket name is read from the ``GCS_BUCKET_NAME`` environment variable.
If the variable is not set, the module operates in no-op mode — uploads are
skipped silently.  This lets the rest of the pipeline work without GCS during
development or local testing.
"""

import logging
import os

logger = logging.getLogger(__name__)

_BUCKET_NAME: str | None = os.environ.get("GCS_BUCKET_NAME")


def _get_client():
    from google.cloud import storage  # lazy import — not required in tests
    return storage.Client()


def build_gcs_path(gestoria_id: str, cuenta_id: str, doc_hash: str, filename: str) -> str:
    """Return the canonical GCS object path for a document."""
    safe = filename.replace("/", "_").replace("\x00", "_")
    return f"{gestoria_id}/{cuenta_id}/{doc_hash}/{safe}"


def upload_document(
    file_bytes: bytes,
    gestoria_id: str,
    cuenta_id: str,
    doc_hash: str,
    filename: str,
    mime_type: str,
) -> str | None:
    """Upload *file_bytes* to GCS.

    Returns the GCS object path on success, or ``None`` when GCS is not
    configured or the upload fails (errors are logged, never raised).
    """
    if not _BUCKET_NAME:
        logger.debug("GCS_BUCKET_NAME not set — skipping original storage for %s", doc_hash)
        return None

    path = build_gcs_path(gestoria_id, cuenta_id, doc_hash, filename)
    try:
        client = _get_client()
        blob = client.bucket(_BUCKET_NAME).blob(path)
        blob.upload_from_string(file_bytes, content_type=mime_type)
        logger.info("Stored original in GCS: %s", path)
        return path
    except Exception:
        logger.warning(
            "GCS upload failed for %s — original will not be stored", doc_hash, exc_info=True
        )
        return None


def download_document(path: str) -> bytes | None:
    """Download the raw bytes for *path* from GCS.

    Returns ``None`` when GCS is not configured or the download fails.
    """
    if not _BUCKET_NAME:
        return None

    try:
        client = _get_client()
        blob = client.bucket(_BUCKET_NAME).blob(path)
        return blob.download_as_bytes()
    except Exception:
        logger.warning("GCS download failed for %s", path, exc_info=True)
        return None
