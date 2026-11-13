"""Panel administrativo interno (ERP clínico)."""
from __future__ import annotations

import datetime as dt

from flask import Blueprint, abort, render_template, request, session

from config import Config
from db import BusinessError
from security import role_required, staff_required
from services import (
    auth_service,
    billing_service,
    catalog_service,
    clinical_service,
    dashboard_service,
    inventory_service,
)
from utils import jsonable, parse_date

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@staff_required
def dashboard():
    datos = dashboard_service.get_dashboard(session["uid"])
    return render_template("admin/dashboard.html", datos=datos, active="dashboard")


@admin_bp.route("/agenda")
@staff_required
def agenda():
    fecha = parse_date(request.args.get("fecha") or dt.date.today(), "fecha", required=False)
    estado = request.args.get("estado") or None
    if estado not in (None, "Pendiente", "Confirmada", "Cancelada", "Completada"):
        estado = None
    return render_template(
        "admin/agenda.html",
        active="agenda",
        fecha=fecha,
        estado=estado,
        reservas=clinical_service.list_reservations(fecha=fecha, estado=estado),
        clientes=clinical_service.list_clients(),
        mascotas=clinical_service.list_pets(),
        vets=clinical_service.list_vets(),
    )


@admin_bp.route("/triaje")
@staff_required
def triaje():
    estado = request.args.get("estado") or None
    if estado not in (None, "En Espera", "En Consulta", "Finalizada"):
        estado = None
    return render_template(
        "admin/triaje.html",
        active="triaje",
        estado=estado,
        atenciones=clinical_service.list_attentions(estado=estado),
        vets=clinical_service.list_vets(),
        mascotas=clinical_service.list_pets(),
        reservas=clinical_service.list_reservations(
            fecha=dt.date.today(), estado="Confirmada"
        ),
        productos=jsonable(catalog_service.list_products()),
        lotes=jsonable(inventory_service.list_lots(include_empty=False)),
        clientes=clinical_service.list_clients(),
    )


@admin_bp.route("/expedientes")
@staff_required
def expedientes():
    search = (request.args.get("q") or "").strip()
    return render_template(
        "admin/expedientes.html",
        active="expedientes",
        mascotas=clinical_service.list_pets(search=search or None),
        clientes=clinical_service.list_clients(search=search or None),
        search=search,
    )


@admin_bp.route("/expedientes/<int:mascota_id>")
@staff_required
def expediente_detalle(mascota_id: int):
    try:
        data = clinical_service.get_expediente(mascota_id)
    except BusinessError as error:
        abort(404, description=error.message)
    return render_template(
        "admin/expediente_detalle.html",
        active="expedientes",
        data=data,
        vets=clinical_service.list_vets(),
        productos=catalog_service.list_products(),
    )


@admin_bp.route("/clientes")
@staff_required
def clientes():
    search = (request.args.get("q") or "").strip()
    return render_template(
        "admin/clientes.html",
        active="clientes",
        clientes=clinical_service.list_clients(search=search or None),
        search=search,
    )


@admin_bp.route("/clientes/<int:cliente_id>")
@staff_required
def cliente_detalle(cliente_id: int):
    try:
        cliente = clinical_service.get_client(cliente_id)
    except BusinessError:
        abort(404)
    return render_template(
        "admin/cliente_detalle.html",
        active="clientes",
        cliente=cliente,
        mascotas=clinical_service.list_pets(cliente_id=cliente_id),
    )


@admin_bp.route("/inventario")
@staff_required
def inventario():
    inventory_service.refresh_lot_states()
    return render_template(
        "admin/inventario.html",
        active="inventario",
        productos=jsonable(catalog_service.list_products()),
        lotes=jsonable(inventory_service.list_lots()),
        movimientos=jsonable(inventory_service.list_movements(limit=80)),
        alertas=jsonable(inventory_service.inventory_alerts()),
        categorias=jsonable(catalog_service.list_categories()),
    )


@admin_bp.route("/compras")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def compras():
    return render_template(
        "admin/compras.html",
        active="compras",
        compras=jsonable(inventory_service.list_purchases()),
        proveedores=jsonable(inventory_service.list_suppliers()),
        productos=jsonable(catalog_service.list_products()),
    )


@admin_bp.route("/caja")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def caja():
    sesion = billing_service.get_open_session(session["uid"])
    resumen = billing_service.session_summary(sesion["IdSesion"]) if sesion else None
    return render_template(
        "admin/caja.html",
        active="caja",
        sesion=sesion,
        resumen=resumen,
        ventas=jsonable(billing_service.list_sales(limit=25)),
        conceptos=jsonable(catalog_service.list_concepts(only_active=True)),
        clientes=jsonable(clinical_service.list_clients()),
        sesiones=jsonable(billing_service.list_sessions(limit=10)),
    )


@admin_bp.route("/ventas")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def ventas():
    desde = parse_date(request.args.get("desde"), "desde", required=False)
    hasta = parse_date(request.args.get("hasta"), "hasta", required=False)
    estado = request.args.get("estado") or None
    origen = request.args.get("origen") or None
    return render_template(
        "admin/ventas.html",
        active="ventas",
        ventas=billing_service.list_sales(desde=desde, hasta=hasta, estado=estado, origen=origen),
        desde=desde,
        hasta=hasta,
        estado=estado,
        origen=origen,
    )


@admin_bp.route("/ventas/<int:venta_id>")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def venta_detalle(venta_id: int):
    try:
        venta = billing_service.get_sale(venta_id)
    except BusinessError:
        abort(404)
    return render_template("admin/venta_detalle.html", active="ventas", venta=venta)


@admin_bp.route("/catalogo")
@role_required(Config.ROLE_ADMIN)
def catalogo():
    return render_template(
        "admin/catalogo.html",
        active="catalogo",
        conceptos=jsonable(catalog_service.list_concepts(only_active=False)),
        servicios=jsonable(catalog_service.list_services()),
        categorias=jsonable(catalog_service.list_categories()),
        productos=jsonable(catalog_service.list_products()),
    )


@admin_bp.route("/usuarios")
@role_required(Config.ROLE_ADMIN)
def usuarios():
    return render_template(
        "admin/usuarios.html",
        active="usuarios",
        usuarios=auth_service.list_users(),
        roles=["Administrador", "Veterinario", "Cajero"],
    )


@admin_bp.route("/reportes")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def reportes():
    datos = dashboard_service.get_dashboard(session["uid"])
    return render_template(
        "admin/reportes.html",
        active="reportes",
        datos=datos,
        sesiones=billing_service.list_sessions(limit=15),
        ventas=billing_service.list_sales(limit=30),
    )
