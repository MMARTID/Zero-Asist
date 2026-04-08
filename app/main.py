from fastapi import FastAPI

from app.api.documents import router as documents_router
from app.api.gmail import router as gmail_router

app = FastAPI()

app.include_router(documents_router)
app.include_router(gmail_router)