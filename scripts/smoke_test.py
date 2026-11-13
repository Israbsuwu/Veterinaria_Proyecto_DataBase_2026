"""Smoke test de rutas HTML y API (uso local, no modifica datos salvo el carrito de sesión)."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from db import fetch_all, fetch_one  # noqa: E402

app = create_app()
app.testing = True


def check(client, method: str, url: str, label: str, **kwargs):
    try:
        response = getattr(client, method)(url, **kwargs)
        status = response.status_code
        marker = "OK " if status < 400 else "ERR"
        print(f"[{marker}] {status} {label:32s} {url}")
        if status >= 400:
            body = response.get_data(as_text=True)
            print(body[:600].replace("\n", " "))
        return response
    except Exception as error:  # noqa: BLE001
        print(f"[EXC]      {label:32s} {url} -> {error}")
        traceback.print_exc(limit=3)
        return None


print("== Anónimo ==")
with app.test_client() as client:
    check(client, "get", "/", "raíz")
    check(client, "get", "/tienda/", "tienda home")
    check(client, "get", "/tienda/catalogo", "tienda catálogo")
    check(client, "get", "/tienda/catalogo?tipo=Servicio", "tienda catálogo servicios")
    check(client, "get", "/tienda/carrito", "tienda carrito vacío")
    check(client, "get", "/tienda/login", "tienda login")
    check(client, "get", "/tienda/registro", "tienda registro")
    check(client, "get", "/login", "login interno")

    catalog = check(client, "get", "/api/tienda/catalogo", "api catálogo")
    if catalog is not None and catalog.status_code == 200:
        products = catalog.get_json()["data"]
        product = next((p for p in products if p["TipoConcepto"] == "Producto" and (p.get("Stock") or 0) > 0), None)
        if product:
            check(client, "post", "/api/tienda/carrito", "api agregar carrito",
                  json={"id_concepto": product["IdConcepto"], "cantidad": 1})
            check(client, "get", "/tienda/carrito", "tienda carrito con item")
            check(client, "get", "/tienda/checkout", "checkout sin sesión (redirige)")

print("== Cliente ==")
with app.test_client() as client:
    login = check(client, "post", "/tienda/login", "login cliente",
                  data={"correo": "cliente@pepe.com", "contrasena": "123456"}, follow_redirects=False)
    print("   login status:", login.status_code, "->", login.headers.get("Location") if login else None)
    check(client, "get", "/tienda/", "home cliente")
    check(client, "get", "/tienda/cuenta", "cuenta cliente")
    check(client, "get", "/tienda/cuenta?panel=mascotas", "cuenta mascotas")
    check(client, "get", "/tienda/reservar", "reservar cita")

    catalog = check(client, "get", "/api/tienda/catalogo", "api catálogo cliente")
    if catalog is not None and catalog.status_code == 200:
        products = catalog.get_json()["data"]
        product = next((p for p in products if p["TipoConcepto"] == "Producto" and (p.get("Stock") or 0) > 0), None)
        if product:
            check(client, "post", "/api/tienda/carrito", "api agregar carrito",
                  json={"id_concepto": product["IdConcepto"], "cantidad": 1})
            check(client, "get", "/tienda/carrito", "carrito con item")
            check(client, "get", "/tienda/checkout", "checkout cliente")

    check(client, "get", "/api/tienda/mis-compras", "api mis compras")
    check(client, "get", "/api/tienda/mis-mascotas", "api mis mascotas")
    check(client, "get", "/api/tienda/mis-reservas", "api mis reservas")
    check(client, "get", "/api/tienda/perfil", "api perfil")
    check(client, "get", "/api/tienda/notificaciones", "api notificaciones")

print("== Admin ==")
with app.test_client() as client:
    check(client, "post", "/login", "login admin",
          data={"correo": "admin@pepe.com", "contrasena": "123456"})
    for url, label in [
        ("/admin/", "tablero"),
        ("/admin/agenda", "agenda"),
        ("/admin/triaje", "triaje"),
        ("/admin/expedientes", "expedientes"),
        ("/admin/clientes", "clientes"),
        ("/admin/inventario", "inventario"),
        ("/admin/compras", "compras"),
        ("/admin/caja", "caja"),
        ("/admin/ventas", "ventas"),
        ("/admin/catalogo", "catálogo admin"),
        ("/admin/usuarios", "usuarios"),
        ("/admin/reportes", "reportes"),
    ]:
        check(client, "get", url, label)

    pets = fetch_all("SELECT TOP 3 IdMascota FROM MASCOTA ORDER BY IdMascota")
    for pet in pets:
        check(client, "get", f"/admin/expedientes/{pet['IdMascota']}", f"expediente {pet['IdMascota']}")
    clients = fetch_all("SELECT TOP 2 IdCliente FROM CLIENTE ORDER BY IdCliente")
    for item in clients:
        check(client, "get", f"/admin/clientes/{item['IdCliente']}", f"cliente {item['IdCliente']}")
    sales = fetch_all("SELECT TOP 2 IdVenta FROM VENTA ORDER BY IdVenta DESC")
    for sale in sales:
        check(client, "get", f"/admin/ventas/{sale['IdVenta']}", f"venta {sale['IdVenta']}")

print("== Datos ==")
with app.app_context():
    print("clientes:", fetch_one("SELECT COUNT(*) AS n FROM CLIENTE"))
    print("ventas:", fetch_all("SELECT TOP 5 IdVenta, Factura, Estado, Origen, IdCliente FROM VENTA ORDER BY IdVenta DESC"))
