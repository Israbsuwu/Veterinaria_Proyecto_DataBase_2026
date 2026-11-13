"""Autenticación, sesión y control de acceso por roles."""
from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import flash, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(stored: str | None, provided: str) -> bool:
    """Soporta hashes de Werkzeug y contraseñas planas heredadas del prototipo."""
    if not stored:
        return False
    if stored.startswith(("pbkdf2:", "scrypt:", "argon2")):
        try:
            return check_password_hash(stored, provided)
        except ValueError:
            return False
    return stored == provided


def is_hashed(value: str | None) -> bool:
    return bool(value and value.startswith(("pbkdf2:", "scrypt:", "argon2")))


def current_user() -> dict:
    return {
        "id": session.get("uid"),
        "nombre": session.get("nombre", ""),
        "rol": session.get("rol", ""),
        "cliente_id": session.get("cliente_id"),
        "correo": session.get("correo", ""),
    }


def is_staff() -> bool:
    return session.get("rol") in Config.STAFF_ROLES


def _wants_json() -> bool:
    return (
        request.path.startswith("/api/")
        or request.is_json
        or request.accept_mimetypes.best == "application/json"
    )


def _next_path() -> str:
    """Ruta actual sin el '?' final que agrega Flask cuando no hay query string."""
    return request.full_path.rstrip("?")


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("uid"):
            if _wants_json():
                return jsonify({"success": False, "error": "Debes iniciar sesión."}), 401
            flash("Debes iniciar sesión para continuar.", "warning")
            return redirect(url_for("auth.login", next=_next_path()))
        return view(*args, **kwargs)

    return wrapper


def staff_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("uid"):
            if _wants_json():
                return jsonify({"success": False, "error": "Debes iniciar sesión."}), 401
            return redirect(url_for("auth.login", next=_next_path()))
        if not is_staff():
            if _wants_json():
                return jsonify({"success": False, "error": "No tienes permisos internos."}), 403
            flash("Esa sección es exclusiva del personal de la clínica.", "danger")
            return redirect(url_for("shop.home"))
        return view(*args, **kwargs)

    return wrapper


def role_required(*roles: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not session.get("uid"):
                if _wants_json():
                    return jsonify({"success": False, "error": "Debes iniciar sesión."}), 401
                return redirect(url_for("auth.login", next=_next_path()))
            if session.get("rol") not in roles:
                if _wants_json():
                    return jsonify({"success": False, "error": "No tienes permisos para esta acción."}), 403
                flash("No tienes permisos para acceder a esa sección.", "danger")
                return redirect(url_for("admin.dashboard"))
            return view(*args, **kwargs)

        return wrapper

    return decorator


def client_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("uid") or session.get("rol") != Config.ROLE_CLIENT:
            if _wants_json():
                return jsonify({"success": False, "error": "Inicia sesión como cliente para continuar."}), 401
            flash("Inicia sesión para comprar y gestionar tus mascotas.", "warning")
            return redirect(url_for("auth.shop_login", next=_next_path()))
        if not session.get("cliente_id"):
            if _wants_json():
                return jsonify({"success": False, "error": "Tu usuario no tiene ficha de cliente vinculada."}), 403
            flash("Tu usuario no tiene una ficha de cliente vinculada. Contacta a la clínica.", "danger")
            return redirect(url_for("shop.home"))
        return view(*args, **kwargs)

    return wrapper
