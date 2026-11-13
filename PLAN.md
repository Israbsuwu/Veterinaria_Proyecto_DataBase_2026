# Plan de ejecución — VetPepePepito

Plan aplicado para convertir el prototipo de una sola página en un sistema dual (ERP interno + tienda en línea) compartiendo base de datos y API.

---

## Fase 0 — Análisis

- [x] Revisar el directorio: `app.py`, `Vet_BDD.sql`, plantillas y assets existentes.
- [x] Identificar la paleta y el estilo visual heredados.
- [x] Inspeccionar la base viva `VetPepePepito` en `MSI\SQLEXPRESS` (28 entidades).
- [x] Detectar inconsistencias: cliente sin usuario, producto sin concepto facturable, pagos web sin caja.

## Fase 1 — Base de datos

- [x] Crear `sql/001_ecommerce_y_ajustes.sql` idempotente.
- [x] Agregar `CLIENTE.IdUsuario` (FK nullable/única) y su índice.
- [x] Agregar `PRODUCTO.IdConcepto` para herencia de `CONCEPTO_FACTURABLE`.
- [x] Hacer nullable `PAGO.IdSesion` para cobros web.
- [x] Agregar `VENTA.Origen` (`POS` / `Web`).
- [x] Crear roles `Cajero` y `Cliente Web` y 17 permisos con sus mapeos.
- [x] Crear índices de rendimiento y vistas `VW_STOCK_PRODUCTO` / `VW_LOTE_STOCK`.
- [x] Sembrar usuarios demo, vínculo cliente↔usuario y stock inicial del lote de ejemplo.
- [x] Aplicar la migración con `scripts/run_sql.py` y verificar FK, stock, roles y vistas.

## Fase 2 — Infraestructura backend

- [x] `config.py`: configuración por entorno y cadena ODBC.
- [x] `db.py`: conexión por request, helpers y contexto transaccional.
- [x] `security.py`: sesión, roles, hashing y redirecciones seguras.
- [x] `utils.py`: formato de dinero/fechas y serialización JSON de `Decimal`/fechas.
- [x] `app.py`: fábrica, blueprints, filtros Jinja, contexto global y manejo de errores.

## Fase 3 — Servicios de negocio

- [x] `auth_service`: autenticación staff/cliente, registro y cambio de contraseña.
- [x] `catalog_service`: productos, servicios, categorías y conceptos.
- [x] `inventory_service`: lotes, FEFO, compras, salidas, ajustes y alertas.
- [x] `clinical_service`: reserva → check-in → atención → consulta → preventivo.
- [x] `billing_service`: caja, ventas POS, numeración, pagos y anulación.
- [x] `ecommerce_service`: carrito, checkout y datos de cuenta.
- [x] `dashboard_service`: indicadores del tablero y reportes.

## Fase 4 — API y rutas HTML

- [x] `api_routes.py`: endpoints JSON para ambos frontends, con control de rol.
- [x] `admin_routes.py`: vistas del ERP con datos serializables.
- [x] `shop_routes.py`: vistas de la tienda y detalle de pedido.
- [x] `auth_routes.py`: accesos separados para personal y clientes.
- [x] Manejo uniforme de errores de negocio (JSON o flash + redirect).

## Fase 5 — ERP interno

- [x] Layout y navegación del personal.
- [x] Tablero, agenda, triaje, expedientes y detalle de expediente.
- [x] Clientes, detalle de cliente y mascotas.
- [x] Inventario, compras y caja.
- [x] Ventas, detalle de venta y anulación.
- [x] Catálogo, usuarios y reportes.
- [x] Assets compartidos `admin.css`, `admin.js`, `common.js`.

## Fase 6 — Tienda en línea

- [x] Layout, navegación, carrito en badge, flashes y footer.
- [x] Inicio con categorías, servicios y destacados.
- [x] Catálogo con búsqueda, filtros y tarjetas.
- [x] Carrito con cantidades, eliminación y totales en vivo.
- [x] Checkout con método de pago y referencia.
- [x] Cuenta con pestañas de perfil, mascotas, pedidos, citas y avisos.
- [x] Reserva de citas y detalle de pedido.
- [x] Login y registro de clientes.
- [x] Tema claro propio en `shop.css` manteniendo la paleta de la clínica.

## Fase 7 — Verificación

- [x] Smoke test de rutas públicas, de tienda y de admin (200/302 esperados).
- [x] E2E: registro, mascota, perfil, reserva web, check-in, consulta.
- [x] E2E: preventivo con descuento FEFO y notificación.
- [x] E2E: apertura de caja, venta POS (producto + servicio), cálculo de cambio.
- [x] E2E: anulación con reposición de stock y cierre de caja.
- [x] E2E: compra a proveedor con lote nuevo.
- [x] E2E: checkout web, pedido con `IdSesion = NULL`, listados completados.
- [x] Limpieza de datos de prueba y restauración del stock base.
- [x] Verificación en navegador: inicio, catálogo, carrito, cantidades, eliminación, checkout, cuenta y reserva.
- [x] Corregir pérdida del carrito al iniciar sesión y el `?` sobrante en `next`.

---

## Correcciones aplicadas durante la verificación

- [x] Carrito de invitado se conserva al autenticarse (`_start_session`).
- [x] Redirección de login sin `?` final (`security._next_path`).
- [x] Serialización de `Decimal`/fechas antes de `|tojson`.
- [x] `TOP (CAST(? AS INT))` y orden correcto de parámetros en listados.
- [x] Lectura consistente de banderas `"0"`/`"1"` en clientes.
- [x] Contraseñas planas heredadas migradas a hash al iniciar sesión.
- [x] Notificaciones con `Clave` única para evitar el problema de índice único con `NULL`.

---

## Roadmap recomendado

- [ ] **CSRF** en formularios y llamadas mutables (Flask-WTF o token propio).
- [ ] Envío real de correos para citas, pedidos y recordatorios de vacunas.
- [ ] Pasarela de pago real (tarjeta/transferencia) y conciliación.
- [ ] Recuperación de contraseña por correo.
- [ ] Paginación y exportación (CSV/PDF) en ventas, inventario y expedientes.
- [ ] Bitácora de auditoría de acciones sensibles (anulaciones, ajustes, usuarios).
- [ ] Pruebas automatizadas con `pytest` y datos de prueba aislados.
- [ ] Servidor WSGI (Waitress/Gunicorn) + HTTPS para despliegue.
- [ ] Respaldos programados de SQL Server y monitoreo de errores.
