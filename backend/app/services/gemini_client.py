# gemini_client.py
"""Two-phase Gemini extraction: classify → extract with type-specific schema.

Retry strategy: 5 attempts on gemini-2.5-flash, then 5 more on gemini-2.0-flash.
"""

import os
import json
import logging
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from google.genai import Client, types
from app.models.document import ClassificationResult, DocumentType
from app.models.registry import DOCUMENT_TYPE_REGISTRY
from app.services.errors import PipelineError

logger = logging.getLogger(__name__)

load_dotenv()

client = Client(api_key=os.getenv("GEMINI_API_KEY"))

PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-2.5-flash-lite"
RETRIES_PER_MODEL = 5

CLASSIFICATION_PROMPT = (
    "Clasifica este documento en exactamente uno de los siguientes tipos:\n"
    "- invoice_received: factura de gasto recibida de un proveedor\n"
    "- invoice_sent: factura emitida a un cliente\n"
    "- payment_receipt: justificante o comprobante de pago\n"
    "- administrative_notice: documento fiscal, tributario o administrativo\n"
    "- bank_document: extracto bancario, aviso del banco o movimiento\n"
    "- contract: contrato, acuerdo legal o documento vinculante\n"
    "- expense_ticket: ticket de compra o justificante de gasto menor\n"
    "- other: cualquier otro tipo de documento\n"
    "Responde únicamente con el JSON estructurado."
)


def _is_retryable(exc: BaseException) -> bool:
    """Return True for 503/UNAVAILABLE, 429/RATE_LIMIT and transient parse errors."""
    if isinstance(exc, PipelineError):
        return exc.code in ("UNAVAILABLE", "RATE_LIMIT", "PARSE_ERROR")
    msg = str(exc).upper()
    return "503" in msg or "UNAVAILABLE" in msg or "429" in msg or "RESOURCE_EXHAUSTED" in msg


def _build_contents(file_bytes: bytes, mime_type: str) -> list:
    """Convert raw file bytes into a Gemini-compatible contents list."""
    if mime_type.startswith("image/") or mime_type == "application/pdf":
        return [types.Part.from_bytes(data=file_bytes, mime_type=mime_type)]

    if mime_type in ("application/xml", "text/xml") or file_bytes.startswith(b"<?xml"):
        try:
            return [file_bytes.decode("utf-8")]
        except UnicodeDecodeError:
            return [file_bytes.decode("latin-1")]

    raise ValueError(f"Tipo MIME no soportado: {mime_type}")


def _call_gemini(model: str, contents: list, config: types.GenerateContentConfig):
    """Single Gemini call with error wrapping."""
    try:
        return client.models.generate_content(
            model=model, contents=contents, config=config,
        )
    except PipelineError:
        raise
    except Exception as e:
        raise PipelineError.from_exception(e) from e


def _call_with_fallback(make_call):
    """Execute make_call(model) with retries, falling back to FALLBACK_MODEL.

    make_call receives a model name and must return the final parsed result.
    Both API errors and parse errors are retried (up to RETRIES_PER_MODEL per model).
    """

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(RETRIES_PER_MODEL),
        reraise=True,
    )
    def _try_primary():
        return make_call(PRIMARY_MODEL)

    try:
        return _try_primary()
    except Exception as primary_err:
        if not _is_retryable(primary_err):
            raise
        logger.warning(
            "%s agotó %d reintentos, cambiando a %s",
            PRIMARY_MODEL, RETRIES_PER_MODEL, FALLBACK_MODEL,
        )

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(RETRIES_PER_MODEL),
        reraise=True,
    )
    def _try_fallback():
        return make_call(FALLBACK_MODEL)

    return _try_fallback()


def classify_document(file_bytes: bytes, mime_type: str) -> str:
    """Phase 1: classify the document type (lightweight, ~100 tokens)."""
    contents = _build_contents(file_bytes, mime_type)
    config = types.GenerateContentConfig(
        system_instruction=CLASSIFICATION_PROMPT,
        temperature=0,
        top_p=0.95,
        top_k=1,
        max_output_tokens=256,
        response_mime_type="application/json",
        response_schema=ClassificationResult,
    )

    def _classify(model):
        response = _call_gemini(model, contents, config)
        try:
            raw = json.loads(response.text)
            result = ClassificationResult.model_validate(raw)
        except Exception as e:
            logger.warning("Gemini classify parse error (%s): %s", type(e).__name__, e)
            raise PipelineError.from_exception(e) from e
        return result.document_type.value

    return _call_with_fallback(_classify)


def extract_document(file_bytes: bytes, mime_type: str, document_type: str) -> dict:
    """Phase 2: extract fields using the type-specific schema and prompt."""
    type_config = DOCUMENT_TYPE_REGISTRY.get(document_type)
    if not type_config or not type_config.extraction_schema:
        raise ValueError(f"No extraction schema registered for type: {document_type}")

    contents = _build_contents(file_bytes, mime_type)
    config = types.GenerateContentConfig(
        system_instruction=type_config.prompt,
        temperature=0,
        top_p=0.95,
        top_k=1,
        max_output_tokens=4096,
        response_mime_type="application/json",
        response_schema=type_config.extraction_schema,
    )

    def _extract(model):
        response = _call_gemini(model, contents, config)
        try:
            raw = json.loads(response.text)
            validated = type_config.extraction_schema.model_validate(raw)
        except Exception as e:
            logger.warning("Gemini extract parse error (%s): %s", type(e).__name__, e)
            raise PipelineError.from_exception(e) from e
        return validated.model_dump()

    return _call_with_fallback(_extract)
