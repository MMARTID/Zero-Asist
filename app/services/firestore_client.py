from google.cloud import firestore
import os

# Inicializar cliente de Firestore (usa las credenciales por defecto en Cloud Run)
db = firestore.Client()

def guardar_documento(coleccion: str, doc_id: str, data: dict):
    doc_ref = db.collection(coleccion).document(doc_id)
    doc_ref.set(data)
    return doc_id