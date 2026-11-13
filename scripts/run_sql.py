"""Ejecuta un script .sql de SQL Server separando lotes por GO.

Uso:
    venv\\Scripts\\python.exe scripts\\run_sql.py sql\\001_ecommerce_y_ajustes.sql
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def connection_string() -> str:
    server = os.getenv("DB_SERVER", r"MSI\SQLEXPRESS")
    database = os.getenv("DB_NAME", "VetPepePepito")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    if os.getenv("DB_USER"):
        return (
            f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            f"UID={os.getenv('DB_USER')};PWD={os.getenv('DB_PASSWORD', '')};"
        )
    return (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        "Trusted_Connection=yes;"
    )


def split_batches(script: str) -> list[str]:
    return [b.strip() for b in re.split(r"^\s*GO\s*$", script, flags=re.MULTILINE) if b.strip()]


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Indica la ruta del archivo .sql")
    path = Path(sys.argv[1])
    if not path.is_absolute():
        path = ROOT / path
    script = path.read_text(encoding="utf-8-sig")
    with pyodbc.connect(connection_string(), autocommit=True, timeout=15) as conn:
        cur = conn.cursor()
        for batch in split_batches(script):
            cur.execute(batch)
            while cur.nextset():
                pass
    print(f"OK -> {path}")


if __name__ == "__main__":
    main()
