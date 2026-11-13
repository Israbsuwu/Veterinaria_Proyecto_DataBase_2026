"""Inventario: productos, lotes, compras, salidas y ajustes (FEFO)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from db import BusinessError, fetch_all, fetch_one, fetch_scalar, insert_returning, transaction
from utils import parse_date, to_decimal, to_int


def refresh_lot_states() -> None:
    """Marca lotes vencidos o agotados según stock y fecha actual."""
    with transaction() as cur:
        _refresh_lot_states(cur)


def _refresh_lot_states(cur) -> None:
    cur.execute(
        """
        UPDATE L
        SET Estado = 'Vencido'
        FROM LOTE L
        WHERE L.Estado = 'Disponible'
          AND L.FechaVenc < CAST(GETDATE() AS DATE)
        """
    )
    cur.execute(
        """
        UPDATE L
        SET Estado = 'Agotado'
        FROM LOTE L
        INNER JOIN VW_LOTE_STOCK S ON S.IdLote = L.IdLote
        WHERE L.Estado = 'Disponible'
          AND S.StockLote <= 0
          AND L.FechaVenc >= CAST(GETDATE() AS DATE)
        """
    )


def list_lots(producto_id: int | None = None, include_empty: bool = True) -> list[dict[str, Any]]:
    conditions = ["1 = 1"]
    params: list[Any] = []
    if producto_id:
        conditions.append("IdProducto = ?")
        params.append(producto_id)
    if not include_empty:
        conditions.append("StockLote > 0")
    return fetch_all(
        f"""
        SELECT *, DATEDIFF(day, CAST(GETDATE() AS DATE), FechaVenc) AS DiasParaVencer
        FROM VW_LOTE_STOCK
        WHERE {' AND '.join(conditions)}
        ORDER BY FechaVenc, CodigoLote
        """,
        params,
    )


def list_movements(limit: int = 120, producto_id: int | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    condition = ""
    if producto_id:
        condition = "WHERE L.IdProducto = ?"
        params.append(producto_id)
    params.insert(0, max(1, min(int(limit), 500)))
    return fetch_all(
        f"""
        SELECT TOP (CAST(? AS INT)) M.IdMov, M.FechaMov, M.TipoMov, M.Cantidad, M.Motivo,
               M.IdLote, L.CodigoLote, L.FechaVenc, P.IdProducto, P.Nombre AS Producto,
               U.Nombre + ' ' + U.Apellido AS Usuario
        FROM MOVIMIENTO_INVENTARIO M
        INNER JOIN LOTE L ON L.IdLote = M.IdLote
        INNER JOIN PRODUCTO P ON P.IdProducto = L.IdProducto
        INNER JOIN USUARIO U ON U.IdUsuario = M.IdUsuario
        {condition}
        ORDER BY M.FechaMov DESC, M.IdMov DESC
        """,
        params,
    )


def product_stock(producto_id: int) -> int:
    return int(fetch_scalar("SELECT Stock FROM VW_STOCK_PRODUCTO WHERE IdProducto = ?", (producto_id,), 0) or 0)


def _available_lots(cur, producto_id: int, allow_expired: bool = False) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT IdLote, CodigoLote, FechaVenc, StockLote, Estado
        FROM VW_LOTE_STOCK
        WHERE IdProducto = ?
          AND StockLote > 0
          AND Estado <> 'Cuarentena'
          AND (? = 1 OR FechaVenc >= CAST(GETDATE() AS DATE))
        ORDER BY FechaVenc, IdLote
        """,
        (producto_id, 1 if allow_expired else 0),
    )
    columns = [c[0] for c in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def consume_fefo(
    cur,
    producto_id: int,
    cantidad: int,
    usuario_id: int,
    motivo: str,
    lote_id: int | None = None,
    allow_expired: bool = False,
) -> list[dict[str, Any]]:
    """Descuenta stock usando FEFO (First Expired, First Out)."""
    cantidad = int(cantidad)
    if cantidad <= 0:
        raise BusinessError("La cantidad a descontar debe ser mayor que cero.")

    product = cur.execute(
        "SELECT IdProducto, Nombre FROM PRODUCTO WHERE IdProducto = ?", (producto_id,)
    ).fetchone()
    if not product:
        raise BusinessError("Producto no encontrado.", 404)

    if lote_id:
        cur.execute(
            """
            SELECT IdLote, CodigoLote, FechaVenc, StockLote, Estado
            FROM VW_LOTE_STOCK
            WHERE IdLote = ? AND IdProducto = ?
            """,
            (lote_id, producto_id),
        )
        row = cur.fetchone()
        if not row:
            raise BusinessError("El lote indicado no pertenece al producto.")
        cols = [c[0] for c in cur.description]
        lots = [dict(zip(cols, row))]
    else:
        lots = _available_lots(cur, producto_id, allow_expired)

    disponible = sum(int(lot["StockLote"]) for lot in lots)
    if disponible < cantidad:
        raise BusinessError(
            f"Stock insuficiente de '{product['Nombre']}': disponible {disponible}, solicitado {cantidad}."
        )

    remaining = cantidad
    used: list[dict[str, Any]] = []
    for lot in lots:
        if remaining <= 0:
            break
        stock_lote = int(lot["StockLote"])
        if stock_lote <= 0:
            continue
        take = min(stock_lote, remaining)
        cur.execute(
            """
            INSERT INTO MOVIMIENTO_INVENTARIO (TipoMov, Cantidad, Motivo, IdLote, IdUsuario)
            VALUES ('Salida', ?, ?, ?, ?)
            """,
            (take, motivo[:255], lot["IdLote"], usuario_id),
        )
        remaining -= take
        used.append({"id_lote": int(lot["IdLote"]), "codigo_lote": lot["CodigoLote"], "cantidad": take})
        if stock_lote - take <= 0:
            cur.execute("UPDATE LOTE SET Estado = 'Agotado' WHERE IdLote = ?", (lot["IdLote"],))

    return used


def restore_to_lot(cur, lote_id: int, cantidad: int, usuario_id: int, motivo: str) -> None:
    cur.execute(
        """
        INSERT INTO MOVIMIENTO_INVENTARIO (TipoMov, Cantidad, Motivo, IdLote, IdUsuario)
        VALUES ('Entrada', ?, ?, ?, ?)
        """,
        (int(cantidad), motivo[:255], lote_id, usuario_id),
    )
    cur.execute(
        "UPDATE LOTE SET Estado = 'Disponible' WHERE IdLote = ? AND Estado = 'Agotado'",
        (lote_id,),
    )


def create_exit(data: dict[str, Any], usuario_id: int) -> dict[str, Any]:
    producto_id = to_int(data.get("id_producto"), "producto")
    cantidad = to_int(data.get("cantidad"), "cantidad")
    motivo = (data.get("motivo") or "Salida manual de inventario").strip()
    lote_id = to_int(data["id_lote"], "lote") if data.get("id_lote") else None
    with transaction() as cur:
        used = consume_fefo(cur, producto_id, cantidad, usuario_id, motivo, lote_id=lote_id)
    return {"movimientos": used}


def adjust_stock(data: dict[str, Any], usuario_id: int) -> dict[str, Any]:
    lote_id = to_int(data.get("id_lote"), "lote")
    nueva_cantidad = to_int(data.get("nueva_cantidad"), "nueva cantidad")
    if nueva_cantidad < 0:
        raise BusinessError("La cantidad contada no puede ser negativa.")
    motivo = (data.get("motivo") or "Ajuste de inventario").strip()

    with transaction() as cur:
        cur.execute("SELECT StockLote FROM VW_LOTE_STOCK WHERE IdLote = ?", (lote_id,))
        row = cur.fetchone()
        if not row:
            raise BusinessError("Lote no encontrado.", 404)
        actual = int(row[0] or 0)
        delta = nueva_cantidad - actual
        if delta == 0:
            return {"delta": 0, "stock": actual}
        cur.execute(
            """
            INSERT INTO MOVIMIENTO_INVENTARIO (TipoMov, Cantidad, Motivo, IdLote, IdUsuario)
            VALUES ('Ajuste', ?, ?, ?, ?)
            """,
            (delta, motivo[:255], lote_id, usuario_id),
        )
        cur.execute(
            """
            UPDATE LOTE
            SET Estado = CASE
                WHEN ? <= 0 THEN 'Agotado'
                WHEN FechaVenc < CAST(GETDATE() AS DATE) THEN 'Vencido'
                ELSE 'Disponible' END
            WHERE IdLote = ?
            """,
            (nueva_cantidad, lote_id),
        )
    return {"delta": delta, "stock": nueva_cantidad}


def list_suppliers() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT IdProveedor, Nombre, Telefono, Correo, Direccion, Estado
        FROM PROVEEDOR ORDER BY Nombre
        """
    )


def create_supplier(data: dict[str, Any]) -> int:
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        raise BusinessError("El nombre del proveedor es obligatorio.")
    with transaction() as cur:
        return insert_returning(
            cur,
            """
            INSERT INTO PROVEEDOR (Nombre, Telefono, Correo, Direccion, Estado)
            OUTPUT INSERTED.IdProveedor
            VALUES (?, ?, ?, ?, 'Activo')
            """,
            (
                nombre,
                (data.get("telefono") or "").strip() or None,
                (data.get("correo") or "").strip() or None,
                (data.get("direccion") or "").strip() or None,
            ),
        )


def create_purchase(data: dict[str, Any], usuario_id: int) -> dict[str, Any]:
    proveedor_id = to_int(data.get("id_proveedor"), "proveedor")
    num_doc = (data.get("num_doc") or "").strip()
    fecha = parse_date(data.get("fecha_compra") or dt.date.today(), "fecha de compra")
    items = data.get("items") or []
    if not num_doc:
        raise BusinessError("El número de documento de la compra es obligatorio.")
    if not items:
        raise BusinessError("Agrega al menos un producto a la compra.")
    if not fetch_one("SELECT 1 AS x FROM PROVEEDOR WHERE IdProveedor = ?", (proveedor_id,)):
        raise BusinessError("Proveedor no encontrado.", 404)

    total = Decimal("0.00")
    with transaction() as cur:
        compra_id = insert_returning(
            cur,
            """
            INSERT INTO COMPRA (FechaCompra, NumDoc, Estado, IdProveedor, IdUsuario)
            OUTPUT INSERTED.IdCompra
            VALUES (?, ?, 'Completada', ?, ?)
            """,
            (fecha, num_doc, proveedor_id, usuario_id),
        )

        for index, item in enumerate(items, start=1):
            producto = cur.execute(
                "SELECT IdProducto, Nombre, ControlVenc, IdConcepto FROM PRODUCTO WHERE IdProducto = ?",
                (to_int(item.get("id_producto"), "producto"),),
            ).fetchone()
            if not producto:
                raise BusinessError(f"El producto de la línea {index} no existe.")

            cantidad = to_int(item.get("cantidad"), "cantidad")
            costo = to_decimal(item.get("costo_unit"), "costo unitario")
            if cantidad <= 0 or costo < 0:
                raise BusinessError(f"La línea {index} tiene cantidad o costo inválido.")
            total += costo * cantidad

            cur.execute(
                """
                INSERT INTO DETALLE_COMPRA (Cantidad, CostoUnit, IdCompra, IdProducto)
                VALUES (?, ?, ?, ?)
                """,
                (cantidad, costo, compra_id, producto.IdProducto),
            )

            codigo_lote = (item.get("codigo_lote") or f"COMP-{compra_id}-{producto.IdProducto}").strip()
            fecha_venc = parse_date(
                item.get("fecha_venc") or (dt.date.today() + dt.timedelta(days=365 * 5)),
                "fecha de vencimiento",
            )

            row = cur.execute(
                "SELECT IdLote FROM LOTE WHERE IdProducto = ? AND CodigoLote = ?",
                (producto.IdProducto, codigo_lote),
            ).fetchone()
            if row:
                lote_id = int(row[0])
            else:
                estado = "Vencido" if fecha_venc < dt.date.today() else "Disponible"
                lote_id = insert_returning(
                    cur,
                    """
                    INSERT INTO LOTE (CodigoLote, FechaVenc, FechaIng, Estado, IdProducto)
                    OUTPUT INSERTED.IdLote
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (codigo_lote, fecha_venc, fecha, estado, producto.IdProducto),
                )

            cur.execute(
                """
                INSERT INTO MOVIMIENTO_INVENTARIO (TipoMov, Cantidad, Motivo, IdLote, IdUsuario)
                VALUES ('Entrada', ?, ?, ?, ?)
                """,
                (cantidad, f"Compra {num_doc}", lote_id, usuario_id),
            )

            # Si el producto aún no tiene concepto de venta, se puede crear desde la compra
            precio_venta = item.get("precio_venta")
            if precio_venta not in (None, "") and not producto.IdConcepto:
                concepto_id = insert_returning(
                    cur,
                    """
                    INSERT INTO CONCEPTO_FACTURABLE (TipoConcepto, Nombre, Descripcion, Precio, Estado)
                    OUTPUT INSERTED.IdConcepto
                    VALUES ('Producto', ?, NULL, ?, 'Activo')
                    """,
                    (producto.Nombre, to_decimal(precio_venta, "precio de venta")),
                )
                cur.execute(
                    "UPDATE PRODUCTO SET IdConcepto = ? WHERE IdProducto = ?",
                    (concepto_id, producto.IdProducto),
                )

        _refresh_lot_states(cur)

    return {"id_compra": compra_id, "total": float(total)}


def list_purchases(limit: int = 100) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT TOP (CAST(? AS INT)) C.IdCompra, C.FechaCompra, C.NumDoc, C.Estado,
               P.Nombre AS Proveedor, U.Nombre + ' ' + U.Apellido AS Usuario,
               (SELECT SUM(D.Cantidad * D.CostoUnit) FROM DETALLE_COMPRA D WHERE D.IdCompra = C.IdCompra) AS Total,
               (SELECT COUNT(*) FROM DETALLE_COMPRA D WHERE D.IdCompra = C.IdCompra) AS Lineas
        FROM COMPRA C
        INNER JOIN PROVEEDOR P ON P.IdProveedor = C.IdProveedor
        INNER JOIN USUARIO U ON U.IdUsuario = C.IdUsuario
        ORDER BY C.FechaCompra DESC, C.IdCompra DESC
        """,
        (max(1, min(limit, 500)),),
    )


def get_purchase(compra_id: int) -> dict[str, Any]:
    compra = fetch_one(
        """
        SELECT C.*, P.Nombre AS Proveedor
        FROM COMPRA C INNER JOIN PROVEEDOR P ON P.IdProveedor = C.IdProveedor
        WHERE C.IdCompra = ?
        """,
        (compra_id,),
    )
    if not compra:
        raise BusinessError("Compra no encontrada.", 404)
    compra["detalle"] = fetch_all(
        """
        SELECT D.IdDetCompra, D.Cantidad, D.CostoUnit, D.IdProducto, P.Nombre AS Producto
        FROM DETALLE_COMPRA D INNER JOIN PRODUCTO P ON P.IdProducto = D.IdProducto
        WHERE D.IdCompra = ?
        """,
        (compra_id,),
    )
    return compra


def inventory_alerts() -> dict[str, list[dict[str, Any]]]:
    low_stock = fetch_all(
        """
        SELECT IdProducto, Nombre, Stock, StockMin, UnidadMedida
        FROM VW_STOCK_PRODUCTO
        WHERE Stock <= StockMin
        ORDER BY Stock, Nombre
        """
    )
    expiring = fetch_all(
        """
        SELECT IdLote, CodigoLote, Producto, FechaVenc, StockLote,
               DATEDIFF(day, CAST(GETDATE() AS DATE), FechaVenc) AS Dias
        FROM VW_LOTE_STOCK
        WHERE StockLote > 0 AND FechaVenc >= CAST(GETDATE() AS DATE)
          AND FechaVenc <= DATEADD(day, 30, CAST(GETDATE() AS DATE))
        ORDER BY FechaVenc
        """
    )
    expired = fetch_all(
        """
        SELECT IdLote, CodigoLote, Producto, FechaVenc, StockLote
        FROM VW_LOTE_STOCK
        WHERE StockLote > 0 AND FechaVenc < CAST(GETDATE() AS DATE)
        ORDER BY FechaVenc
        """
    )
    without_concept = fetch_all(
        "SELECT IdProducto, Nombre FROM PRODUCTO WHERE IdConcepto IS NULL ORDER BY Nombre"
    )
    return {
        "stock_bajo": low_stock,
        "por_vencer": expiring,
        "vencidos": expired,
        "sin_concepto": without_concept,
    }
