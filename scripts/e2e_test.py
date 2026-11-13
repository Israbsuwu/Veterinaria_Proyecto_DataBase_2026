"""Prueba E2E de los flujos de tienda, clínica, inventario y caja.

Crea datos marcados con SMOKE y los elimina al finalizar (incluso si falla).
"""
from __future__ import annotations

import datetime as dt
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from db import fetch_all, fetch_one, transaction  # noqa: E402

app = create_app()
app.testing = True

STAMP = dt.datetime.now().strftime("%Y%m%d%H%M%S")
MARK = f"SMOKE{STAMP}"
CEDULA = f"SMK-{STAMP}"
EMAIL = f"smoke{STAMP}@test.local"
SUPPLIER = f"Proveedor {MARK}"
PURCHASE_DOC = f"COMP-{MARK}"
LOT_CODE = f"LOT-{MARK}"
PASSWORD = "123456"

state: dict = {"facturas": []}


def show(label, value):
    print(f"  · {label}: {value}")


def data_of(response, label):
    payload = response.get_json()
    if response.status_code >= 400 or not payload or not payload.get("success"):
        raise AssertionError(f"{label} falló ({response.status_code}): {payload}")
    return payload.get("data")


def api(client, method, url, label, **kwargs):
    response = getattr(client, method)(url, **kwargs)
    return data_of(response, label)


def login(client, url, correo, contrasena):
    response = client.post(url, data={"correo": correo, "contrasena": contrasena})
    assert response.status_code == 302, f"login {correo} -> {response.status_code}"
    return response


def cleanup() -> None:
    print("\n== Limpieza ==")
    facturas = state.get("facturas", [])
    consulta_id = state.get("consulta_id")
    with app.app_context():
        cliente = fetch_one("SELECT IdCliente, IdUsuario FROM CLIENTE WHERE Cedula = ?", (CEDULA,))
        cliente_id = cliente["IdCliente"] if cliente else None
        usuario_id = cliente["IdUsuario"] if cliente else None
        proveedor = fetch_one("SELECT IdProveedor FROM PROVEEDOR WHERE Nombre = ?", (SUPPLIER,))
        proveedor_id = proveedor["IdProveedor"] if proveedor else None
        compra = fetch_one("SELECT IdCompra FROM COMPRA WHERE NumDoc = ?", (PURCHASE_DOC,))
        compra_id = compra["IdCompra"] if compra else None
        lotes = fetch_all("SELECT IdLote FROM LOTE WHERE CodigoLote = ?", (LOT_CODE,))
        lote_ids = [row["IdLote"] for row in lotes]

        with transaction() as cur:
            def run(sql, params=()):
                cur.execute(sql, params)

            # Notificaciones del cliente de prueba y de sus registros clínicos
            if cliente_id:
                run("DELETE FROM NOTIFICACION WHERE IdCliente = ?", (cliente_id,))
            if consulta_id:
                run(
                    """
                    DELETE FROM NOTIFICACION
                    WHERE IdRegPrev IN (
                        SELECT IdRegPrev FROM REGISTRO_PREVENTIVO WHERE IdConsulta = ?
                    ) OR IdDetReceta IN (
                        SELECT DR.IdDetReceta FROM DETALLE_RECETA DR
                        INNER JOIN RECETA_MEDICA R ON R.IdReceta = DR.IdReceta
                        WHERE R.IdConsulta = ?
                    )
                    """,
                    (consulta_id, consulta_id),
                )
                run(
                    """
                    DELETE DR FROM DETALLE_RECETA DR
                    INNER JOIN RECETA_MEDICA R ON R.IdReceta = DR.IdReceta
                    WHERE R.IdConsulta = ?
                    """,
                    (consulta_id,),
                )
                run(
                    """
                    DELETE R FROM RECETA_MEDICA R
                    WHERE R.IdConsulta = ?
                    """,
                    (consulta_id,),
                )
                run("DELETE FROM REGISTRO_PREVENTIVO WHERE IdConsulta = ?", (consulta_id,))
                run("DELETE FROM CONSULTA_MEDICA WHERE IdConsulta = ?", (consulta_id,))

            if cliente_id:
                run(
                    """
                    DELETE A FROM ATENCION A
                    INNER JOIN MASCOTA M ON M.IdMascota = A.IdMascota
                    WHERE M.IdCliente = ?
                    """,
                    (cliente_id,),
                )
                run(
                    """
                    DELETE N FROM NOTIFICACION N
                    INNER JOIN RESERVA R ON R.IdReserva = N.IdReserva
                    WHERE R.IdCliente = ?
                    """,
                    (cliente_id,),
                )
                run("DELETE FROM RESERVA WHERE IdCliente = ?", (cliente_id,))
                run(
                    """
                    DELETE E FROM EXPEDIENTE_CLINICO E
                    INNER JOIN MASCOTA M ON M.IdMascota = E.IdMascota
                    WHERE M.IdCliente = ?
                    """,
                    (cliente_id,),
                )
                run(
                    """
                    DELETE M FROM MASCOTA M WHERE M.IdCliente = ?
                    """,
                    (cliente_id,),
                )

            # Movimientos de inventario generados por la prueba
            for factura in facturas:
                run(
                    "DELETE FROM MOVIMIENTO_INVENTARIO WHERE Motivo LIKE ? OR Motivo LIKE ? OR Motivo LIKE ?",
                    (f"%{factura}%", f"%{factura}%", f"%{factura}%"),
                )
            if consulta_id:
                run("DELETE FROM MOVIMIENTO_INVENTARIO WHERE Motivo LIKE ?", (f"%consulta #{consulta_id}%",))
            for lote_id in lote_ids:
                run("DELETE FROM MOVIMIENTO_INVENTARIO WHERE IdLote = ?", (lote_id,))
            run("DELETE FROM MOVIMIENTO_INVENTARIO WHERE Motivo = ?", (f"Compra {PURCHASE_DOC}",))

            if cliente_id:
                run(
                    """
                    DELETE P FROM PAGO P INNER JOIN VENTA V ON V.IdVenta = P.IdVenta
                    WHERE V.IdCliente = ?
                    """,
                    (cliente_id,),
                )
                run(
                    """
                    DELETE D FROM DETALLE_VENTA D INNER JOIN VENTA V ON V.IdVenta = D.IdVenta
                    WHERE V.IdCliente = ?
                    """,
                    (cliente_id,),
                )
                run("DELETE FROM VENTA WHERE IdCliente = ?", (cliente_id,))

            if compra_id:
                run("DELETE FROM DETALLE_COMPRA WHERE IdCompra = ?", (compra_id,))
                run("DELETE FROM COMPRA WHERE IdCompra = ?", (compra_id,))
            for lote_id in lote_ids:
                run("DELETE FROM LOTE WHERE IdLote = ?", (lote_id,))
            if proveedor_id:
                run("DELETE FROM PROVEEDOR WHERE IdProveedor = ?", (proveedor_id,))

            sesion_id = state.get("sesion_id")
            if sesion_id:
                run("DELETE FROM SESION_CAJA WHERE IdSesion = ?", (sesion_id,))

            if cliente_id:
                run("UPDATE CLIENTE SET IdUsuario = NULL WHERE IdCliente = ?", (cliente_id,))
                run("DELETE FROM CLIENTE WHERE IdCliente = ?", (cliente_id,))
            if usuario_id:
                run("DELETE FROM USUARIO WHERE IdUsuario = ?", (usuario_id,))
        print("  · datos SMOKE eliminados")


def main() -> None:
    print("== Datos base ==")
    with app.app_context():
        producto = fetch_one(
            "SELECT TOP 1 IdProducto, Nombre, IdConcepto FROM PRODUCTO WHERE IdConcepto IS NOT NULL ORDER BY IdProducto"
        )
        servicio = fetch_one(
            "SELECT TOP 1 IdConcepto, Nombre FROM CONCEPTO_FACTURABLE WHERE TipoConcepto = 'Servicio' AND Estado = 'Activo' ORDER BY IdConcepto"
        )
        lote = fetch_one(
            """
            SELECT TOP 1 L.IdLote FROM LOTE L
            WHERE L.IdProducto = ? AND L.Estado = 'Disponible' AND L.FechaVenc >= CAST(GETDATE() AS DATE)
            ORDER BY L.FechaVenc
            """,
            (producto["IdProducto"],),
        )
    assert producto and servicio and lote, "Faltan datos base (producto, servicio o lote)."
    show("producto", dict(producto))
    show("servicio", dict(servicio))
    show("lote", lote["IdLote"])

    with app.test_client() as shop:
        print("\n== Registro de cliente y mascota ==")
        response = shop.post(
            "/tienda/registro",
            data={
                "nombre": "Cliente",
                "apellido": MARK,
                "cedula": CEDULA,
                "correo": EMAIL,
                "telefono": "8888-0000",
                "direccion": "Managua",
                "contrasena": PASSWORD,
            },
        )
        assert response.status_code == 302, response.get_data(as_text=True)[:500]
        perfil = api(shop, "get", "/api/tienda/perfil", "perfil")
        state["cliente_id"] = perfil["cliente"]["IdCliente"]
        show("cliente_id", state["cliente_id"])
        api(
            shop,
            "patch",
            "/api/tienda/perfil",
            "actualizar perfil",
            json={"acepta_notif": "0", "telefono": "8888-1111"},
        )
        perfil_actualizado = api(shop, "get", "/api/tienda/perfil", "perfil actualizado")
        assert int(perfil_actualizado["cliente"]["AceptaNotif"]) == 0, "No se desactivó AceptaNotif."
        assert perfil_actualizado["cliente"]["Telefono"] == "8888-1111"
        show("perfil", "acepta_notif=0, teléfono actualizado")

        pet_id = api(
            shop,
            "post",
            "/api/tienda/mis-mascotas",
            "crear mascota",
            json={"nombre": f"Mascota {MARK}", "especie": "Perro", "raza": "Mestizo", "sexo": "Macho", "fecha_nac": "2021-05-01"},
        )["id_mascota"]
        state["mascota_id"] = pet_id
        show("mascota_id", pet_id)

        print("\n== Reserva web ==")
        reserva = api(
            shop,
            "post",
            "/api/tienda/reservas",
            "crear reserva",
            json={
                "id_mascota": pet_id,
                "fecha_ini": "2026-12-15 10:00",
                "motivo": "Consulta general",
                "obs": MARK,
            },
        )
        state["reserva_id"] = reserva["id_reserva"]
        show("reserva_id", reserva["id_reserva"])
        reservas = api(shop, "get", "/api/tienda/mis-reservas", "mis reservas")
        assert any(r["IdReserva"] == state["reserva_id"] for r in reservas)

    with app.test_client() as admin:
        login(admin, "/login", "admin@pepe.com", PASSWORD)

        print("\n== Check-in y consulta con preventivo ==")
        atencion = api(
            admin,
            "post",
            f"/api/reservas/{state['reserva_id']}/checkin",
            "check-in",
            json={"prioridad": "Media", "tipo_atencion": "Rutina"},
        )
        atencion_id = atencion["id_atencion"]
        show("atencion_id", atencion_id)

        stock_antes = next(
            p for p in api(admin, "get", "/api/inventario/stock", "stock antes") if p["IdProducto"] == producto["IdProducto"]
        )["Stock"]
        result = api(
            admin,
            "post",
            "/api/consultas",
            "consulta",
            json={
                "id_atencion": atencion_id,
                "peso": 12.5,
                "motivo": "Control",
                "diagnostico": f"Diagnóstico {MARK}",
                "tratamiento": f"Tratamiento {MARK}",
                "preventivos": [
                    {
                        "tipo_proc": "Vacuna",
                        "nombre_prod": "Vacuna Antirrábica",
                        "id_producto": producto["IdProducto"],
                        "id_lote": lote["IdLote"],
                        "cantidad": 1,
                        "fecha_aplic": dt.date.today().isoformat(),
                        "prox_aplic": (dt.date.today() + dt.timedelta(days=365)).isoformat(),
                        "dosis": "1 dosis",
                    }
                ],
            },
        )
        state["consulta_id"] = result["id_consulta"]
        show("consulta_id", result["id_consulta"])
        stock_despues = next(
            p for p in api(admin, "get", "/api/inventario/stock", "stock después") if p["IdProducto"] == producto["IdProducto"]
        )["Stock"]
        show("stock", f"{stock_antes} -> {stock_despues}")
        assert int(stock_despues) == int(stock_antes) - 1, "El preventivo no descontó inventario."

        print("\n== Caja y venta POS ==")
        api(admin, "post", "/api/caja/abrir", "abrir caja", json={"monto_inicial": 500})
        caja = api(admin, "get", "/api/caja/actual", "caja actual")
        state["sesion_id"] = caja["sesion"]["IdSesion"]
        show("sesion_id", state["sesion_id"])

        venta = api(
            admin,
            "post",
            "/api/ventas",
            "venta POS",
            json={
                "id_cliente": state["cliente_id"],
                "metodo": "Efectivo",
                "monto_recibido": 1000,
                "items": [
                    {"id_concepto": producto["IdConcepto"], "cantidad": 1},
                    {"id_concepto": servicio["IdConcepto"], "cantidad": 1},
                ],
            },
        )
        state["facturas"].append(venta["factura"])
        show("venta POS", venta)
        assert venta["vuelto"] >= 0
        detalle = api(admin, "get", f"/api/ventas/{venta['id_venta']}", "detalle venta")
        assert len(detalle["detalle"]) == 2
        assert detalle["pagos"][0]["IdSesion"] == state["sesion_id"]

        anulada = api(admin, "post", f"/api/ventas/{venta['id_venta']}/anular", "anular POS")
        show("anulación", anulada)
        stock_anulada = next(
            p for p in api(admin, "get", "/api/inventario/stock", "stock anulada") if p["IdProducto"] == producto["IdProducto"]
        )["Stock"]
        assert int(stock_anulada) == int(stock_despues), "La anulación no restauró el stock."

        cierre = api(admin, "post", "/api/caja/cerrar", "cerrar caja", json={})
        show("cierre", {"estado": cierre["Estado"], "diferencia": cierre["diferencia"]})
        assert cierre["Estado"] == "Cerrada"

        print("\n== Compra e inventario ==")
        proveedor = api(admin, "post", "/api/proveedores", "proveedor", json={"nombre": SUPPLIER, "telefono": "2222-0000"})
        stock_purchase_before = next(
            p for p in api(admin, "get", "/api/inventario/stock", "stock compra antes") if p["IdProducto"] == producto["IdProducto"]
        )["Stock"]
        compra = api(
            admin,
            "post",
            "/api/compras",
            "compra",
            json={
                "id_proveedor": proveedor["id_proveedor"],
                "num_doc": PURCHASE_DOC,
                "fecha_compra": dt.date.today().isoformat(),
                "items": [
                    {
                        "id_producto": producto["IdProducto"],
                        "cantidad": 5,
                        "costo_unit": 10,
                        "codigo_lote": LOT_CODE,
                        "fecha_venc": "2028-12-31",
                    }
                ],
            },
        )
        show("compra", compra)
        stock_purchase_after = next(
            p for p in api(admin, "get", "/api/inventario/stock", "stock compra después") if p["IdProducto"] == producto["IdProducto"]
        )["Stock"]
        show("stock compra", f"{stock_purchase_before} -> {stock_purchase_after}")
        assert int(stock_purchase_after) == int(stock_purchase_before) + 5, "La compra no incrementó el stock."

    with app.test_client() as shop2:
        print("\n== Checkout web ==")
        login(shop2, "/tienda/login", EMAIL, PASSWORD)
        api(shop2, "post", "/api/tienda/carrito", "agregar al carrito", json={"id_concepto": producto["IdConcepto"], "cantidad": 1})
        carrito = api(shop2, "get", "/api/tienda/carrito", "carrito")
        assert carrito["lineas"], "Carrito vacío"
        checkout = api(
            shop2,
            "post",
            "/api/tienda/checkout",
            "checkout web",
            json={"metodo": "Tarjeta", "referencia": f"REF-{MARK}"},
        )
        state["facturas"].append(checkout["factura"])
        state["web_venta_id"] = checkout["id_venta"]
        show("checkout", checkout)
        assert checkout["origen"] == "Web" and checkout["sesion_id"] is None

        response = shop2.get(f"/tienda/pedido/{checkout['id_venta']}")
        assert response.status_code == 200, response.get_data(as_text=True)[:500]
        assert checkout["factura"] in response.get_data(as_text=True)
        print("  · página de pedido renderizada")

    with app.test_client() as admin2:
        login(admin2, "/login", "admin@pepe.com", PASSWORD)
        print("\n== Verificaciones finales ==")
        notifs = api(admin2, "get", f"/api/reservas?estado=Completada", "reservas completadas")
        assert any(r["IdReserva"] == state["reserva_id"] for r in notifs), "La reserva no quedó completada."
        ventas = api(admin2, "get", f"/api/ventas?origen=Web&cliente={state['cliente_id']}", "ventas web")
        assert any(v["IdVenta"] == state["web_venta_id"] for v in ventas)
        print("  · reserva completada y venta web listadas")

    print("\n✅ E2E completado sin errores.")


try:
    main()
finally:
    try:
        cleanup()
    except Exception:  # noqa: BLE001
        print("⚠️ Error durante la limpieza:")
        traceback.print_exc()
