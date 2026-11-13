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
from routes.colleague_routes import register as register_colleague_routes
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

    # Filtros/plantillas heredados del frontend del compañero.
    def _moneda(valor):
        if valor is None or valor == '':
            return '—'
        try:
            return f"C$ {float(valor):,.2f}"
        except (TypeError, ValueError):
            return '—'

    def _numero(valor):
        try:
            return f"{int(valor):,}"
        except (TypeError, ValueError):
            return '0'

    def _fecha(valor, formato='%d/%m/%Y'):
        if not valor:
            return '—'
        try:
            return valor.strftime(formato)
        except AttributeError:
            return str(valor)

    def _fechahora(valor):
        return _fecha(valor, '%d/%m/%Y %I:%M %p')

    def _hora(valor):
        return _fecha(valor, '%I:%M %p')

    app.add_template_filter(_moneda, "moneda")
    app.add_template_filter(_numero, "numero")
    app.add_template_filter(_fecha, "fecha")
    app.add_template_filter(_fechahora, "fechahora")
    app.add_template_filter(_hora, "hora")

    import os as _os

    _carpeta_productos = _os.path.join(app.static_folder, 'img', 'productos')

    def _arte_categoria(nombre):
        mapping = {
            'alimento seco y humedo para perros': 'alimento-perros.svg',
            'alimento y arena para gatos': 'alimento-gatos.svg',
            'antiparasitarios': 'antiparasitarios.svg',
            'higiene y cuidado': 'higiene.svg',
            'accesorios para perros': 'accesorios-perros.svg',
            'accesorios para gatos': 'accesorios-gatos.svg',
            'farmacia y primeros auxilios': 'farmacia.svg',
            'vacunas y pruebas preventivas': 'vacunas.svg',
            'suplementos nutricionales': 'suplementos.svg',
            'insumos clinicos': 'insumos.svg',
        }
        texto = str(nombre or '').strip().lower()
        archivo = mapping.get(texto, 'producto.svg')
        return url_for('static', filename=f'img/categorias/{archivo}')

    def _imagen_producto(id_producto):
        try:
            pid = int(id_producto)
        except (TypeError, ValueError):
            return None
        for extension in ('jpg', 'jpeg', 'png', 'webp'):
            nombre = f'producto_{pid}.{extension}'
            if _os.path.isfile(_os.path.join(_carpeta_productos, nombre)):
                return url_for('static', filename=f'img/productos/{nombre}')
        return None

    app.add_template_global(_arte_categoria, "arte_categoria")
    app.add_template_global(_imagen_producto, "imagen_producto")

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
        return redirect(request.referrer or url_for("index"))

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("error.html", code=403, mensaje="No tienes permisos para acceder a esta sección."), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("error.html", code=404, mensaje="La página o el registro que buscas no existe."), 404

    register_colleague_routes(app)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
