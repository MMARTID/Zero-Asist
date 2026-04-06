# gemini_client.py
import os
import json
from dotenv import load_dotenv
from google.genai import Client, types
from app.models.document import DocumentoExtraido

load_dotenv()

SYSTEM_INSTRUCTION = (
    "Eres un asistente especializado en extracción y clasificación de documentos financieros y administrativos. "
    "Analiza el documento proporcionado, identifica su tipo y extrae todos los campos disponibles. "
    "El campo 'document_type' debe ser uno de los siguientes valores: "
    "invoice_received, invoice_issued, receipt, bank_statement, payroll, "
    "social_security_form, delivery_note, contract, tax_authority_communication, other. "
    "El campo 'data' debe contener los campos extraídos del documento según su tipo. "
    "Si un campo no está presente en el documento, devuelve null. "
    "Para facturas (invoice_received / invoice_issued), extrae también los siguientes campos fiscales españoles: "
    "'is_national' (boolean): true si la operación es nacional (proveedor y receptor en España), false si es extranjera. "
    "'inversion_sujeto_pasivo' (boolean): true si aplica inversión del sujeto pasivo (el receptor es quien liquida el IVA). "
    "'pasivo_intracomunitario' (boolean): true si es una adquisición intracomunitaria de bienes o servicios (proveedor en otro estado miembro de la UE). "
    "'importacion_exento' (boolean): true si la factura corresponde a una importación exenta de IVA. "
    "'recargo_equivalencia' (número): importe total del recargo de equivalencia si aparece en la factura, null en caso contrario. "
    "'bienes_inversion' (boolean): true si la factura incluye bienes de inversión (activos fijos sujetos a prorrata especial de IVA). "
    "Responde únicamente con el JSON estructurado, sin texto adicional."
)

client = Client(api_key=os.getenv("GEMINI_API_KEY"))

generation_config = types.GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTION,
    temperature=0,
    top_p=0.95,
    top_k=1,
    max_output_tokens=4096,
    response_mime_type="application/json",
    response_schema=DocumentoExtraido,
)


def extract_from_file(file_bytes: bytes, mime_type: str) -> dict:
    if mime_type.startswith("image/") or mime_type == "application/pdf":
        contents = [
            types.Part.from_bytes(
                data=file_bytes,
                mime_type=mime_type
            )
        ]

    elif mime_type in ("application/xml", "text/xml") or file_bytes.startswith(b"<?xml"):
        try:
            xml_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            xml_text = file_bytes.decode("latin-1")

        contents = [xml_text]

    else:
        raise ValueError(f"Tipo MIME no soportado: {mime_type}")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=generation_config,
    )

    return json.loads(response.text)


def extract_from_pdf(pdf_bytes: bytes) -> dict:
    return extract_from_file(pdf_bytes, "application/pdf")