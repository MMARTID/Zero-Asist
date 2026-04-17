import json
import logging
import os
from typing import Optional

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.discovery import Resource
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from app.services.tenant import TenantContext

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

TOKEN_PATH = os.environ.get("GMAIL_TOKEN_PATH", "app/collectors/token.json")
CREDENTIALS_PATH = os.environ.get("GMAIL_CREDENTIALS_PATH", "app/collectors/credentials.json")

# Variable de entorno con el contenido JSON del token (para Cloud Run / producción).
# En desarrollo local se usa el archivo TOKEN_PATH como fallback.
_ENV_TOKEN_VAR = "GMAIL_TOKEN_JSON"


def _load_or_refresh_creds() -> Credentials:
    token_from_env = os.environ.get(_ENV_TOKEN_VAR)

    if token_from_env:
        # Cloud Run: cargar desde variable de entorno (Secret Manager)
        creds = Credentials.from_authorized_user_info(
            json.loads(token_from_env), SCOPES
        )
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        # No se escribe de vuelta: el refresh_token es de larga duración y
        # el access_token se renueva en memoria en cada arranque del contenedor.
        return creds

    # Desarrollo local: flujo basado en archivo
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
        os.chmod(TOKEN_PATH, 0o600)

    return creds


def _load_tenant_creds(ctx: TenantContext) -> Credentials:
    """Load and refresh credentials for a tenant from the credential store."""
    from app.services.credential_store import load_credentials, save_credentials

    creds = load_credentials(ctx)
    if creds is None:
        raise RuntimeError(
            f"No Gmail credentials for tenant "
            f"{ctx.gestoria_id}/{ctx.cliente_id}"
        )
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_credentials(ctx, creds)
        else:
            raise RuntimeError(
                f"Gmail credentials expired and cannot be refreshed for tenant "
                f"{ctx.gestoria_id}/{ctx.cliente_id}"
            )
    return creds


def get_gmail_service(ctx: Optional[TenantContext] = None) -> Resource:
    """Build a Gmail ``Resource``.

    When *ctx* is provided, credentials are loaded from the credential store
    for that tenant.  Otherwise the legacy single-account flow is used.
    """
    if ctx is not None:
        creds = _load_tenant_creds(ctx)
    else:
        creds = _load_or_refresh_creds()
    return build("gmail", "v1", credentials=creds)
