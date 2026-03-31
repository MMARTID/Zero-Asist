import hashlib
import uuid
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException
from app.models.document import DocumentoNormalizado, FacturaData, ExtractedData
from app.services.gemini_client import extract_from_pdf, extract_from_file
from app.ingestion.normalizer import normalize_extracted_data 
from app.services.firestore_client import guardar_documento

app = FastAPI()

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

    try:
        # 🔥 Llamamos a Gemini SOLO una vez
        raw_extracted = extract_from_file(contenido, mime_type)

        # Intentamos mapear a ExtractedData
        try:
            extracted_obj = ExtractedData(**raw_extracted, raw=raw_extracted)
        except Exception:
            extracted_obj = ExtractedData(raw=raw_extracted)

        # Normalizamos
        normalized = normalize_extracted_data(raw_extracted)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en extracción: {str(e)}")

    factura_data = FacturaData(**normalized)

    doc_id = str(uuid.uuid4())
    now = datetime.utcnow()

    normalized_dict = factura_data.dict()
    for field in ["issue_date", "due_date"]:
        if normalized_dict.get(field):
            normalized_dict[field] = datetime.combine(normalized_dict[field], datetime.min.time())

    documento = DocumentoNormalizado(
        id=doc_id,
        file_name=file.filename,
        file_size=len(contenido),
        document_hash=doc_hash,
        extracted_data=extracted_obj,
        normalized_data=factura_data,
        created_at=now
    )

    guardar_documento(
        "documentos",
        doc_id,
        {
            **documento.dict(exclude={"normalized_data"}),
            "normalized_data": normalized_dict,
            "extracted_data": extracted_obj.dict(),
        }
    )
    
    return {
        "documento_id": doc_id,
        "normalized_data": factura_data.dict()
    }
