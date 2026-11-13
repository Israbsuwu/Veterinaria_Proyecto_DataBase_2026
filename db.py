"""Capa de acceso a datos (pyodbc + SQL Server).

Todas las consultas usan parámetros `?` para evitar inyección SQL.
Las operaciones de escritura deben ejecutarse dentro de `transaction()`.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Sequence

import pyodbc
from flask import current_app, g

from config import connection_string


class BusinessError(Exception):
    """Error de regla de negocio, se muestra al usuario tal cual."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def get_db() -> pyodbc.Connection:
    if "db" not in g:
        g.db = pyodbc.connect(connection_string(), autocommit=False, timeout=15)
    return g.db


def close_db(_exception: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


def init_app(app) -> None:
    app.teardown_appcontext(close_db)


def _rows(cursor: pyodbc.Cursor) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description or []]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_all(sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    cursor = get_db().cursor()
    try:
        cursor.execute(sql, params or ())
        return _rows(cursor)
    finally:
        cursor.close()


def fetch_one(sql: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
    cursor = get_db().cursor()
    try:
        cursor.execute(sql, params or ())
        rows = _rows(cursor)
        return rows[0] if rows else None
    finally:
        cursor.close()


def fetch_scalar(sql: str, params: Sequence[Any] | None = None, default: Any = None) -> Any:
    cursor = get_db().cursor()
    try:
        cursor.execute(sql, params or ())
        row = cursor.fetchone()
        return row[0] if row else default
    finally:
        cursor.close()


def execute(sql: str, params: Sequence[Any] | None = None) -> int:
    """Ejecuta una escritura y confirma la transacción."""
    with transaction() as cursor:
        cursor.execute(sql, params or ())
        return cursor.rowcount


@contextmanager
def transaction():
    conn = get_db()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def insert_returning(cursor: pyodbc.Cursor, sql: str, params: Sequence[Any] | None = None) -> int:
    """Ejecuta INSERT ... OUTPUT INSERTED.Id y devuelve el id generado."""
    cursor.execute(sql, params or ())
    row = cursor.fetchone()
    if row is None:
        raise BusinessError("No se pudo obtener el identificador generado.")
    return int(row[0])


def log_sql_error(app, error: Exception) -> None:
    app.logger.exception("Error de base de datos: %s", error)
