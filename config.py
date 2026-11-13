"""Configuración central del sistema VetPepePepito."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "vetpepepito-dev-secret-change-me")

    DB_SERVER = os.getenv("DB_SERVER", r"MSI\SQLEXPRESS")
    DB_NAME = os.getenv("DB_NAME", "VetPepePepito")
    DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_TRUSTED = os.getenv("DB_TRUSTED", "yes")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12  # 12 horas

    CURRENCY = os.getenv("CURRENCY", "C$")
    CLINIC_NAME = "Veterinaria Pepe & Pepito"
    CLINIC_PHONE = os.getenv("CLINIC_PHONE", "8888-8888")
    CLINIC_ADDRESS = os.getenv("CLINIC_ADDRESS", "Managua, Nicaragua")

    # Roles del sistema
    ROLE_ADMIN = "Administrador"
    ROLE_VET = "Veterinario"
    ROLE_CASHIER = "Cajero"
    ROLE_CLIENT = "Cliente Web"
    STAFF_ROLES = (ROLE_ADMIN, ROLE_VET, ROLE_CASHIER)


def connection_string() -> str:
    """Construye la cadena ODBC usando autenticación de Windows o SQL."""
    driver = Config.DB_DRIVER
    base = f"DRIVER={{{driver}}};SERVER={Config.DB_SERVER};DATABASE={Config.DB_NAME};"
    if Config.DB_USER:
        return base + f"UID={Config.DB_USER};PWD={Config.DB_PASSWORD};TrustServerCertificate=yes;"
    trusted = "yes" if Config.DB_TRUSTED.lower() in ("yes", "true", "1") else "no"
    return base + f"Trusted_Connection={trusted};TrustServerCertificate=yes;"
