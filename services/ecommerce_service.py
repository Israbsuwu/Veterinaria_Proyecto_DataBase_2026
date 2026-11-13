"""Servicio de la tienda en línea (carrito, checkout y cuenta del cliente)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from flask import session

from config import Config
from db import BusinessError, fetch_all, fetch_one, transaction
from services import auth_service, billing_service, catalog_service, clinical_service
from utils import to_int

CART_KEY = "shop_cart"


# --------------------------------------------------------------------------
# Carrito
# --------------------------------------------------------------------------
def get_cart() -> dict[int, int]:
    raw = session.get(CART_KEY) or {}
    cart: dict[int, int] = {}
    for key, value in raw.items():
        try:
            cart[int(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return cart


def _save_cart(cart: dict[int, int]) -> None:
    session[CART_KEY] = {str(k): v for k, v in cart.items() if v > 0}
    session.modified = True


def clear_cart() -> None:
    session.pop(CART_KEY, None)
    session.modified = True


def cart_count() -> int:
    return sum(get_cart().values())


def add_to_cart(concepto_id: int, cantidad: int = 1) -> dict[str, Any]:
    cantidad = to_int(cantidad, "cantidad", default=1)
    if cantidad <= 0:
        raise BusinessError("La cantidad debe ser mayor que cero.")
    concept = catalog_service.get_concept(concepto_id)
    if concept["Estado"] != "Activo":
        raise BusinessError("Este producto o servicio no está disponible.")
    cart = get_cart()
    nuevo_total = cart.get(concepto_id, 0) + cantidad
    if concept["TipoConcepto"] == "Producto":
        stock = int(concept.get("Stock") or 0)
        if nuevo_total > stock:
            raise BusinessError(
                f"Solo hay {stock} unidad(es) disponibles de '{concept['Nombre']}'."
            )
    cart[concepto_id] = nuevo_total
    _save_cart(cart)
    return {"cantidad": nuevo_total, "carrito_count": cart_count()}


def update_cart(concepto_id: int, cantidad: int) -> dict[str, Any]:
    cantidad = to_int(cantidad, "cantidad", default=0)
    cart = get_cart()
    if cantidad <= 0:
        cart.pop(concepto_id, None)
        _save_cart(cart)
        return {"eliminado": True, "carrito_count": cart_count()}
    concept = catalog_service.get_concept(concepto_id)
    if concept["TipoConcepto"] == "Producto" and cantidad > int(concept.get("Stock") or 0):
        raise BusinessError(f"Solo hay {int(concept.get('Stock') or 0)} unidad(es) disponibles.")
    cart[concepto_id] = cantidad
    _save_cart(cart)
    return {"cantidad": cantidad, "carrito_count": cart_count()}


def remove_from_cart(concepto_id: int) -> dict[str, Any]:
    cart = get_cart()
    cart.pop(concepto_id, None)
    _save_cart(cart)
    return {"carrito_count": cart_count()}


def cart_details() -> dict[str, Any]:
    cart = get_cart()
    lines: list[dict[str, Any]] = []
    invalid: list[int] = []
    for concepto_id, cantidad in cart.items():
        try:
            concept = catalog_service.get_concept(concepto_id)
        except BusinessError:
            invalid.append(concepto_id)
            continue
        if concept["Estado"] != "Activo":
            invalid.append(concepto_id)
            continue
        precio = Decimal(str(concept["Precio"]))
        stock = int(concept.get("Stock") or 0) if concept["TipoConcepto"] == "Producto" else None
        lines.append(
            {
                **concept,
                "Cantidad": cantidad,
                "Subtotal": float(precio * cantidad),
                "Disponible": stock is None or stock >= cantidad,
                "StockActual": stock,
            }
        )
    if invalid:
        for concepto_id in invalid:
            cart.pop(concepto_id, None)
        _save_cart(cart)
    total = sum(Decimal(str(line["Subtotal"])) for line in lines)
    return {
        "lineas": lines,
        "total": float(total),
        "cantidad": sum(line["Cantidad"] for line in lines),
        "todo_disponible": all(line["Disponible"] for line in lines),
    }


# --------------------------------------------------------------------------
# Checkout
# --------------------------------------------------------------------------
def checkout(actor: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    cart = get_cart()
    if not cart:
        raise BusinessError("Tu carrito está vacío.")
    cliente_id = actor.get("cliente_id")
    if not cliente_id:
        raise BusinessError("Tu usuario no tiene una ficha de cliente vinculada.", 403)

    metodo = (payload.get("metodo") or "Tarjeta").strip()
    referencia = (payload.get("referencia") or "").strip() or None
    if metodo not in ("Tarjeta", "Transferencia", "Efectivo"):
        raise BusinessError("Método de pago inválido.")
    if metodo == "Efectivo":
        raise BusinessError("La tienda en línea solo acepta tarjeta o transferencia.")

    items = [{"id_concepto": cid, "cantidad": qty} for cid, qty in cart.items()]
    with transaction() as cur:
        normalized = billing_service.normalize_items(cur, items, allow_price_override=False)
        result = billing_service.persist_sale(
            cur,
            cliente_id=int(cliente_id),
            usuario_id=int(actor["id"]),
            origen="Web",
            items=normalized,
            metodo=metodo,
            referencia=referencia,
            sesion_id=None,
        )
    clear_cart()
    return result


def my_orders(cliente_id: int, limite: int = 50) -> list[dict[str, Any]]:
    return billing_service.list_sales(cliente_id=cliente_id, origen="Web", limit=limite)


def my_reservations(cliente_id: int) -> list[dict[str, Any]]:
    return clinical_service.list_reservations(cliente_id=cliente_id)


def my_pets(cliente_id: int) -> list[dict[str, Any]]:
    return clinical_service.list_pets(cliente_id=cliente_id)


def my_profile(cliente_id: int) -> dict[str, Any]:
    cliente = clinical_service.get_client(cliente_id)
    user = fetch_one(
        """
        SELECT U.IdUsuario, U.Nombre, U.Apellido, U.Correo, U.Telefono, U.FechaReg, R.NombreRol
        FROM USUARIO U INNER JOIN ROL R ON R.IdRol = U.IdRol
        WHERE U.IdUsuario = ?
        """,
        (cliente["IdUsuario"],),
    ) if cliente["IdUsuario"] else None
    return {"cliente": cliente, "usuario": user}


def update_profile(cliente_id: int, data: dict[str, Any]) -> None:
    clinical_service.update_client(cliente_id, data)


def create_my_pet(actor: dict[str, Any], data: dict[str, Any]) -> int:
    data = dict(data)
    data["id_cliente"] = actor["cliente_id"]
    return clinical_service.create_pet(data)


def register_and_login(data: dict[str, Any]) -> dict[str, Any]:
    user = auth_service.register_client(data)
    return auth_service.authenticate(user["correo"], data.get("contrasena") or data.get("password"), "client")


def link_notifications(cliente_id: int, limite: int = 20) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT TOP (CAST(? AS INT)) IdNotif, Tipo, Canal, FechaProg, FechaEnv, Estado
        FROM NOTIFICACION
        WHERE IdCliente = ?
        ORDER BY FechaProg DESC
        """,
        (max(1, min(limite, 100)), cliente_id),
    )
