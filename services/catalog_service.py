"""Catálogo: conceptos facturables, productos, servicios y categorías."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from db import BusinessError, fetch_all, fetch_one, insert_returning, transaction
from utils import to_decimal, to_int


def list_categories() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT C.IdCategoria, C.Nombre, C.Descripcion,
               (SELECT COUNT(*) FROM PRODUCTO P WHERE P.IdCategoria = C.IdCategoria) AS Productos
        FROM CATEGORIA C
        ORDER BY C.Nombre
        """
    )


def create_category(data: dict[str, Any]) -> int:
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        raise BusinessError("El nombre de la categoría es obligatorio.")
    if fetch_one("SELECT 1 AS x FROM CATEGORIA WHERE Nombre = ?", (nombre,)):
        raise BusinessError("Ya existe una categoría con ese nombre.")
    with transaction() as cur:
        return insert_returning(
            cur,
            "INSERT INTO CATEGORIA (Nombre, Descripcion) OUTPUT INSERTED.IdCategoria VALUES (?, ?)",
            (nombre, (data.get("descripcion") or "").strip() or None),
        )


def list_concepts(
    search: str | None = None,
    tipo: str | None = None,
    only_active: bool = True,
    with_stock: bool = True,
    categoria_id: int | None = None,
) -> list[dict[str, Any]]:
    conditions = ["1 = 1"]
    params: list[Any] = []
    if search:
        conditions.append("(C.Nombre LIKE ? OR C.Descripcion LIKE ?)")
        like = f"%{search.strip()}%"
        params.extend([like, like])
    if tipo in ("Producto", "Servicio"):
        conditions.append("C.TipoConcepto = ?")
        params.append(tipo)
    if categoria_id:
        conditions.append("P.IdCategoria = ?")
        params.append(categoria_id)
    if only_active:
        conditions.append("C.Estado = 'Activo'")

    stock_join = (
        "LEFT JOIN PRODUCTO P ON P.IdConcepto = C.IdConcepto "
        "LEFT JOIN VW_STOCK_PRODUCTO S ON S.IdProducto = P.IdProducto"
        if with_stock
        else "LEFT JOIN PRODUCTO P ON P.IdConcepto = C.IdConcepto "
    )
    stock_cols = ", P.IdProducto, P.UnidadMedida, P.ControlVenc, P.StockMin, ISNULL(S.Stock, 0) AS Stock" if with_stock else ", P.IdProducto"
    return fetch_all(
        f"""
        SELECT C.IdConcepto, C.TipoConcepto, C.Nombre, C.Descripcion, C.Precio, C.Estado
               {stock_cols},
               CAT.Nombre AS Categoria,
               SE.IdServicio, SE.DuracionMin
        FROM CONCEPTO_FACTURABLE C
        {stock_join}
        LEFT JOIN CATEGORIA CAT ON CAT.IdCategoria = P.IdCategoria
        LEFT JOIN SERVICIO_CLINICO SE ON SE.IdConcepto = C.IdConcepto
        WHERE {' AND '.join(conditions)}
        ORDER BY C.TipoConcepto, C.Nombre
        """,
        params,
    )


def get_concept(concepto_id: int) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT C.*, P.IdProducto, P.UnidadMedida, P.ControlVenc, P.StockMin, P.IdCategoria,
               ISNULL(S.Stock, 0) AS Stock, SE.IdServicio, SE.DuracionMin, SE.Ind
        FROM CONCEPTO_FACTURABLE C
        LEFT JOIN PRODUCTO P ON P.IdConcepto = C.IdConcepto
        LEFT JOIN VW_STOCK_PRODUCTO S ON S.IdProducto = P.IdProducto
        LEFT JOIN SERVICIO_CLINICO SE ON SE.IdConcepto = C.IdConcepto
        WHERE C.IdConcepto = ?
        """,
        (concepto_id,),
    )
    if not row:
        raise BusinessError("Concepto no encontrado.", 404)
    return row


def create_concept(data: dict[str, Any]) -> int:
    tipo = (data.get("tipo_concepto") or data.get("tipo") or "").strip().title()
    if tipo not in ("Producto", "Servicio"):
        raise BusinessError("El tipo de concepto debe ser Producto o Servicio.")
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        raise BusinessError("El nombre del concepto es obligatorio.")
    precio = to_decimal(data.get("precio"), "precio")
    if precio < 0:
        raise BusinessError("El precio no puede ser negativo.")

    with transaction() as cur:
        return insert_returning(
            cur,
            """
            INSERT INTO CONCEPTO_FACTURABLE (TipoConcepto, Nombre, Descripcion, Precio, Estado)
            OUTPUT INSERTED.IdConcepto
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                tipo,
                nombre,
                (data.get("descripcion") or "").strip() or None,
                precio,
                "Activo" if data.get("estado", "Activo") == "Activo" else "Inactivo",
            ),
        )


def update_concept(concepto_id: int, data: dict[str, Any]) -> None:
    current = get_concept(concepto_id)
    nombre = (data.get("nombre") or current["Nombre"]).strip()
    descripcion = data.get("descripcion", current["Descripcion"])
    precio = to_decimal(data.get("precio", current["Precio"]), "precio")
    estado = data.get("estado", current["Estado"])
    if estado not in ("Activo", "Inactivo"):
        raise BusinessError("Estado de concepto inválido.")
    with transaction() as cur:
        cur.execute(
            """
            UPDATE CONCEPTO_FACTURABLE
            SET Nombre = ?, Descripcion = ?, Precio = ?, Estado = ?
            WHERE IdConcepto = ?
            """,
            (nombre, descripcion or None, precio, estado, concepto_id),
        )


def list_products() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT S.*, C.Descripcion, CON.Nombre AS Concepto, CON.Precio AS PrecioVenta
        FROM VW_STOCK_PRODUCTO S
        LEFT JOIN CATEGORIA C ON C.IdCategoria = S.IdCategoria
        LEFT JOIN CONCEPTO_FACTURABLE CON ON CON.IdConcepto = S.IdConcepto
        ORDER BY S.Nombre
        """
    )


def create_product(data: dict[str, Any]) -> dict[str, Any]:
    nombre = (data.get("nombre") or "").strip()
    unidad = (data.get("unidad_medida") or "Unidad").strip()
    id_categoria = to_int(data.get("id_categoria"), "categoría")
    stock_min = to_int(data.get("stock_min"), "stock mínimo", default=0)
    control_venc = bool(data.get("control_venc", True))
    precio = data.get("precio")
    descripcion = (data.get("descripcion") or "").strip() or None
    id_concepto = data.get("id_concepto")

    if not nombre:
        raise BusinessError("El nombre del producto es obligatorio.")
    if not fetch_one("SELECT 1 AS x FROM CATEGORIA WHERE IdCategoria = ?", (id_categoria,)):
        raise BusinessError("La categoría seleccionada no existe.")

    with transaction() as cur:
        if id_concepto:
            id_concepto = to_int(id_concepto, "concepto")
            if not fetch_one("SELECT 1 AS x FROM CONCEPTO_FACTURABLE WHERE IdConcepto = ?", (id_concepto,)):
                raise BusinessError("El concepto facturable no existe.")
        else:
            precio_dec = to_decimal(precio, "precio de venta", default=Decimal("0.00"))
            id_concepto = insert_returning(
                cur,
                """
                INSERT INTO CONCEPTO_FACTURABLE (TipoConcepto, Nombre, Descripcion, Precio, Estado)
                OUTPUT INSERTED.IdConcepto
                VALUES ('Producto', ?, ?, ?, 'Activo')
                """,
                (nombre, descripcion, precio_dec),
            )

        producto_id = insert_returning(
            cur,
            """
            INSERT INTO PRODUCTO (Nombre, UnidadMedida, ControlVenc, StockMin, IdCategoria, IdConcepto)
            OUTPUT INSERTED.IdProducto
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (nombre, unidad, control_venc, stock_min, id_categoria, id_concepto),
        )
    return {"id_producto": producto_id, "id_concepto": id_concepto}


def update_product(producto_id: int, data: dict[str, Any]) -> None:
    current = fetch_one("SELECT * FROM PRODUCTO WHERE IdProducto = ?", (producto_id,))
    if not current:
        raise BusinessError("Producto no encontrado.", 404)
    with transaction() as cur:
        cur.execute(
            """
            UPDATE PRODUCTO
            SET Nombre = ?, UnidadMedida = ?, ControlVenc = ?, StockMin = ?, IdCategoria = ?
            WHERE IdProducto = ?
            """,
            (
                (data.get("nombre") or current["Nombre"]).strip(),
                (data.get("unidad_medida") or current["UnidadMedida"]).strip(),
                bool(data.get("control_venc", current["ControlVenc"])),
                to_int(data.get("stock_min", current["StockMin"]), "stock mínimo"),
                to_int(data.get("id_categoria", current["IdCategoria"]), "categoría"),
                producto_id,
            ),
        )


def create_service(data: dict[str, Any]) -> dict[str, Any]:
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        raise BusinessError("El nombre del servicio es obligatorio.")
    precio = to_decimal(data.get("precio"), "precio")
    duracion = data.get("duracion_min")
    ind = (data.get("indicaciones") or "").strip() or None
    with transaction() as cur:
        concepto_id = insert_returning(
            cur,
            """
            INSERT INTO CONCEPTO_FACTURABLE (TipoConcepto, Nombre, Descripcion, Precio, Estado)
            OUTPUT INSERTED.IdConcepto
            VALUES ('Servicio', ?, ?, ?, ?)
            """,
            (
                nombre,
                (data.get("descripcion") or "").strip() or None,
                precio,
                "Activo" if data.get("estado", "Activo") == "Activo" else "Inactivo",
            ),
        )
        servicio_id = insert_returning(
            cur,
            """
            INSERT INTO SERVICIO_CLINICO (DuracionMin, Ind, IdConcepto)
            OUTPUT INSERTED.IdServicio
            VALUES (?, ?, ?)
            """,
            (to_int(duracion, "duración", default=None) if duracion else None, ind, concepto_id),
        )
    return {"id_servicio": servicio_id, "id_concepto": concepto_id}


def list_services() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT SE.IdServicio, SE.DuracionMin, SE.Ind, C.IdConcepto, C.Nombre,
               C.Descripcion, C.Precio, C.Estado
        FROM SERVICIO_CLINICO SE
        INNER JOIN CONCEPTO_FACTURABLE C ON C.IdConcepto = SE.IdConcepto
        ORDER BY C.Nombre
        """
    )
