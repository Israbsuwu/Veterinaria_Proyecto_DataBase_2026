"""VetPepePepito - ERP clínico + tienda en línea.

Aplicación Flask única que comparte la base de datos SQL Server y la API.
"""
from __future__ import annotations

from flask import Flask, flash, redirect, render_template, request, url_for

from config import Config
from db import BusinessError, init_app as init_db
from routes.admin_routes import admin_bp
from routes.api_routes import api_bp
from routes.auth_routes import auth_bp
from routes.shop_routes import shop_bp
from security import current_user
from services import ecommerce_service
from utils import date_text, datetime_text, fail, money


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    init_db(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(shop_bp)

    @app.context_processor
    def inject_globals():
        return {
            "current_user": current_user(),
            "cart_count": ecommerce_service.cart_count(),
            "clinic_name": Config.CLINIC_NAME,
            "clinic_phone": Config.CLINIC_PHONE,
            "clinic_address": Config.CLINIC_ADDRESS,
            "currency": Config.CURRENCY,
            "staff_roles": Config.STAFF_ROLES,
            "role_admin": Config.ROLE_ADMIN,
            "role_vet": Config.ROLE_VET,
            "role_cashier": Config.ROLE_CASHIER,
            "role_client": Config.ROLE_CLIENT,
        }

    app.add_template_filter(money, "money")
    app.add_template_filter(date_text, "fecha")
    app.add_template_filter(datetime_text, "fecha_hora")

    @app.template_filter("badge")
    def badge(estado: str | None) -> str:
        mapping = {
            "Activo": "success",
            "Pagada": "success",
            "Disponible": "success",
            "Completada": "success",
            "Confirmada": "success",
            "Vigente": "success",
            "Abierta": "success",
            "Enviada": "success",
            "Pendiente": "warning",
            "En Espera": "warning",
            "Por Vencer": "warning",
            "Baja": "info",
            "Media": "warning",
            "Alta": "danger",
            "En Consulta": "info",
            "Cancelada": "danger",
            "Anulada": "danger",
            "Vencido": "danger",
            "Agotado": "danger",
            "Inactivo": "danger",
            "Fallida": "danger",
            "Cerrada": "info",
            "Archivado": "info",
            "Web": "info",
            "POS": "info",
            "Cuarentena": "warning",
        }
        return mapping.get(estado or "", "info")

    @app.errorhandler(BusinessError)
    def handle_business_error(error: BusinessError):
        if request.path.startswith("/api/") or request.is_json:
            return fail(error.message, error.status)
        flash(error.message, "danger")
        return redirect(request.referrer or url_for("auth.index"))

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("error.html", code=403, mensaje="No tienes permisos para acceder a esta sección."), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("error.html", code=404, mensaje="La página o el registro que buscas no existe."), 404

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
