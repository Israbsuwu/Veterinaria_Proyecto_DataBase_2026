"""Tablero de control y métricas del ERP."""
from __future__ import annotations

import datetime as dt
from typing import Any

from db import fetch_all, fetch_one, fetch_scalar
from services import billing_service, inventory_service


def _sales_total(where: str = "", params: tuple = ()) -> dict[str, Any]:
    row = fetch_one(
        f"""
        SELECT COUNT(DISTINCT V.IdVenta) AS Ventas,
               ISNULL(SUM(D.Cantidad * D.PrecioUnit), 0) AS Total
        FROM VENTA V
        INNER JOIN DETALLE_VENTA D ON D.IdVenta = V.IdVenta
        WHERE V.Estado = 'Pagada' {where}
        """,
        params,
    )
    return row or {"Ventas": 0, "Total": 0}


def get_dashboard(usuario_id: int) -> dict[str, Any]:
    hoy = _sales_total("AND CAST(V.FechaVenta AS DATE) = CAST(GETDATE() AS DATE)")
    mes = _sales_total(
        "AND V.FechaVenta >= DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)"
    )
    web_mes = _sales_total(
        "AND V.Origen = 'Web' AND V.FechaVenta >= DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)"
    )
    pos_mes = _sales_total(
        "AND V.Origen = 'POS' AND V.FechaVenta >= DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)"
    )

    sesion = billing_service.get_open_session(usuario_id)
    resumen_sesion = billing_service.session_summary(sesion["IdSesion"]) if sesion else None

    return {
        "ventas_hoy": hoy,
        "ventas_mes": mes,
        "ventas_web_mes": web_mes,
        "ventas_pos_mes": pos_mes,
        "clientes": fetch_scalar("SELECT COUNT(*) FROM CLIENTE", default=0),
        "pacientes": fetch_scalar("SELECT COUNT(*) FROM MASCOTA", default=0),
        "usuarios_web": fetch_scalar(
            "SELECT COUNT(*) FROM USUARIO WHERE IdRol = (SELECT IdRol FROM ROL WHERE NombreRol = 'Cliente Web')",
            default=0,
        ),
        "reservas_hoy": fetch_scalar(
            """
            SELECT COUNT(*) FROM RESERVA
            WHERE CAST(FechaIni AS DATE) = CAST(GETDATE() AS DATE) AND Estado <> 'Cancelada'
            """,
            default=0,
        ),
        "reservas_pendientes": fetch_scalar(
            "SELECT COUNT(*) FROM RESERVA WHERE Estado = 'Pendiente'", default=0
        ),
        "atenciones_espera": fetch_scalar(
            "SELECT COUNT(*) FROM ATENCION WHERE Estado = 'En Espera'", default=0
        ),
        "atenciones_consulta": fetch_scalar(
            "SELECT COUNT(*) FROM ATENCION WHERE Estado = 'En Consulta'", default=0
        ),
        "alertas_inventario": inventory_service.inventory_alerts(),
        "sesion_caja": resumen_sesion,
        "ventas_recientes": billing_service.list_sales(limit=6),
        "proximas_citas": fetch_all(
            """
            SELECT TOP 8 R.IdReserva, R.FechaIni, R.Motivo, R.Estado, R.Canal,
                   C.Nombre + ' ' + C.Apellido AS Cliente,
                   M.Nombre AS Mascota,
                   U.Nombre + ' ' + U.Apellido AS Veterinario
            FROM RESERVA R
            INNER JOIN CLIENTE C ON C.IdCliente = R.IdCliente
            LEFT JOIN MASCOTA M ON M.IdMascota = R.IdMascota
            LEFT JOIN VETERINARIO V ON V.IdVeterinario = R.IdVeterinario
            LEFT JOIN USUARIO U ON U.IdUsuario = V.IdUsuario
            WHERE R.FechaIni >= CAST(GETDATE() AS DATE)
              AND R.Estado IN ('Pendiente', 'Confirmada')
            ORDER BY R.FechaIni ASC
            """
        ),
        "top_productos": fetch_all(
            """
            SELECT TOP 5 C.Nombre, C.TipoConcepto,
                   SUM(D.Cantidad) AS Unidades,
                   SUM(D.Cantidad * D.PrecioUnit) AS Total
            FROM DETALLE_VENTA D
            INNER JOIN VENTA V ON V.IdVenta = D.IdVenta
            INNER JOIN CONCEPTO_FACTURABLE C ON C.IdConcepto = D.IdConcepto
            WHERE V.Estado = 'Pagada'
              AND V.FechaVenta >= DATEADD(day, -30, GETDATE())
            GROUP BY C.Nombre, C.TipoConcepto
            ORDER BY Total DESC
            """
        ),
        "serie_dias": _sales_series(),
        "ultimos_movimientos": inventory_service.list_movements(limit=6),
    }


def _sales_series() -> list[dict[str, Any]]:
    rows = fetch_all(
        """
        SELECT CAST(V.FechaVenta AS DATE) AS Dia,
               ISNULL(SUM(D.Cantidad * D.PrecioUnit), 0) AS Total
        FROM VENTA V
        INNER JOIN DETALLE_VENTA D ON D.IdVenta = V.IdVenta
        WHERE V.Estado = 'Pagada'
          AND V.FechaVenta >= DATEADD(day, -6, CAST(GETDATE() AS DATE))
        GROUP BY CAST(V.FechaVenta AS DATE)
        ORDER BY Dia
        """
    )
    by_day = {row["Dia"]: float(row["Total"] or 0) for row in rows}
    today = dt.date.today()
    series = []
    for offset in range(6, -1, -1):
        day = today - dt.timedelta(days=offset)
        series.append(
            {
                "dia": day.isoformat(),
                "etiqueta": day.strftime("%d/%m"),
                "total": by_day.get(day, 0.0),
            }
        )
    return series
