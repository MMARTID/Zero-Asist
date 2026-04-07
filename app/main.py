import logging
import os
from fastapi import Header, Depends, FastAPI, HTTPException, UploadFile, File
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from app.services.document_processor import process_document
from app.collectors.gmail_poller import poll_gmail

logger = logging.getLogger(__name__)

app = FastAPI()

_DEV_TOKEN = os.environ.get("SCHEDULER_DEV_TOKEN")
_OIDC_AUDIENCE = os.environ.get("SCHEDULER_AUDIENCE")


def verify_scheduler_token(
    x_scheduler_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    """Dependencia FastAPI que autentica llamadas desde Cloud Scheduler.

    Flujo:
    1. Si X-Scheduler-Token coincide con SCHEDULER_DEV_TOKEN → permitido (dev local).
    2. Si Authorization: Bearer <token> → valida OIDC con google-auth (producción).
    3. Cualquier otro caso → 401.
    """
    if x_scheduler_token is not None:
        if _DEV_TOKEN and x_scheduler_token == _DEV_TOKEN:
            return
        raise HTTPException(status_code=401, detail="X-Scheduler-Token inválido")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not _OIDC_AUDIENCE:
        logger.error("SCHEDULER_AUDIENCE no configurado; rechazando token OIDC")
        raise HTTPException(status_code=401, detail="Servicio no configurado para OIDC")

    token = authorization.removeprefix("Bearer ").strip()
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

    # Detección de MIME por extensión si Content-Type está ausente (específico de HTTP)
    mime_type = file.content_type or ""
    if not mime_type:
        ext = file.filename.split('.')[-1].lower()
        mime_type = {
            "pdf": "application/pdf",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "xml": "application/xml",
        }.get(ext, "")
        if not mime_type:
            raise HTTPException(status_code=400, detail=f"Extensión no soportada: {ext}")

    try:
        result = process_document(
            file_bytes=contenido,
            mime_type=mime_type,
            filename=file.filename,
            file_size=len(contenido),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en extracción: {str(e)}")

    if result.status == "duplicate":
        raise HTTPException(status_code=409, detail="Documento duplicado")

    return {
        "documento_id": result.doc_hash,
        "document_type": result.document_type,
        "normalized_data": result.normalized_data,
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