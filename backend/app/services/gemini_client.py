# gemini_client.py
"""Gemini API client with configurable retry strategies.

Document extraction (classify + extract): 1 attempt on gemini-2.5-flash, 3 on gemini-2.5-flash-lite.
Import normalization (CSV/Excel): 1 attempt on gemini-3-pro, 1 on gemini-2.5-flash, 3 on gemini-2.5-flash-lite.
Total timeout: 300 seconds (5 minutes) per operation.
"""

import os
import json
import logging
import time
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from google.genai import Client, types
from app.models.document import ClassificationResult, DocumentType
from app.models.registry import DOCUMENT_TYPE_REGISTRY
from app.ingestion.context import CuentaContext
from app.services.errors import PipelineError

logger = logging.getLogger(__name__)

load_dotenv()

client = Client(api_key=os.getenv("GEMINI_API_KEY"))

# Retry strategy constants
# For document extraction (classify + extract)
PRIMARY_MODEL = "gemini-2.5-flash"
PRIMARY_RETRIES = 1  # 2 total attempts
FALLBACK_MODEL = "gemini-2.5-flash-lite"
FALLBACK_RETRIES = 3  # 4 total attempts

# For import normalization
IMPORT_PRIMARY_MODEL = "gemini-2.5-pro"
IMPORT_PRIMARY_RETRIES = 0  # 1 total attempt (fail fast)
IMPORT_SECONDARY_MODEL = "gemini-2.5-flash"
IMPORT_SECONDARY_RETRIES = 1  # 2 total attempts
IMPORT_TERTIARY_MODEL = "gemini-2.5-flash-lite"
IMPORT_TERTIARY_RETRIES = 3  # 4 total attempts

TOTAL_TIMEOUT = 300  # 5 minutes total timeout per operation

CLASSIFICATION_PROMPT = (
    "Clasifica este documento en exactamente uno de los siguientes tipos:\n"
    "- invoice_received: factura de gasto recibida de un proveedor (la cuenta es el RECEPTOR/CLIENTE)\n"
    "- invoice_sent: factura emitida a un cliente (la cuenta es el EMISOR)\n"
    "- payment_receipt: justificante o comprobante de pago\n"
    "- administrative_notice: documento fiscal, tributario o administrativo\n"
    "- bank_document: extracto bancario, aviso del banco o movimiento\n"
    "- contract: contrato, acuerdo legal o documento vinculante\n"
    "- expense_ticket: ticket de compra o justificante de gasto menor\n"
    "- other: cualquier otro tipo de documento\n\n"
    "REGLA CLAVE para distinguir invoice_received de invoice_sent:\n"
    "1. Localiza el EMISOR (quien emite/firma la factura) y el RECEPTOR/CLIENTE.\n"
    "2. Compara el NIF/CIF/nombre del EMISOR y del RECEPTOR con los datos de la cuenta.\n"
    "3. Si la cuenta coincide con el EMISOR → invoice_sent.\n"
    "4. Si la cuenta coincide con el RECEPTOR/CLIENTE → invoice_received.\n"
    "5. Ignora prefijos de país al comparar (ej: ESB12345678 = B12345678).\n"
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


def _call_with_retry_chain(make_call, model_attempts_list):
    """Execute make_call with a chain of (model, num_attempts) pairs.
    
    Tries each model in sequence with exponential backoff retry.
    If retryable error and not last model, falls back to next.
    If last model fails, raises the error.
    
    Args:
        make_call: callable(model) -> result (may raise PipelineError)
        model_attempts_list: [(model_name, num_attempts), ...]
                            num_attempts = 1 means 0 retries, 2 means 1 retry, etc.
    """
    start_time = time.time()
    last_error = None
    
    for model_idx, (model, num_attempts) in enumerate(model_attempts_list):
        is_last = (model_idx == len(model_attempts_list) - 1)
        
        @retry(
            retry=retry_if_exception(_is_retryable),
            wait=wait_exponential(multiplier=1, min=2, max=60),
            stop=stop_after_attempt(num_attempts),
            reraise=True,
        )
        def _try_model():
            if time.time() - start_time > TOTAL_TIMEOUT:
                raise PipelineError(
                    code="TIMEOUT",
                    message=f"Gemini operation exceeded total timeout of {TOTAL_TIMEOUT}s",
                )
            return make_call(model)
        
        try:
            return _try_model()
        except Exception as e:
            last_error = e
            if _is_retryable(e) and not is_last:
                next_model = model_attempts_list[model_idx + 1][0]
                logger.warning(
                    "%s agotó %d intento(s), cambiando a %s",
                    model, num_attempts, next_model,
                )
                continue
            else:
                raise
    
    # Should not reach here, but just in case
    if last_error:
        raise last_error


def _call_with_fallback(make_call):
    """Execute make_call with standard retry chain for document extraction.
    
    Uses: gemini-2.5-flash (1 retry) → gemini-2.5-flash-lite (3 retries).
    """
    return _call_with_retry_chain(
        make_call,
        [
            (PRIMARY_MODEL, PRIMARY_RETRIES + 1),
            (FALLBACK_MODEL, FALLBACK_RETRIES + 1),
        ],
    )


def classify_document(
    file_bytes: bytes,
    mime_type: str,
    cuenta_context: CuentaContext | None = None,
) -> str:
    """Phase 1: classify the document type (lightweight, ~100 tokens)."""
    contents = _build_contents(file_bytes, mime_type)
    prompt = _build_prompt(CLASSIFICATION_PROMPT, cuenta_context)
    config = types.GenerateContentConfig(
        system_instruction=prompt,
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
            logger.warning("Gemini classify parse error: %s", type(e).__name__)
            raise PipelineError.from_exception(e) from e
        return result.document_type.value

    return _call_with_fallback(_classify)


def _build_prompt(base_prompt: str, cuenta_context: CuentaContext | None) -> str:
    """Append cuenta identity to the base prompt when available."""
    if not cuenta_context:
        return base_prompt
    parts = []
    if cuenta_context.nombre:
        parts.append(f"Nombre: {cuenta_context.nombre}")
    if cuenta_context.tax_id:
        parts.append(f"NIF/CIF: {cuenta_context.tax_id}")
    if not parts:
        return base_prompt
    suffix = (
        "\n\nDATOS DE LA CUENTA (propietario del documento):\n- "
        + "\n- ".join(parts)
        + "\nCompara estos datos con el emisor y receptor del documento. "
        "Si el NIF/nombre de la cuenta coincide con el EMISOR → invoice_sent. "
        "Si coincide con el RECEPTOR/CLIENTE → invoice_received."
    )
    return base_prompt + suffix


def extract_document(
    file_bytes: bytes,
    mime_type: str,
    document_type: str,
    cuenta_context: CuentaContext | None = None,
) -> dict:
    """Phase 2: extract fields using the type-specific schema and prompt."""
    type_config = DOCUMENT_TYPE_REGISTRY.get(document_type)
    if not type_config or not type_config.extraction_schema:
        raise ValueError(f"No extraction schema registered for type: {document_type}")

    contents = _build_contents(file_bytes, mime_type)
    prompt = _build_prompt(type_config.prompt, cuenta_context)
    config = types.GenerateContentConfig(
        system_instruction=prompt,
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
            logger.warning("Gemini extract parse error: %s", type(e).__name__)
            raise PipelineError.from_exception(e) from e
        return validated.model_dump()

    return _call_with_fallback(_extract)


def _detect_mapping(headers: list[str], sample_rows: list[list[str]]) -> dict:
    """Capa 1: Detecta el mapping de columnas CSV -> campos canónicos.
    
    Usa Pro/Flash para resolver el problema DURO: "¿Qué columna es nombre?"
    
    Args:
        headers: Nombres de columnas del CSV/Excel
        sample_rows: 5-10 filas de ejemplo para contexto
    
    Returns:
        dict: {"columna_original": "campo_canonico"} e.g. {"nombre": "nombre_fiscal"}
    """
    sample_text = chr(10).join([', '.join(row[:10]) for row in sample_rows[:5]])
    
    system_instruction = """Eres un experto mapeando columnas de CSVs/Excels españoles a campos canónicos.
Tu tarea: analizar headers y datos, identificar qué columna es nombre_fiscal, tax_id, phone_number, etc.
Campos canónicos: nombre_fiscal, tax_id, phone_number, email_contacto, direccion_fiscal, codigo_postal."""
    
    prompt = f"""COLUMNAS DETECTADAS: {', '.join(headers)}

PRIMERAS 5 FILAS:
{sample_text}

Mapea cada columna al campo canónico más probable. Retorna SOLO un JSON:
{{"nombre": "nombre_fiscal", "nif": "tax_id", ...}}

Solo JSON, sin explicaciones."""
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.0,
        top_p=0.95,
        response_mime_type="application/json",
    )
    
    def _map(model):
        response = _call_gemini(model, [prompt], config)
        try:
            mapping = json.loads(response.text.strip())
            if not isinstance(mapping, dict):
                raise ValueError("Mapping debe ser un diccionario")
            return mapping
        except json.JSONDecodeError as e:
            logger.warning("Mapping detection parse error on %s: %s", model, e)
            raise PipelineError(
                code="PARSE_ERROR",
                message=f"Failed to parse mapping: {str(e)}"
            ) from e
    
    # Try Pro (fail fast) -> then Flash
    return _call_with_retry_chain(
        _map,
        [
            ("gemini-2.5-pro", 1),           # 1 attempt, fail fast
            ("gemini-2.5-flash", 2),         # 1 retry
        ],
    )


def _normalize_with_mapping(mapping: dict, headers: list[str], rows: list[list[str]]) -> dict:
    """Capa 2: Normaliza filas usando el mapping conocido.
    
    Usa Flash para resolver el problema FÁCIL: "Aplica este mapping"
    
    Args:
        mapping: {"nombre": "nombre_fiscal", ...} del resultado de Capa 1
        headers: Nombres de columnas
        rows: Todas las filas a normalizar
    
    Returns:
        dict: {normalized_rows[], warnings[]}
    """
    num_example_rows = min(len(rows), 5)
    example_rows_text = chr(10).join([', '.join(row[:10]) for row in rows[:num_example_rows]])
    
    # Crear reverse mapping para referencia
    reverse_map = ", ".join([f"{k}→{v}" for k, v in mapping.items()])
    
    system_instruction = """Eres un normalizador de datos contables de España.
Tu tarea: aplicar un mapping conocido y normalizar datos con scores de confianza.
IMPORTANTE: confidence es un diccionario {"nombre_fiscal": 0.95, "tax_id": 0.88, ...}"""
    
    prompt = f"""MAPEO A APLICAR:
{reverse_map}

HEADERS (posición de índice):
{', '.join(f"{i}={h}" for i, h in enumerate(headers))}

EJEMPLO DE FILAS (primeras {num_example_rows}):
{example_rows_text}

TOTAL FILAS: {len(rows)}

Normaliza TODAS las {len(rows)} filas aplicando el mapeo.
Para cada fila:
- Extrae valor de la columna mapeada
- Asigna confidence: 0.95 si valor OK, 0.6 si vacío, 0.3 si malformado
- confidence DEBE SER DICCIONARIO: {{"nombre_fiscal": 0.95, "tax_id": 0.88, ...}}

Retorna JSON:
{{"normalized_rows": [{{"nombre_fiscal": "...", "tax_id": "...", "confidence": {{"nombre_fiscal": 0.95, ...}}}}, ...], "warnings": []}}"""
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.0,
        top_p=0.95,
        response_mime_type="application/json",
    )
    
    def _normalize(model):
        response = _call_gemini(model, [prompt], config)
        try:
            response_text = response.text.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            response_text = response_text.strip()
            
            result = json.loads(response_text)
            if "normalized_rows" not in result:
                raise ValueError("Missing normalized_rows in response")
            
            return result
        except json.JSONDecodeError as e:
            logger.warning("Normalization parse error on %s: %s", model, e)
            raise PipelineError(
                code="PARSE_ERROR",
                message=f"Failed to parse normalization: {str(e)}"
            ) from e
    
    # Flash is sufficient for applying known mapping
    return _call_with_retry_chain(
        _normalize,
        [
            ("gemini-2.5-flash", 1),         # 1 attempt
            ("gemini-2.5-flash-lite", 4),    # 3 retries
        ],
    )


def normalize_import_data(headers: list[str], rows: list[list[str]]) -> dict:
    """Normaliza CSV/Excel import data con arquitectura de 2 capas.
    
    CAPA 1: _detect_mapping() → identifica headers
    - Input: headers + 5 filas ejemplo
    - Output: {"nombre": "nombre_fiscal", "nif": "tax_id", ...}
    - Modelos: Pro (1 intento) → Flash (1 retry)
    
    CAPA 2: _normalize_with_mapping() → aplica mapping en chunks
    - Input: mapping conocido + todas las filas (procesadas en chunks de 200)
    - Output: normalized_rows con confidence como dict
    - Modelos: Flash (1 intento) → Flash-lite (3 retries)
    
    Benefit: 15-20× más barato, determinista, escalable a 1000+ filas.
    
    Args:
        headers: Column names from CSV/Excel
        rows: All rows to normalize
    
    Returns:
        dict: {mapping, normalized_rows[], warnings[]}
    """
    if not rows:
        raise ValueError("No rows provided for import normalization")
    
    if len(rows) > 1000:
        logger.warning("Truncating %d rows to 1000 max for import", len(rows))
        rows = rows[:1000]
    
    logger.info(f"normalize_import_data: {len(rows)} rows, {len(headers)} headers")
    
    # CAPA 1: Detect mapping
    logger.info("CAPA 1: Detecting column mapping...")
    sample_rows = rows[:5] if len(rows) >= 5 else rows
    mapping = _detect_mapping(headers, sample_rows)
    logger.info(f"Mapping detected: {mapping}")
    
    # CAPA 2: Normalize with mapping in chunks
    logger.info("CAPA 2: Normalizing rows with known mapping...")
    chunk_size = 200
    chunks = [rows[i:i + chunk_size] for i in range(0, len(rows), chunk_size)]
    
    all_normalized_rows = []
    all_warnings = set()
    
    for chunk_idx, chunk in enumerate(chunks):
        logger.info(f"Processing chunk {chunk_idx + 1}/{len(chunks)} ({len(chunk)} rows)")
        
        result = _normalize_with_mapping(mapping, headers, chunk)
        
        all_normalized_rows.extend(result.get("normalized_rows", []))
        if "warnings" in result:
            all_warnings.update(result["warnings"])
    
    return {
        "mapping": mapping,
        "normalized_rows": all_normalized_rows,
        "warnings": list(all_warnings),
    }

