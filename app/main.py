import logging
import os
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from app.models.document import DocumentType, ExtractedData
from app.services.document_processor import (
    compute_hash,
    extract_and_normalize,
    is_document_duplicate,
    save_document,
)
from app.collectors.gmail_poller import poll_gmail
from app.collectors.gmail_reader import ALLOWED_MIME_TYPES

logger = logging.getLogger(__name__)

app = FastAPI()

_DEV_TOKEN = os.environ.get("SCHEDULER_DEV_TOKEN")
_OIDC_AUDIENCE = os.environ.get("SCHEDULER_AUDIENCE")


def verify_scheduler_token(request: Request) -> None:
    """Dependencia FastAPI que autentica llamadas desde Cloud Scheduler.

    Flujo:
    1. Si X-Scheduler-Token coincide con SCHEDULER_DEV_TOKEN → permitido (dev local).
    2. Si Authorization: Bearer <token> → valida OIDC con google-auth (producción).
    3. Cualquier otro caso → 401.
    """
    # --- Alternativa de desarrollo local ---
    dev_token_header = request.headers.get("X-Scheduler-Token")
    if dev_token_header:
        if _DEV_TOKEN and dev_token_header == _DEV_TOKEN:
            return
        # Header presente pero token incorrecto o SCHEDULER_DEV_TOKEN no configurado
        raise HTTPException(status_code=401, detail="X-Scheduler-Token inválido")

    # --- OIDC (Cloud Scheduler en producción) ---
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not _OIDC_AUDIENCE:
        logger.error("SCHEDULER_AUDIENCE no configurado; rechazando token OIDC")
        raise HTTPException(status_code=401, detail="Servicio no configurado para OIDC")

    token = auth_header.removeprefix("Bearer ").strip()
    try:
        id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=_OIDC_AUDIENCE,
        )
    except Exception as exc:
        logger.warning("Token OIDC inválido: %s", exc)
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


@app.post("/procesar-documento")
async def procesar_documento(file: UploadFile = File(...)):
    contenido = await file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    mime_type = file.content_type or ""
    if not mime_type:
        ext = file.filename.split('.')[-1].lower()
        mime_type = {
            "pdf": "application/pdf",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "xml": "application/xml"
        }.get(ext, None)

        if not mime_type:
            raise HTTPException(status_code=400, detail=f"Extensión no soportada: {ext}")

    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no soportado: {mime_type}")

    doc_hash = compute_hash(contenido)

    # 🔥 CHECK RÁPIDO (ANTES DE GEMINI)
    if is_document_duplicate(doc_hash):
        raise HTTPException(status_code=409, detail="Documento duplicado")

    try:
        document_type_str, normalized_dict, extracted_data = extract_and_normalize(contenido, mime_type)

        try:
            document_type = DocumentType(document_type_str)
        except ValueError:
            document_type = DocumentType.other

        # Intentamos mapear a ExtractedData para compatibilidad
        try:
            extracted_obj = ExtractedData(
                issuer_name=extracted_data.get("issuer_name"),
                issuer_tax_id=extracted_data.get("issuer_tax_id"),
                invoice_number=extracted_data.get("invoice_number"),
                issue_date=extracted_data.get("issue_date"),
                total_amount=extracted_data.get("total_amount"),
                raw=extracted_data
            )
        except Exception:
            extracted_obj = ExtractedData(raw=extracted_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en extracción: {str(e)}")

    try:
        save_document(
            doc_hash=doc_hash,
            filename=file.filename,
            file_size=len(contenido),
            document_type_str=document_type.value,
            normalized_dict=normalized_dict,
            extracted_data=extracted_obj.model_dump(),
        )
    except ValueError:
        raise HTTPException(status_code=409, detail="Documento duplicado")

    return {
        "documento_id": doc_hash,
        "document_type": document_type.value,
        "normalized_data": normalized_dict
    }


@app.post("/poll-gmail")
def poll_gmail_endpoint(_: None = Depends(verify_scheduler_token)):
    summary = poll_gmail()
    return {
        "procesados": len(summary["procesados"]),
        "duplicados": len(summary["duplicados"]),
        "errores": len(summary["errores"]),
        "descartados": len(summary["descartados"]),
        "documentos": summary["procesados"],
        "detalle_duplicados": summary["duplicados"],
        "detalle_errores": summary["errores"],
    }