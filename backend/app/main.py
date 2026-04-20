from dotenv import load_dotenv
load_dotenv()

import logging
import os

# Logging a nivel INFO para que Cloud Run muestre todo el pipeline.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.documents import router as documents_router
from app.api.gmail import router as gmail_router
from app.api.webhook import router as webhook_router
from app.api.internal import router as internal_router
from app.api.onboarding import router as onboarding_router
from app.api.dashboard import router as dashboard_router

app = FastAPI()

_frontend_url = os.environ.get("FRONTEND_URL", "")
_allowed_origins = ["http://localhost:3000", "http://localhost:3001", "http://localhost:3002"]
if _frontend_url:
    _allowed_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions.

    Starlette's ServerErrorMiddleware returns a bare 500 that bypasses
    CORSMiddleware, so the browser never sees the CORS headers.  By
    registering an explicit handler here the response is routed through
    the normal middleware stack (including CORS).
    """
    import logging
    logging.getLogger(__name__).exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

app.include_router(documents_router)
app.include_router(gmail_router)
app.include_router(webhook_router)
app.include_router(internal_router)
app.include_router(onboarding_router)
app.include_router(dashboard_router)


@app.get("/")
def health_check():
    return {"status": "ok"}