# gemini_client.py
import json
import os
from dotenv import load_dotenv
from google.genai import Client, types

load_dotenv()

client = Client(api_key=os.getenv("GEMINI_API_KEY"))

def extract_from_file(file_bytes: bytes, mime_type: str) -> dict:
    prompt = """
    Extrae los datos de esta factura y devuelve SOLO un JSON con el siguiente formato:
    {
        "issuer_name": "nombre",
        "issuer_tax_id": "NIF",
        "invoice_number": "número",
        "series": "serie o null",
        "issue_date": "YYYY-MM-DD",
        "due_date": "YYYY-MM-DD o null",
        "base_amount": número,
        "tax_amount": número,
        "total_amount": número,
        "currency": "EUR",
        "payment_method": "string o null",
        "tax_breakdown": [{"rate": número, "base": número, "amount": número}],
        "line_items": [{"description": "texto", "quantity": número, "unit_price": número, "base": número, "tax_rate": número, "tax_amount": número, "total": número}]
    }
    Si algún campo no está disponible, pon null.
    """

    if mime_type.startswith("image/") or mime_type == "application/pdf":
        contents = [
            prompt,
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

        contents = [
            prompt,
            xml_text
        ]

    else:
        raise ValueError(f"Tipo MIME no soportado: {mime_type}")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config={
            "temperature": 0,
            "response_mime_type": "application/json"
        }
    )

    return json.loads(response.text)


def extract_from_pdf(pdf_bytes: bytes) -> dict:
    return extract_from_file(pdf_bytes, "application/pdf")