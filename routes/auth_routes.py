"""Rutas de acceso: personal interno y clientes de la tienda."""
from __future__ import annotations

from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from config import Config
from db import BusinessError
from services import auth_service, ecommerce_service

auth_bp = Blueprint("auth", __name__)


def _safe_next(default: str) -> str:
    target = request.args.get("next") or request.form.get("next")
    if target:
        parsed = urlparse(target)
        if not parsed.scheme and not parsed.netloc and target.startswith("/") and not target.startswith("//"):
            return target
    return default


def _start_session(user: dict) -> None:
    # Conserva el carrito que el visitante armó antes de iniciar sesión.
    carrito_previo = session.get(ecommerce_service.CART_KEY)
    session.clear()
    session.permanent = True
    if carrito_previo:
        session[ecommerce_service.CART_KEY] = carrito_previo
    session["uid"] = user["id"]
    session["nombre"] = f"{user['nombre']} {user.get('apellido', '')}".strip()
    session["correo"] = user["correo"]
    session["rol"] = user["rol"]
    session["cliente_id"] = user.get("cliente_id")
    session["vet_id"] = user.get("veterinario_id")
    # Claves compatibles con el frontend del compañero (templates/JS).
    session["user_id"] = user["id"]
    session["user_nombre"] = user["nombre"]
    session["user_apellido"] = user.get("apellido", "")
    session["user_correo"] = user["correo"]
    session["user_rol"] = user["rol"]
    session["user_tipo"] = "personal" if user["rol"] in Config.STAFF_ROLES else "cliente"


@auth_bp.route("/inicio")
def index():
    if session.get("rol") == Config.ROLE_CLIENT:
        return redirect(url_for("index"))
    if session.get("rol") in Config.STAFF_ROLES:
        return redirect(url_for("dashboard"))
    return redirect(url_for("index"))


@auth_bp.route("/admin/login", methods=["GET", "POST"])
def login():
    if session.get("rol") in Config.STAFF_ROLES:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        try:
            user = auth_service.authenticate(
                request.form.get("correo", ""),
                request.form.get("contrasena", ""),
                expected_role="staff",
            )
            if user["rol"] == Config.ROLE_CLIENT:
                raise BusinessError("Usa el acceso de clientes en la tienda en línea.")
            _start_session(user)
            flash(f"Bienvenido(a), {user['nombre']}.", "success")
            return redirect(_safe_next(url_for("dashboard")))
        except BusinessError as error:
            flash(error.message, "danger")
    return render_template("login.html", tab="login", correo="", datos={}, roles=[])


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Sesión finalizada.", "info")
    return redirect(url_for("login"))


@auth_bp.route("/tienda/login", methods=["GET", "POST"])
def shop_login():
    if session.get("rol") == Config.ROLE_CLIENT:
        return redirect(url_for("mi_cuenta"))
    if request.method == "POST":
        try:
            user = auth_service.authenticate(
                request.form.get("correo", ""),
                request.form.get("contrasena", ""),
                expected_role="client",
            )
            _start_session(user)
            flash(f"¡Hola de nuevo, {user['nombre']}!", "success")
            return redirect(_safe_next(url_for("mi_cuenta")))
        except BusinessError as error:
            flash(error.message, "danger")
    return render_template("shop/login.html")


@auth_bp.route("/tienda/registro", methods=["GET", "POST"])
def shop_register():
    if session.get("rol") == Config.ROLE_CLIENT:
        return redirect(url_for("mi_cuenta"))
    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre", ""),
            "apellido": request.form.get("apellido", ""),
            "cedula": request.form.get("cedula", ""),
            "correo": request.form.get("correo", ""),
            "telefono": request.form.get("telefono", ""),
            "direccion": request.form.get("direccion", ""),
            "contrasena": request.form.get("contrasena", ""),
        }
        try:
            user = ecommerce_service.register_and_login(data)
            _start_session(user)
            flash("Tu cuenta fue creada. ¡Bienvenido a la familia Pepe & Pepito!", "success")
            return redirect(url_for("mi_cuenta"))
        except BusinessError as error:
            flash(error.message, "danger")
    return render_template("shop/register.html")


@auth_bp.route("/tienda/logout")
def shop_logout():
    session.clear()
    flash("Has cerrado sesión.", "info")
    return redirect(url_for("index"))
