"""API JSON consumida por el panel interno y la tienda."""
from __future__ import annotations

import datetime as dt

from flask import Blueprint, request

from config import Config
from security import client_required, current_user, login_required, role_required, staff_required
from services import (
    auth_service,
    billing_service,
    catalog_service,
    clinical_service,
    dashboard_service,
    ecommerce_service,
    inventory_service,
)
from utils import ok, parse_date, to_int

api_bp = Blueprint("api", __name__, url_prefix="/api")


def body() -> dict:
    return request.get_json(silent=True) or {}


def _date_arg(name: str):
    return parse_date(request.args.get(name), name, required=False)


# ==========================================================================
# Tablero
# ==========================================================================
@api_bp.get("/dashboard")
@staff_required
def dashboard():
    return ok(dashboard_service.get_dashboard(current_user()["id"]))


# ==========================================================================
# Clientes y mascotas
# ==========================================================================
@api_bp.get("/clientes")
@staff_required
def get_clientes():
    return ok(clinical_service.list_clients(request.args.get("q")))


@api_bp.get("/clientes/<int:cliente_id>")
@staff_required
def get_cliente(cliente_id: int):
    return ok(
        {
            "cliente": clinical_service.get_client(cliente_id),
            "mascotas": clinical_service.list_pets(cliente_id=cliente_id),
        }
    )


@api_bp.post("/clientes")
@staff_required
def post_cliente():
    return ok({"id_cliente": clinical_service.create_client(body())})


@api_bp.patch("/clientes/<int:cliente_id>")
@staff_required
def patch_cliente(cliente_id: int):
    clinical_service.update_client(cliente_id, body())
    return ok({"id_cliente": cliente_id})


@api_bp.post("/clientes/<int:cliente_id>/cuenta")
@role_required(Config.ROLE_ADMIN)
def post_cliente_cuenta(cliente_id: int):
    data = body()
    return ok(auth_service.create_client_account(cliente_id, data.get("correo"), data.get("contrasena")))


@api_bp.get("/clientes/<int:cliente_id>/mascotas")
@staff_required
def get_cliente_mascotas(cliente_id: int):
    return ok(clinical_service.list_pets(cliente_id=cliente_id))


@api_bp.get("/mascotas")
@staff_required
def get_mascotas():
    cliente_id = request.args.get("cliente")
    return ok(
        clinical_service.list_pets(
            cliente_id=int(cliente_id) if cliente_id else None,
            search=request.args.get("q"),
        )
    )


@api_bp.post("/mascotas")
@staff_required
def post_mascota():
    return ok({"id_mascota": clinical_service.create_pet(body())})


@api_bp.patch("/mascotas/<int:mascota_id>")
@staff_required
def patch_mascota(mascota_id: int):
    clinical_service.update_pet(mascota_id, body())
    return ok({"id_mascota": mascota_id})


@api_bp.get("/mascotas/<int:mascota_id>/expediente")
@staff_required
def get_expediente(mascota_id: int):
    return ok(clinical_service.get_expediente(mascota_id))


@api_bp.get("/veterinarios")
@staff_required
def get_veterinarios():
    return ok(clinical_service.list_vets())


# ==========================================================================
# Reservas y atenciones
# ==========================================================================
@api_bp.get("/reservas")
@staff_required
def get_reservas():
    cliente_id = request.args.get("cliente")
    return ok(
        clinical_service.list_reservations(
            fecha=_date_arg("fecha"),
            estado=request.args.get("estado") or None,
            cliente_id=int(cliente_id) if cliente_id else None,
        )
    )


@api_bp.post("/reservas")
@staff_required
def post_reserva():
    return ok({"id_reserva": clinical_service.create_reservation(body(), current_user())})


@api_bp.patch("/reservas/<int:reserva_id>/estado")
@staff_required
def patch_reserva(reserva_id: int):
    clinical_service.update_reservation_state(reserva_id, body().get("estado", ""))
    return ok({"id_reserva": reserva_id})


@api_bp.post("/reservas/<int:reserva_id>/checkin")
@staff_required
def post_checkin(reserva_id: int):
    return ok({"id_atencion": clinical_service.check_in(reserva_id, body(), current_user())})


@api_bp.get("/atenciones")
@staff_required
def get_atenciones():
    return ok(
        clinical_service.list_attentions(
            estado=request.args.get("estado") or None,
            fecha=_date_arg("fecha"),
        )
    )


@api_bp.post("/atenciones")
@staff_required
def post_atencion():
    return ok({"id_atencion": clinical_service.create_attention(body(), current_user())})


@api_bp.patch("/atenciones/<int:atencion_id>/estado")
@staff_required
def patch_atencion(atencion_id: int):
    clinical_service.update_attention_state(atencion_id, body().get("estado", ""))
    return ok({"id_atencion": atencion_id})


@api_bp.post("/consultas")
@role_required(Config.ROLE_ADMIN, Config.ROLE_VET)
def post_consulta():
    return ok(clinical_service.register_consultation(body(), current_user()))


# ==========================================================================
# Inventario
# ==========================================================================
@api_bp.get("/inventario/stock")
@staff_required
def get_stock():
    return ok(catalog_service.list_products())


@api_bp.get("/inventario/lotes")
@staff_required
def get_lotes():
    producto = request.args.get("producto")
    return ok(inventory_service.list_lots(int(producto) if producto else None))


@api_bp.get("/inventario/movimientos")
@staff_required
def get_movimientos():
    producto = request.args.get("producto")
    limit = request.args.get("limit", "100")
    return ok(
        inventory_service.list_movements(
            limit=int(limit) if str(limit).isdigit() else 100,
            producto_id=int(producto) if producto else None,
        )
    )


@api_bp.get("/inventario/alertas")
@staff_required
def get_alertas():
    return ok(inventory_service.inventory_alerts())


@api_bp.post("/inventario/salida")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def post_salida():
    return ok(inventory_service.create_exit(body(), current_user()["id"]))


@api_bp.post("/inventario/ajuste")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def post_ajuste():
    return ok(inventory_service.adjust_stock(body(), current_user()["id"]))


@api_bp.get("/categorias")
@staff_required
def get_categorias():
    return ok(catalog_service.list_categories())


@api_bp.post("/categorias")
@role_required(Config.ROLE_ADMIN)
def post_categoria():
    return ok({"id_categoria": catalog_service.create_category(body())})


@api_bp.get("/productos")
@staff_required
def get_productos():
    return ok(catalog_service.list_products())


@api_bp.post("/productos")
@role_required(Config.ROLE_ADMIN)
def post_producto():
    return ok(catalog_service.create_product(body()))


@api_bp.patch("/productos/<int:producto_id>")
@role_required(Config.ROLE_ADMIN)
def patch_producto(producto_id: int):
    catalog_service.update_product(producto_id, body())
    return ok({"id_producto": producto_id})


# ==========================================================================
# Compras y proveedores
# ==========================================================================
@api_bp.get("/proveedores")
@staff_required
def get_proveedores():
    return ok(inventory_service.list_suppliers())


@api_bp.post("/proveedores")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def post_proveedor():
    return ok({"id_proveedor": inventory_service.create_supplier(body())})


@api_bp.get("/compras")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def get_compras():
    return ok(inventory_service.list_purchases())


@api_bp.get("/compras/<int:compra_id>")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def get_compra(compra_id: int):
    return ok(inventory_service.get_purchase(compra_id))


@api_bp.post("/compras")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def post_compra():
    return ok(inventory_service.create_purchase(body(), current_user()["id"]))


# ==========================================================================
# Caja y facturación
# ==========================================================================
@api_bp.get("/caja/actual")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def get_caja_actual():
    sesion = billing_service.get_open_session(current_user()["id"])
    return ok(
        {
            "sesion": sesion,
            "resumen": billing_service.session_summary(sesion["IdSesion"]) if sesion else None,
        }
    )


@api_bp.post("/caja/abrir")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def post_abrir_caja():
    sesion_id = billing_service.open_session(current_user()["id"], body().get("monto_inicial", 0))
    return ok(billing_service.session_summary(sesion_id))


@api_bp.post("/caja/cerrar")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def post_cerrar_caja():
    data = body()
    sesion_id = data.get("id_sesion")
    if not sesion_id:
        sesion = billing_service.get_open_session(current_user()["id"])
        if not sesion:
            return ok({"mensaje": "No hay una sesión abierta."})
        sesion_id = sesion["IdSesion"]
    return ok(billing_service.close_session(int(sesion_id), current_user(), data.get("monto_contado")))


@api_bp.get("/caja/resumen/<int:sesion_id>")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def get_caja_resumen(sesion_id: int):
    return ok(billing_service.session_summary(sesion_id))


@api_bp.get("/caja/sesiones")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def get_caja_sesiones():
    return ok(billing_service.list_sessions())


@api_bp.get("/conceptos")
@staff_required
def get_conceptos():
    return ok(
        catalog_service.list_concepts(
            search=request.args.get("q"),
            tipo=request.args.get("tipo"),
            only_active=request.args.get("todos") != "1",
        )
    )


@api_bp.post("/conceptos")
@role_required(Config.ROLE_ADMIN)
def post_concepto():
    return ok({"id_concepto": catalog_service.create_concept(body())})


@api_bp.patch("/conceptos/<int:concepto_id>")
@role_required(Config.ROLE_ADMIN)
def patch_concepto(concepto_id: int):
    catalog_service.update_concept(concepto_id, body())
    return ok({"id_concepto": concepto_id})


@api_bp.get("/servicios")
@staff_required
def get_servicios():
    return ok(catalog_service.list_services())


@api_bp.post("/servicios")
@role_required(Config.ROLE_ADMIN)
def post_servicio():
    return ok(catalog_service.create_service(body()))


@api_bp.get("/ventas")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def get_ventas():
    return ok(
        billing_service.list_sales(
            desde=_date_arg("desde"),
            hasta=_date_arg("hasta"),
            estado=request.args.get("estado") or None,
            origen=request.args.get("origen") or None,
            cliente_id=int(request.args["cliente"]) if request.args.get("cliente") else None,
        )
    )


@api_bp.get("/ventas/<int:venta_id>")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def get_venta(venta_id: int):
    return ok(billing_service.get_sale(venta_id))


@api_bp.post("/ventas")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def post_venta():
    return ok(billing_service.create_sale(body(), current_user()))


@api_bp.post("/ventas/<int:venta_id>/anular")
@role_required(Config.ROLE_ADMIN, Config.ROLE_CASHIER)
def post_anular_venta(venta_id: int):
    return ok(billing_service.annul_sale(venta_id, current_user()))


# ==========================================================================
# Usuarios (solo administrador)
# ==========================================================================
@api_bp.get("/usuarios")
@role_required(Config.ROLE_ADMIN)
def get_usuarios():
    return ok(auth_service.list_users())


@api_bp.post("/usuarios")
@role_required(Config.ROLE_ADMIN)
def post_usuario():
    return ok(auth_service.create_staff_user(body()))


@api_bp.patch("/usuarios/<int:usuario_id>/estado")
@role_required(Config.ROLE_ADMIN)
def patch_usuario_estado(usuario_id: int):
    auth_service.set_user_state(usuario_id, body().get("estado", ""))
    return ok({"id_usuario": usuario_id})


# ==========================================================================
# Tienda en línea
# ==========================================================================
@api_bp.get("/tienda/catalogo")
def get_catalogo():
    return ok(
        catalog_service.list_concepts(
            search=request.args.get("q"),
            tipo=request.args.get("tipo"),
            categoria_id=int(request.args["categoria"]) if request.args.get("categoria") else None,
            only_active=True,
        )
    )


@api_bp.get("/tienda/carrito")
def get_carrito():
    return ok(ecommerce_service.cart_details())


@api_bp.post("/tienda/carrito")
def post_carrito():
    data = body()
    return ok(
        ecommerce_service.add_to_cart(
            to_int(data.get("id_concepto"), "concepto"),
            to_int(data.get("cantidad", 1), "cantidad", default=1),
        )
    )


@api_bp.patch("/tienda/carrito/<int:concepto_id>")
def patch_carrito(concepto_id: int):
    return ok(ecommerce_service.update_cart(concepto_id, body().get("cantidad", 0)))


@api_bp.delete("/tienda/carrito/<int:concepto_id>")
def delete_carrito(concepto_id: int):
    return ok(ecommerce_service.remove_from_cart(concepto_id))


@api_bp.post("/tienda/checkout")
@client_required
def post_checkout():
    return ok(ecommerce_service.checkout(current_user(), body()))


@api_bp.get("/tienda/mis-compras")
@client_required
def get_mis_compras():
    return ok(ecommerce_service.my_orders(current_user()["cliente_id"]))


@api_bp.get("/tienda/mis-mascotas")
@client_required
def get_mis_mascotas():
    return ok(ecommerce_service.my_pets(current_user()["cliente_id"]))


@api_bp.post("/tienda/mis-mascotas")
@client_required
def post_mi_mascota():
    return ok({"id_mascota": ecommerce_service.create_my_pet(current_user(), body())})


@api_bp.get("/tienda/mis-reservas")
@client_required
def get_mis_reservas():
    return ok(ecommerce_service.my_reservations(current_user()["cliente_id"]))


@api_bp.post("/tienda/reservas")
@client_required
def post_mi_reserva():
    data = body()
    return ok({"id_reserva": clinical_service.create_reservation(data, current_user())})


@api_bp.get("/tienda/perfil")
@client_required
def get_perfil():
    return ok(ecommerce_service.my_profile(current_user()["cliente_id"]))


@api_bp.patch("/tienda/perfil")
@client_required
def patch_perfil():
    ecommerce_service.update_profile(current_user()["cliente_id"], body())
    return ok(ecommerce_service.my_profile(current_user()["cliente_id"]))


@api_bp.get("/tienda/notificaciones")
@client_required
def get_notificaciones():
    return ok(ecommerce_service.link_notifications(current_user()["cliente_id"]))


@api_bp.post("/perfil/contrasena")
@login_required
def post_cambiar_contrasena():
    data = body()
    auth_service.change_password(
        current_user()["id"], data.get("actual", ""), data.get("nueva", "")
    )
    return ok({"mensaje": "Contraseña actualizada."})
