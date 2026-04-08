from fastapi import APIRouter

from app.collectors.gmail_poller import poll_gmail

router = APIRouter()


@router.post("/poll-gmail")
def poll_gmail_endpoint():
    summary = poll_gmail()

    has_errors = len(summary["errores"]) > 0
    has_processed = len(summary["procesados"]) > 0

    if has_processed:
        status = "partial_success" if has_errors else "success"
    elif has_errors:
        status = "error"
    else:
        status = "empty"

    return {
        "status": status,
        "procesados": len(summary["procesados"]),
        "duplicados": len(summary["duplicados"]),
        "errores": len(summary["errores"]),
        "descartados": len(summary["descartados"]),
        "documentos": summary["procesados"],
        "detalle_duplicados": summary["duplicados"],
        "detalle_errores": summary["errores"],
    }