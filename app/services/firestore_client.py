from google.cloud import firestore
import os

# Inicializar cliente de Firestore (usa las credenciales por defecto en Cloud Run)
db = firestore.Client()

@firestore.transactional
def guardar_si_no_existe(transaction, coleccion: str, doc_hash: str, data: dict):
    ref = db.collection(coleccion).document(doc_hash)
    snapshot = ref.get(transaction=transaction)
    if snapshot.exists:
        raise ValueError("Documento duplicado")
    transaction.set(ref, data)
    
def guardar_documento(coleccion: str, doc_id: str, data: dict):
    doc_ref = db.collection(coleccion).document(doc_id)
    doc_ref.set(data)
    return doc_id