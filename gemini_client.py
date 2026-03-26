import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def extract_from_pdf(pdf_bytes: bytes) -> dict:
    model = genai.GenerativeModel('gemini-2.5-flash')
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
    response = model.generate_content([
        prompt,
        {"mime_type": "application/pdf", "data": pdf_bytes}
    ])
    text = response.text
    # Extraer JSON (puede venir con markdown)
    start = text.find('{')
    end = text.rfind('}') + 1
    if start != -1 and end > start:
        json_str = text[start:end]
        return json.loads(json_str)
    else:
        raise ValueError("No se pudo extraer JSON de la respuesta")