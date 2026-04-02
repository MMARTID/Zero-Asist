import os
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

TOKEN_PATH = "app/collectors/token.json"
CREDENTIALS_PATH = "app/collectors/credentials.json"


def get_gmail_service():
    """
    Devuelve un cliente de la API de Gmail autenticado con OAuth.
    No tiene lógica de negocio: solo autenticación + build().
    """
    creds = None

    # Cargar token si existe
    if os.path.exists(TOKEN_PATH):giit
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # Si no hay credenciales válidas → login / refresh
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH,
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Guardar token
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    # Crear servicio Gmail
    service = build("gmail", "v1", credentials=creds)

    # (Opcional) imprimir la cuenta conectada, pero sin tocar correos
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress")
    print(f"✅ Conectado a Gmail como: {email}")

    return service


if __name__ == "__main__":
    # Pequeño test manual
    service = get_gmail_service()