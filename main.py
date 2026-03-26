import hashlib
import uuid
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException
from models import DocumentoNormalizado, FacturaData
from gemini_client import extract_from_pdf
from firestore_client import guardar_documento

app = FastAPI()

@app.post("/procesar-pdf")
async def procesar_pdf(file: UploadFile = File(...)):
    # Leer archivo
    contenido = await file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="Archivo vacío")

    # Calcular hash
    doc_hash = hashlib.sha256(contenido).hexdigest()

    try:
        # Extraer con Gemini
        extracted = extract_from_pdf(contenido)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en extracción: {str(e)}")

    # Construir objeto FacturaData (validación Pydantic)
    factura_data = FacturaData(**extracted)

    # Generar ID y metadata
    doc_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    documento = DocumentoNormalizado(
        id=doc_id,
        file_name=file.filename,
        file_size=len(contenido),
        document_hash=doc_hash,
        extracted_data=factura_data,
        created_at=now
    )

    # Guardar en Firestore
    guardar_documento("documentos", doc_id, documento.dict())

    return {"documento_id": doc_id, "datos_extraidos": factura_data.dict()}