from fastapi import APIRouter

from app.collectors.gmail_poller import poll_gmail

router = APIRouter()


@router.post("/poll-gmail")
def poll_gmail_endpoint():
    summary = poll_gmail()
    return {
        "procesados": len(summary["procesados"]),
        "duplicados": len(summary["duplicados"]),
        "errores": len(summary["errores"]),
        "descartados": len(summary["descartados"]),
        "documentos": summary["procesados"],
        "detalle_duplicados": summary["duplicados"],
        "detalle_errores": summary["errores"],
    }
