from datetime import date, datetime
from typing import Any, Dict

from app.ingestion.constants import DATE_FIELDS


def _date_to_datetime(value: Any) -> Any:
    """Convert a date or datetime to a midnight datetime for Firestore."""
    if isinstance(value, datetime):
        return datetime.combine(value.date(), datetime.min.time())
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return value


def dates_to_firestore(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert date fields to datetime for Firestore compatibility.

    Handles both top-level fields in ``DATE_FIELDS`` and nested
    ``transactions[].date`` fields found in bank statements.
    """
    result = dict(data)
    for field_name in DATE_FIELDS:
        if field_name in result:
            result[field_name] = _date_to_datetime(result[field_name])

    if "movements" in result and isinstance(result["movements"], list):
        converted = []
        for mov in result["movements"]:
            if isinstance(mov, dict) and "date" in mov:
                mov = dict(mov)
                mov["date"] = _date_to_datetime(mov["date"])
            converted.append(mov)
        result["movements"] = converted

    return result
