"""Facturación: caja, ventas POS, pagos y conceptos facturables."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any
from uuid import uuid4

from config import Config
from db import BusinessError, fetch_all, fetch_one, insert_returning, transaction
from services import inventory_service
from utils import parse_date, to_decimal, to_int

METODOS_PAGO = ("Efectivo", "Tarjeta", "Transferencia")


# --------------------------------------------------------------------------
# Sesión de caja
# --------------------------------------------------------------------------
def get_open_session(usuario_id: int) -> dict[str, Any] | None:
    return fetch_one(
        """
        SELECT S.*, U.Nombre + ' ' + U.Apellido AS Usuario
        FROM SESION_CAJA S
        INNER JOIN USUARIO U ON U.IdUsuario = S.IdUsuario
        WHERE S.IdUsuario = ? AND S.Estado = 'Abierta'
        ORDER BY S.FechaApert DESC
        """,
        (usuario_id,),
    )


def open_session(usuario_id: int, monto_inicial: Any = 0) -> int:
    monto = to_decimal(monto_inicial, "monto inicial", default=Decimal("0.00"))
    if monto < 0:
        raise BusinessError("El monto inicial no puede ser negativo.")
    if get_open_session(usuario_id):
        raise BusinessError("Ya tienes una sesión de caja abierta. Debes cerrarla primero.")
    with transaction() as cur:
        return insert_returning(
            cur,
            """
            INSERT INTO SESION_CAJA (FechaApert, MontoIni, Estado, IdUsuario)
            OUTPUT INSERTED.IdSesion
            VALUES (GETDATE(), ?, 'Abierta', ?)
            """,
            (monto, usuario_id),
        )


def session_summary(sesion_id: int) -> dict[str, Any]:
    sesion = fetch_one(
        """
        SELECT S.*, U.Nombre + ' ' + U.Apellido AS Usuario
        FROM SESION_CAJA S INNER JOIN USUARIO U ON U.IdUsuario = S.IdUsuario
        WHERE S.IdSesion = ?
        """,
        (sesion_id,),
    )
    if not sesion:
        raise BusinessError("Sesión de caja no encontrada.", 404)

    pagos = fetch_all(
        """
        SELECT P.Metodo, COUNT(*) AS Operaciones, ISNULL(SUM(P.Monto), 0) AS Total
        FROM PAGO P
        INNER JOIN VENTA V ON V.IdVenta = P.IdVenta
        WHERE P.IdSesion = ? AND V.Estado = 'Pagada'
        GROUP BY P.Metodo
        """,
        (sesion_id,),
    )
    total_ventas = sum(float(p["Total"] or 0) for p in pagos)
    efectivo = sum(float(p["Total"] or 0) for p in pagos if p["Metodo"] == "Efectivo")
    ventas = fetch_one(
        """
        SELECT COUNT(DISTINCT V.IdVenta) AS Ventas,
               ISNULL(SUM(D.Cantidad * D.PrecioUnit), 0) AS Facturado
        FROM PAGO P
        INNER JOIN VENTA V ON V.IdVenta = P.IdVenta
        INNER JOIN DETALLE_VENTA D ON D.IdVenta = V.IdVenta
        WHERE P.IdSesion = ? AND V.Estado = 'Pagada'
        """,
        (sesion_id,),
    )
    anuladas = fetch_one(
        """
        SELECT COUNT(DISTINCT V.IdVenta) AS Total
        FROM PAGO P INNER JOIN VENTA V ON V.IdVenta = P.IdVenta
        WHERE P.IdSesion = ? AND V.Estado = 'Anulada'
        """,
        (sesion_id,),
    )
    monto_ini = float(sesion["MontoIni"] or 0)
    sesion["pagos"] = pagos
    sesion["total_ventas"] = total_ventas
    sesion["efectivo"] = efectivo
    sesion["esperado_efectivo"] = monto_ini + efectivo
    sesion["ventas_count"] = int(ventas["Ventas"] or 0)
    sesion["facturado"] = float(ventas["Facturado"] or 0)
    sesion["anuladas_count"] = int(anuladas["Total"] or 0)
    if sesion["MontoCont"] is not None:
        sesion["diferencia"] = float(sesion["MontoCont"]) - sesion["esperado_efectivo"]
    else:
        sesion["diferencia"] = None
    return sesion


def close_session(sesion_id: int, actor: dict[str, Any], monto_contado: Any = None) -> dict[str, Any]:
    sesion = fetch_one("SELECT * FROM SESION_CAJA WHERE IdSesion = ?", (sesion_id,))
    if not sesion:
        raise BusinessError("Sesión de caja no encontrada.", 404)
    if sesion["Estado"] == "Cerrada":
        raise BusinessError("La sesión ya está cerrada.")
    if int(sesion["IdUsuario"]) != int(actor["id"]) and actor.get("rol") != Config.ROLE_ADMIN:
        raise BusinessError("Solo el cajero que abrió la sesión o un administrador puede cerrarla.", 403)

    resumen = session_summary(sesion_id)
    contado = to_decimal(
        monto_contado,
        "monto contado",
        default=Decimal(str(round(resumen["esperado_efectivo"], 2))),
    )
    with transaction() as cur:
        cur.execute(
            """
            UPDATE SESION_CAJA
            SET FechaCierre = GETDATE(), MontoCont = ?, Estado = 'Cerrada'
            WHERE IdSesion = ?
            """,
            (contado, sesion_id),
        )
    return session_summary(sesion_id)


def list_sessions(limit: int = 30) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT TOP (CAST(? AS INT)) S.IdSesion, S.FechaApert, S.FechaCierre, S.MontoIni, S.MontoCont,
               S.Estado, U.Nombre + ' ' + U.Apellido AS Usuario,
               (SELECT COUNT(DISTINCT P.IdVenta) FROM PAGO P
                 INNER JOIN VENTA V ON V.IdVenta = P.IdVenta
                 WHERE P.IdSesion = S.IdSesion AND V.Estado = 'Pagada') AS Ventas,
               (SELECT ISNULL(SUM(P.Monto), 0) FROM PAGO P
                 INNER JOIN VENTA V ON V.IdVenta = P.IdVenta
                 WHERE P.IdSesion = S.IdSesion AND V.Estado = 'Pagada') AS Total
        FROM SESION_CAJA S
        INNER JOIN USUARIO U ON U.IdUsuario = S.IdUsuario
        ORDER BY S.FechaApert DESC
        """,
        (max(1, min(limit, 200)),),
    )


# --------------------------------------------------------------------------
# Ventas
# --------------------------------------------------------------------------
def _walkin_client(cur) -> int:
    cur.execute("SELECT IdCliente FROM CLIENTE WHERE Cedula = 'CF-000000'")
    row = cur.fetchone()
    if row:
        return int(row[0])
    return insert_returning(
        cur,
        """
        INSERT INTO CLIENTE (Nombre, Apellido, Cedula, Telefono, Correo, Direccion, AceptaNotif)
        OUTPUT INSERTED.IdCliente
        VALUES ('Cliente', 'Mostrador', 'CF-000000', NULL, NULL, NULL, 0)
        """,
    )


def _get_concept(cur, concepto_id: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT C.IdConcepto, C.TipoConcepto, C.Nombre, C.Precio, C.Estado,
               P.IdProducto, P.Nombre AS Producto
        FROM CONCEPTO_FACTURABLE C
        LEFT JOIN PRODUCTO P ON P.IdConcepto = C.IdConcepto
        WHERE C.IdConcepto = ?
        """,
        (concepto_id,),
    )
    row = cur.fetchone()
    if not row:
        raise BusinessError("El concepto facturable no existe.")
    columns = [c[0] for c in cur.description]
    return dict(zip(columns, row))


def normalize_items(cur, items: list[dict[str, Any]], allow_price_override: bool = False) -> list[dict[str, Any]]:
    if not items:
        raise BusinessError("Agrega al menos un producto o servicio a la venta.")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        concepto_id = to_int(item.get("id_concepto") or item.get("idConcepto"), "concepto")
        cantidad = to_int(item.get("cantidad"), "cantidad")
        if cantidad <= 0:
            raise BusinessError(f"La línea {index} debe tener cantidad mayor que cero.")
        concept = _get_concept(cur, concepto_id)
        if concept["Estado"] != "Activo":
            raise BusinessError(f"El concepto '{concept['Nombre']}' está inactivo.")

        precio = concept["Precio"]
        if allow_price_override and item.get("precio_unit") not in (None, ""):
            precio = to_decimal(item.get("precio_unit"), "precio unitario")
        if precio < 0:
            raise BusinessError("El precio no puede ser negativo.")

        normalized.append(
            {
                "id_concepto": int(concepto_id),
                "nombre": concept["Nombre"],
                "tipo": concept["TipoConcepto"],
                "id_producto": int(concept["IdProducto"]) if concept["IdProducto"] else None,
                "cantidad": cantidad,
                "precio_unit": Decimal(precio),
                "subtotal": Decimal(precio) * cantidad,
            }
        )
    return normalized


def persist_sale(
    cur,
    *,
    cliente_id: int,
    usuario_id: int,
    origen: str,
    items: list[dict[str, Any]],
    metodo: str,
    referencia: str | None = None,
    sesion_id: int | None = None,
    estado: str = "Pagada",
) -> dict[str, Any]:
    """Inserta venta, detalle, pago y descuenta inventario. Requiere transacción abierta."""
    if origen not in ("POS", "Web"):
        raise BusinessError("Origen de venta inválido.")
    if metodo not in METODOS_PAGO:
        raise BusinessError("Método de pago inválido.")
    if not items:
        raise BusinessError("La venta no tiene líneas.")

    total = sum((item["subtotal"] for item in items), Decimal("0.00"))
    temp_invoice = f"TMP-{uuid4().hex}"

    venta_id = insert_returning(
        cur,
        """
        INSERT INTO VENTA (FechaVenta, Factura, Estado, IdCliente, IdUsuario, Origen)
        OUTPUT INSERTED.IdVenta
        VALUES (GETDATE(), ?, ?, ?, ?, ?)
        """,
        (temp_invoice, estado, cliente_id, usuario_id, origen),
    )
    factura = f"FAC-{venta_id:06d}"
    cur.execute("UPDATE VENTA SET Factura = ? WHERE IdVenta = ?", (factura, venta_id))

    for item in items:
        cur.execute(
            """
            INSERT INTO DETALLE_VENTA (Cantidad, PrecioUnit, IdVenta, IdConcepto)
            VALUES (?, ?, ?, ?)
            """,
            (item["cantidad"], item["precio_unit"], venta_id, item["id_concepto"]),
        )
        if item["id_producto"]:
            inventory_service.consume_fefo(
                cur,
                item["id_producto"],
                item["cantidad"],
                usuario_id,
                f"Venta {'Web ' if origen == 'Web' else ''}{factura}",
            )

    cur.execute(
        """
        INSERT INTO PAGO (FechaPago, Monto, Metodo, Referencia, IdVenta, IdSesion)
        VALUES (GETDATE(), ?, ?, ?, ?, ?)
        """,
        (total, metodo, (referencia or "").strip() or None, venta_id, sesion_id),
    )

    return {
        "id_venta": venta_id,
        "factura": factura,
        "total": float(total),
        "metodo": metodo,
        "origen": origen,
        "sesion_id": sesion_id,
        "items": [
            {
                "id_concepto": i["id_concepto"],
                "nombre": i["nombre"],
                "cantidad": i["cantidad"],
                "precio_unit": float(i["precio_unit"]),
                "subtotal": float(i["subtotal"]),
            }
            for i in items
        ],
    }


def create_sale(payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    items_raw = payload.get("items") or []
    metodo = (payload.get("metodo") or "Efectivo").strip()
    referencia = (payload.get("referencia") or "").strip() or None

    sesion = get_open_session(actor["id"])
    if not sesion:
        raise BusinessError("Abre una sesión de caja antes de registrar ventas.", 409)

    with transaction() as cur:
        cliente_id = payload.get("id_cliente") or payload.get("clienteId")
        cliente_id = to_int(cliente_id, "cliente") if cliente_id else _walkin_client(cur)
        if not cur.execute("SELECT 1 FROM CLIENTE WHERE IdCliente = ?", (cliente_id,)).fetchone():
            raise BusinessError("Cliente no encontrado.", 404)

        items = normalize_items(
            cur,
            items_raw,
            allow_price_override=actor.get("rol") == Config.ROLE_ADMIN,
        )
        result = persist_sale(
            cur,
            cliente_id=cliente_id,
            usuario_id=actor["id"],
            origen="POS",
            items=items,
            metodo=metodo,
            referencia=referencia,
            sesion_id=int(sesion["IdSesion"]),
        )

        # Vuelto cuando el cliente paga en efectivo con un monto mayor
        recibido = payload.get("monto_recibido")
        if metodo == "Efectivo" and recibido not in (None, ""):
            recibido_dec = to_decimal(recibido, "monto recibido")
            if recibido_dec < Decimal(str(result["total"])):
                raise BusinessError("El monto recibido es menor que el total de la venta.")
            result["recibido"] = float(recibido_dec)
            result["vuelto"] = float(recibido_dec - Decimal(str(result["total"])))
        else:
            result["recibido"] = result["total"]
            result["vuelto"] = 0.0
    return result


def list_sales(
    desde: dt.date | None = None,
    hasta: dt.date | None = None,
    estado: str | None = None,
    origen: str | None = None,
    cliente_id: int | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    conditions = ["1 = 1"]
    params: list[Any] = []
    if desde:
        conditions.append("CAST(V.FechaVenta AS DATE) >= ?")
        params.append(desde)
    if hasta:
        conditions.append("CAST(V.FechaVenta AS DATE) <= ?")
        params.append(hasta)
    if estado:
        conditions.append("V.Estado = ?")
        params.append(estado)
    if origen:
        conditions.append("V.Origen = ?")
        params.append(origen)
    if cliente_id:
        conditions.append("V.IdCliente = ?")
        params.append(cliente_id)
    params.insert(0, max(1, min(limit, 500)))
    return fetch_all(
        f"""
        SELECT TOP (CAST(? AS INT)) V.IdVenta, V.FechaVenta, V.Factura, V.Estado, V.Origen,
               C.Nombre + ' ' + C.Apellido AS Cliente, V.IdCliente,
               U.Nombre + ' ' + U.Apellido AS Usuario,
               (SELECT ISNULL(SUM(D.Cantidad * D.PrecioUnit), 0)
                  FROM DETALLE_VENTA D WHERE D.IdVenta = V.IdVenta) AS Total,
               (SELECT COUNT(*) FROM DETALLE_VENTA D WHERE D.IdVenta = V.IdVenta) AS Lineas,
               (SELECT TOP 1 P.Metodo FROM PAGO P WHERE P.IdVenta = V.IdVenta ORDER BY P.IdPago) AS Metodo,
               (SELECT TOP 1 P.Monto FROM PAGO P WHERE P.IdVenta = V.IdVenta ORDER BY P.IdPago) AS Pagado
        FROM VENTA V
        INNER JOIN CLIENTE C ON C.IdCliente = V.IdCliente
        INNER JOIN USUARIO U ON U.IdUsuario = V.IdUsuario
        WHERE {' AND '.join(conditions)}
        ORDER BY V.FechaVenta DESC, V.IdVenta DESC
        """,
        params,
    )


def get_sale(venta_id: int) -> dict[str, Any]:
    venta = fetch_one(
        """
        SELECT V.*, C.Nombre + ' ' + C.Apellido AS Cliente, C.Cedula, C.Correo,
               U.Nombre + ' ' + U.Apellido AS Usuario
        FROM VENTA V
        INNER JOIN CLIENTE C ON C.IdCliente = V.IdCliente
        INNER JOIN USUARIO U ON U.IdUsuario = V.IdUsuario
        WHERE V.IdVenta = ?
        """,
        (venta_id,),
    )
    if not venta:
        raise BusinessError("Venta no encontrada.", 404)
    venta["detalle"] = fetch_all(
        """
        SELECT D.*, C.Nombre AS Concepto, C.TipoConcepto
        FROM DETALLE_VENTA D
        INNER JOIN CONCEPTO_FACTURABLE C ON C.IdConcepto = D.IdConcepto
        WHERE D.IdVenta = ?
        """,
        (venta_id,),
    )
    venta["pagos"] = fetch_all(
        """
        SELECT P.*, S.IdSesion
        FROM PAGO P LEFT JOIN SESION_CAJA S ON S.IdSesion = P.IdSesion
        WHERE P.IdVenta = ?
        """,
        (venta_id,),
    )
    venta["total"] = sum(float(d["Cantidad"]) * float(d["PrecioUnit"]) for d in venta["detalle"])
    return venta


def annul_sale(venta_id: int, actor: dict[str, Any]) -> dict[str, Any]:
    venta = fetch_one("SELECT * FROM VENTA WHERE IdVenta = ?", (venta_id,))
    if not venta:
        raise BusinessError("Venta no encontrada.", 404)
    if venta["Estado"] == "Anulada":
        raise BusinessError("La venta ya está anulada.")
    if actor.get("rol") not in (Config.ROLE_ADMIN, Config.ROLE_CASHIER):
        raise BusinessError("No tienes permiso para anular ventas.", 403)

    with transaction() as cur:
        cur.execute(
            """
            SELECT IdLote, Cantidad, Motivo
            FROM MOVIMIENTO_INVENTARIO
            WHERE TipoMov = 'Salida' AND Motivo IN (?, ?)
            """,
            (f"Venta {venta['Factura']}", f"Venta Web {venta['Factura']}"),
        )
        movimientos = cur.fetchall()
        for mov in movimientos:
            inventory_service.restore_to_lot(
                cur,
                int(mov[0]),
                int(mov[1]),
                actor["id"],
                f"Anulación {venta['Factura']}",
            )
        cur.execute("UPDATE VENTA SET Estado = 'Anulada' WHERE IdVenta = ?", (venta_id,))
    return {"id_venta": venta_id, "factura": venta["Factura"], "movimientos_revertidos": len(movimientos)}
