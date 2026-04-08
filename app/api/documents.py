import logging
from fastapi import APIRouter, HTTPException, UploadFile, File

from app.services.document_processor import process_document
from app.services.errors import PipelineError

logger = logging.getLogger(__name__)

router = APIRouter()

# Extension → MIME mapping for uploads missing Content-Type
_EXT_MIME = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "xml": "application/xml",
}


@router.post("/procesar-documento")
async def procesar_documento(file: UploadFile = File(...)):
    contenido = await file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    mime_type = file.content_type or ""
    if not mime_type:
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        mime_type = _EXT_MIME.get(ext, "")
        if not mime_type:
            raise HTTPException(status_code=400, detail=f"Extensión no soportada: {ext}")

    try:
        result = process_document(
            file_bytes=contenido,
            mime_type=mime_type,
            filename=file.filename,
            file_size=len(contenido),
        )
    except PipelineError as e:
        if e.code == "INVALID_MIME":
            raise HTTPException(status_code=400, detail=e.message)
        if e.code in ("UNAVAILABLE", "RATE_LIMIT", "TIMEOUT"):
            raise HTTPException(status_code=503, detail=e.message)
        raise HTTPException(status_code=500, detail=e.message)
    except Exception as e:
        logger.exception("Error inesperado en /procesar-documento: %s", e)
        raise HTTPException(status_code=500, detail="Error interno del servidor")

    if result.status == "duplicate":
        raise HTTPException(status_code=409, detail="Documento duplicado")

    return {
        "documento_id": result.doc_hash,
        "document_type": result.document_type,
        "normalized_data": result.normalized_data,
    }
