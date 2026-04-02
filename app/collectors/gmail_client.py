import os
import base64
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def connect_gmail():
    creds = None

    # Cargar token si existe
    if os.path.exists("app/collectors/token.json"):
        creds = Credentials.from_authorized_user_file(
            "app/collectors/token.json", SCOPES
        )

    # Si no hay credenciales válidas → login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "app/collectors/credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Guardar token
        with open("app/collectors/token.json", "w") as token:
            token.write(creds.to_json())

    # Crear servicio Gmail
    service = build("gmail", "v1", credentials=creds)

    # Obtener perfil
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress")

    print(f"✅ Conectado en la cuenta: {email}")

    # Obtener el último correo
    messages = service.users().messages().list(
        userId="me",
        maxResults=1,
        labelIds=["INBOX"]
    ).execute()

    if "messages" not in messages:
        print("no hay correos en la bandeja de entrada")
        return service

    last_message_id = messages["messages"][0]["id"]

    message = service.users().messages().get(
        userId="me",
        id=last_message_id,
        format="full"
    ).execute()

    headers = message.get("payload", {}).get("headers", [])

    subject = None
    for header in headers:
        if header["name"] == "Subject":
            subject = header["value"]
            break

    print(f"📨 Último asunto: {subject}")

    return service


if __name__ == "__main__":
    connect_gmail()