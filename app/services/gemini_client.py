# gemini_client.py
import os
import json
from dotenv import load_dotenv
from google.genai import Client, types
from app.models.document import FacturaData

load_dotenv()

SYSTEM_INSTRUCTION = (
    "Eres un asistente especializado en extracción de datos de facturas. "
    "Analiza el documento proporcionado y extrae todos los campos disponibles. "
    "Si un campo no está presente en el documento, devuelve null. "
    "Responde únicamente con el JSON estructurado, sin texto adicional."
)

client = Client(api_key=os.getenv("GEMINI_API_KEY"))

generation_config = types.GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTION,
    temperature=0,
    top_p=0.95,
    top_k=1,
    max_output_tokens=2048,
    response_mime_type="application/json",
    response_schema=FacturaData,
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