"""Utilidades compartidas: serialización, fechas y montos."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import jsonify

from db import BusinessError


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return str(value)


def ok(data: Any = None, **extra: Any):
    payload: dict[str, Any] = {"success": True}
    if data is not None:
        payload["data"] = jsonable(data)
    payload.update({k: jsonable(v) for k, v in extra.items()})
    return jsonify(payload)


def fail(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status


def parse_date(value: Any, field: str = "fecha", required: bool = True) -> dt.date | None:
    if value in (None, "", "null"):
        if required:
            raise BusinessError(f"El campo {field} es obligatorio.")
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    raise BusinessError(f"El campo {field} no tiene un formato de fecha válido.")


def parse_datetime(value: Any, field: str = "fecha", required: bool = True) -> dt.datetime | None:
    if value in (None, "", "null"):
        if required:
            raise BusinessError(f"El campo {field} es obligatorio.")
        return None
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time.min)
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise BusinessError(f"El campo {field} no tiene un formato de fecha/hora válido.")


def to_int(value: Any, field: str = "valor", default: int | None = None) -> int:
    if value in (None, "", "null"):
        if default is not None:
            return default
        raise BusinessError(f"El campo {field} es obligatorio.")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise BusinessError(f"El campo {field} debe ser un número entero.")


def to_decimal(value: Any, field: str = "valor", default: Decimal | None = None) -> Decimal:
    if value in (None, "", "null"):
        if default is not None:
            return default
        raise BusinessError(f"El campo {field} es obligatorio.")
    try:
        return Decimal(str(value).replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise BusinessError(f"El campo {field} debe ser un monto válido.")


def money(value: Any) -> str:
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        amount = Decimal("0")
    return f"C$ {amount:,.2f}"


def date_text(value: Any) -> str:
    if not value:
        return "—"
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime("%d/%m/%Y")
    return str(value)


def datetime_text(value: Any) -> str:
    if not value:
        return "—"
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value)
