"""Tienda en línea para clientes."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from db import BusinessError
from security import client_required, current_user
from services import billing_service, catalog_service, clinical_service, ecommerce_service
from utils import to_int

shop_bp = Blueprint("shop", __name__, url_prefix="/tienda")


@shop_bp.route("/")
def home():
    productos = catalog_service.list_concepts(tipo="Producto", only_active=True)
    servicios = catalog_service.list_concepts(tipo="Servicio", only_active=True)
    return render_template(
        "shop/home.html",
        active="home",
        productos=productos[:8],
        servicios=servicios[:4],
        categorias=catalog_service.list_categories(),
    )


@shop_bp.route("/catalogo")
def catalogo():
    search = (request.args.get("q") or "").strip()
    tipo = request.args.get("tipo") or None
    categoria = request.args.get("categoria") or None
    return render_template(
        "shop/catalogo.html",
        active="catalogo",
        productos=catalog_service.list_concepts(
            search=search or None,
            tipo=tipo,
            categoria_id=int(categoria) if categoria and categoria.isdigit() else None,
            only_active=True,
        ),
        categorias=catalog_service.list_categories(),
        search=search,
        tipo=tipo,
        categoria=categoria,
    )


@shop_bp.route("/carrito")
def carrito():
    return render_template("shop/carrito.html", active="carrito", carrito=ecommerce_service.cart_details())


@shop_bp.route("/checkout")
@client_required
def checkout():
    carrito = ecommerce_service.cart_details()
    if not carrito["lineas"]:
        flash("Tu carrito está vacío. Agrega productos o servicios primero.", "warning")
        return redirect(url_for("shop.catalogo"))
    return render_template(
        "shop/checkout.html",
        active="carrito",
        carrito=carrito,
        perfil=ecommerce_service.my_profile(current_user()["cliente_id"]),
    )


@shop_bp.route("/cuenta")
@client_required
def cuenta():
    cliente_id = current_user()["cliente_id"]
    return render_template(
        "shop/cuenta.html",
        active="cuenta",
        perfil=ecommerce_service.my_profile(cliente_id),
        mascotas=ecommerce_service.my_pets(cliente_id),
        pedidos=ecommerce_service.my_orders(cliente_id),
        reservas=ecommerce_service.my_reservations(cliente_id),
        notificaciones=ecommerce_service.link_notifications(cliente_id),
        servicios=catalog_service.list_concepts(tipo="Servicio", only_active=True),
        vets=clinical_service.list_vets(),
    )


@shop_bp.route("/reservar")
@client_required
def reservar():
    cliente_id = current_user()["cliente_id"]
    return render_template(
        "shop/reservar.html",
        active="cuenta",
        mascotas=ecommerce_service.my_pets(cliente_id),
        vets=clinical_service.list_vets(),
        servicios=catalog_service.list_concepts(tipo="Servicio", only_active=True),
    )


@shop_bp.route("/pedido/<int:venta_id>")
@client_required
def pedido(venta_id: int):
    try:
        venta = billing_service.get_sale(venta_id)
    except BusinessError:
        abort(404)
    if int(venta["IdCliente"]) != int(current_user()["cliente_id"]):
        abort(403)
    return render_template("shop/pedido.html", active="cuenta", venta=venta)
