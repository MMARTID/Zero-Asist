import hashlib
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException
from app.models.document import DocumentoNormalizado, DocumentType, ExtractedData
from app.services.gemini_client import extract_from_file
from app.ingestion.normalizer import normalize_document
from app.services.firestore_client import db, guardar_si_no_existe
from app.collectors.gmail_poller import poll_gmail
from app.collectors.gmail_service import get_gmail_service   # <-- añadir esta línea

app = FastAPI()


@app.post("/procesar-documento")
async def procesar_documento(file: UploadFile = File(...)):
    service = get_gmail_service()
    print(service.users().getProfile(userId='me').execute())
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

    allowed_mimes = [
        "application/pdf",
        "image/jpeg",
        "image/jpg",
        "image/png",
        "application/xml",
        "text/xml"
    ]

    if mime_type not in allowed_mimes:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no soportado: {mime_type}")

    doc_hash = hashlib.sha256(contenido).hexdigest()

    # 🔥 CHECK RÁPIDO (ANTES DE GEMINI)
    doc_ref = db.collection("documentos").document(doc_hash)
    if doc_ref.get().exists:
        raise HTTPException(status_code=409, detail="Documento duplicado")

    try:
        # Llamamos a Gemini SOLO una vez → devuelve { document_type, data }
        raw_extracted = extract_from_file(contenido, mime_type)

        document_type_str = raw_extracted.get("document_type", "other")
        try:
            document_type = DocumentType(document_type_str)
        except ValueError:
            document_type = DocumentType.other

        data = raw_extracted.get("data", {})

        # Intentamos mapear a ExtractedData para compatibilidad
        try:
            extracted_obj = ExtractedData(
                issuer_name=data.get("issuer_name"),
                issuer_tax_id=data.get("issuer_tax_id"),
                invoice_number=data.get("invoice_number"),
                issue_date=data.get("issue_date"),
                total_amount=data.get("total_amount"),
                raw=data
            )
        except Exception:
            extracted_obj = ExtractedData(raw=data)

        # Normalizamos según el tipo de documento
        normalized = normalize_document(data, document_type.value)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en extracción: {str(e)}")

    doc_id = doc_hash
    now = datetime.utcnow()

    # Convertir fechas date → datetime para Firestore
    normalized_dict = dict(normalized)
    for field in ["issue_date", "due_date", "period_start", "period_end"]:
        if normalized_dict.get(field):
            val = normalized_dict[field]
            if hasattr(val, 'year'):
                normalized_dict[field] = datetime.combine(val, datetime.min.time())

    documento = DocumentoNormalizado(
        id=doc_id,
        file_name=file.filename,
        file_size=len(contenido),
        document_hash=doc_hash,
        document_type=document_type,
        extracted_data=extracted_obj,
        normalized_data=normalized_dict,
        created_at=now
    )

    transaction = db.transaction()

    try:
        guardar_si_no_existe(
            transaction,
            "documentos",
            doc_hash,
            {
                **documento.dict(exclude={"normalized_data"}),
                "normalized_data": normalized_dict,
                "extracted_data": extracted_obj.dict(),
                "document_type": document_type.value,
            }
        )
    except ValueError:
        raise HTTPException(status_code=409, detail="Documento duplicado")

    return {
        "documento_id": doc_id,
        "document_type": document_type.value,
        "normalized_data": normalized_dict
    }


@app.post("/poll-gmail")
def poll_gmail_endpoint():
    processed = poll_gmail()
    return {"procesados": len(processed), "documentos": processed}