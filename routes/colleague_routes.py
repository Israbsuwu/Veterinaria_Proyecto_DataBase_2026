"""Rutas compatibles con el frontend del compañero (avanzes-de-prueba).

Se registran con los mismos nombres de endpoint que esperan sus templates/JS,
pero reutilizan los servicios y la base de datos del ERP.
"""
from __future__ import annotations

import os
from datetime import datetime

from flask import flash, redirect, render_template, request, session, url_for

from config import Config
from db import BusinessError, get_db
from security import staff_required, client_required, current_user
from services import auth_service, billing_service, catalog_service, clinical_service, ecommerce_service
from routes.auth_routes import _start_session
from utils import to_int
from dashboard_data import (
    actualizar_estado_cita,
    cargar_catalogo,
    cargar_dashboard,
    crear_producto,
    crear_proveedor,
    obtener_factura,
    panel_vacio,
    registrar_movimiento,
)

CARPETA_PRODUCTOS = os.path.join("static", "img", "productos")
ARTE_CATEGORIAS = {}


def _limpiar(valor):
    return (valor or "").strip()


def _es_personal():
    return session.get("user_tipo") == "personal" or session.get("rol") in (Config.STAFF_ROLES or [])


def _datos_usuario():
    nombre = session.get("user_nombre", "") or ""
    apellido = session.get("user_apellido", "") or ""
    return {
        "id": session.get("user_id") or session.get("uid"),
        "nombre": nombre,
        "apellido": apellido,
        "correo": session.get("user_correo", "") or "",
        "rol": session.get("user_rol", "") or session.get("rol", "Personal") or "Personal",
        "iniciales": (nombre[:1] + apellido[:1]).upper() or "VP",
    }


def index():
    productos, categorias = [], []
    try:
        cursor = get_db().cursor()
        catalogo = cargar_catalogo(cursor)
        productos = catalogo["productos"]
        categorias = catalogo["categorias"]
        for producto in productos:
            pid = producto["id"]
            imagen = None
            for ext in ("jpg", "jpeg", "png", "webp"):
                path = os.path.join("static", "img", "productos", f"producto_{pid}.{ext}")
                if os.path.isfile(path):
                    imagen = url_for("static", filename=f"img/productos/producto_{pid}.{ext}")
                    break
            producto["imagen"] = imagen
            producto["arte"] = None
    except Exception:
        flash("No se pudo cargar el catálogo. Revisa la conexión con la base de datos.", "error")

    return render_template(
        "index.html",
        productos=productos,
        categorias=categorias,
        es_personal=_es_personal(),
    )


def login():
    if session.get("user_tipo") == "cliente":
        return redirect(url_for("index"))
    if session.get("uid") and _es_personal():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        correo = _limpiar(request.form.get("correo")).lower()
        contrasena = request.form.get("contrasena") or ""
        if not correo or not contrasena:
            flash("Escribe tu correo y tu contraseña para entrar.", "error")
            return render_template("login.html", tab="login", correo=correo, datos={}, roles=[])
        try:
            user = auth_service.authenticate(correo, contrasena, expected_role="staff")
            _start_session(user)
            flash("Bienvenido(a), %s." % user["nombre"], "success")
            return redirect(url_for("dashboard"))
        except BusinessError as error:
            flash(error.message, "danger")
    return render_template("login.html", tab="login", correo="", datos={}, roles=[])


def registro():
    if session.get("user_tipo") == "cliente":
        return redirect(url_for("index"))
    if session.get("uid") and _es_personal():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        flash("El registro de personal se gestiona desde el panel de administración.", "info")
        return redirect(url_for("login"))
    return render_template("login.html", tab="registro", correo="", datos={}, roles=[])


def cliente_login():
    if session.get("user_tipo") == "cliente":
        return redirect(url_for("index"))
    if session.get("uid") and _es_personal():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        correo = _limpiar(request.form.get("correo")).lower()
        contrasena = request.form.get("contrasena") or ""
        if not correo or not contrasena:
            flash("Escribe tu correo y tu contraseña para entrar.", "error")
            return render_template("login_cliente.html", tab="login", correo=correo, datos={}, roles=[])
        try:
            user = auth_service.authenticate(correo, contrasena, expected_role="client")
            _start_session(user)
            flash(f"¡Hola de nuevo, {user['nombre']}!", "success")
            return redirect(url_for("index"))
        except BusinessError as error:
            flash(error.message, "danger")
    return render_template("login_cliente.html", tab="login", correo="", datos={}, roles=[])


def cliente_registro():
    if session.get("user_tipo") == "cliente":
        return redirect(url_for("index"))
    if session.get("uid") and _es_personal():
        return redirect(url_for("dashboard"))

    if request.method == "GET":
        return render_template("login_cliente.html", tab="registro", correo="", datos={}, roles=[])

    datos = {
        "nombre": _limpiar(request.form.get("nombre")),
        "apellido": _limpiar(request.form.get("apellido")),
        "cedula": _limpiar(request.form.get("cedula")),
        "telefono": _limpiar(request.form.get("telefono")),
        "correo": _limpiar(request.form.get("correo")).lower(),
        "direccion": _limpiar(request.form.get("direccion")),
    }
    contrasena = request.form.get("contrasena") or ""
    confirmar = request.form.get("confirmar") or ""

    if contrasena != confirmar:
        flash("Las contraseñas no coinciden.", "error")
        return render_template("login_cliente.html", tab="registro", correo=datos["correo"], datos=datos, roles=[])

    try:
        user = ecommerce_service.register_and_login({**datos, "contrasena": contrasena})
        _start_session(user)
        flash("Tu cuenta fue creada. ¡Bienvenido a la familia Pepe & Pepito!", "success")
        return redirect(url_for("index"))
    except BusinessError as error:
        flash(error.message, "danger")
        return render_template("login_cliente.html", tab="registro", correo=datos["correo"], datos=datos, roles=[])


def mi_cuenta():
    if session.get("user_tipo") == "personal":
        return redirect(url_for("dashboard"))
    if session.get("user_tipo") != "cliente":
        return redirect(url_for("cliente_login"))
    cliente_id = session.get("cliente_id")
    if not cliente_id:
        session.clear()
        return redirect(url_for("cliente_login"))

    cliente = None
    mascotas = []
    try:
        cur = get_db().cursor()
        cur.execute(
            "SELECT Nombre, Apellido, Cedula, Telefono, Correo, Direccion FROM CLIENTE WHERE IdCliente = ?",
            (cliente_id,),
        )
        row = cur.fetchone()
        if row is None:
            session.clear()
            return redirect(url_for("cliente_login"))
        cliente = {
            "nombre": row[0],
            "apellido": row[1],
            "cedula": row[2],
            "telefono": row[3],
            "correo": row[4],
            "direccion": row[5],
        }
        cur.execute(
            """
            SELECT M.Nombre, M.Especie, M.Raza, M.Sexo, M.Color,
                   E.Condiciones, E.Obs
            FROM MASCOTA M
            LEFT JOIN EXPEDIENTE_CLINICO E ON E.IdMascota = M.IdMascota
            WHERE M.IdCliente = ?
            ORDER BY M.Nombre
            """,
            (cliente_id,),
        )
        for m in cur.fetchall():
            mascotas.append(
                {
                    "nombre": m[0],
                    "especie": m[1],
                    "raza": m[2],
                    "sexo": m[3],
                    "color": m[4] or "",
                    "condiciones": (m[5] or "").strip(),
                    "observaciones": (m[6] or "").strip(),
                }
            )
    except Exception:
        flash("No se pudo cargar tu cuenta. Revisa la conexión con la base de datos.", "error")
        return redirect(url_for("cliente_login"))

    return render_template("mi_cuenta.html", cliente=cliente, mascotas=mascotas)


def logout():
    session.clear()
    flash("Sesión finalizada.", "info")
    return redirect(url_for("login"))


def portal_clinico():
    if not _es_personal():
        if session.get("user_tipo") == "cliente":
            return redirect(url_for("index"))
        return redirect(url_for("login"))

    clientes = []
    mascotas = []
    try:
        cur = get_db().cursor()
        cur.execute(
            "SELECT IdCliente, Nombre, Apellido, Cedula, Telefono, Correo, Direccion FROM CLIENTE ORDER BY Nombre, Apellido"
        )
        for c in cur.fetchall():
            clientes.append(
                {
                    "id": c[0],
                    "nombre": c[1],
                    "apellido": c[2],
                    "cedula": c[3] or "",
                    "tel": c[4] or "",
                    "correo": c[5] or "",
                    "direccion": c[6] or "",
                }
            )
        cur.execute(
            """
            SELECT M.IdMascota, M.Nombre, M.Especie, M.Raza, M.Sexo, M.IdCliente,
                   M.Color, M.FechaNac, M.Senas,
                   E.Alergias, E.Condiciones, E.Obs
            FROM MASCOTA M
            LEFT JOIN EXPEDIENTE_CLINICO E ON E.IdMascota = M.IdMascota
            ORDER BY M.Nombre
            """
        )
        for m in cur.fetchall():
            nacimiento = ""
            if m[7]:
                try:
                    nacimiento = m[7].strftime("%Y-%m-%d")
                except Exception:
                    nacimiento = str(m[7])[:10]
            condiciones = (m[10] or "").strip() if len(m) > 10 else ""
            observaciones = (m[11] or "").strip() if len(m) > 11 else ""
            alergias = (m[9] or "").strip() if len(m) > 9 else ""
            analisis = alergias or condiciones or observaciones
            mascotas.append(
                {
                    "id": m[0],
                    "duenoId": m[5],
                    "nombre": m[1],
                    "especie": m[2] or "",
                    "raza": m[3] or "",
                    "sexo": m[4] or "",
                    "color": m[6] or "",
                    "fecha_nacimiento": nacimiento,
                    "senas": m[8] or "",
                    "condiciones": condiciones,
                    "observaciones": observaciones,
                    "analisis_alergia": analisis,
                }
            )
    except Exception:
        flash("No se pudo cargar el portal clínico. Revisa la conexión con la base de datos.", "error")

    return render_template(
        "portal_clinico.html",
        clientes=clientes,
        mascotas=mascotas,
        usuario=_datos_usuario(),
    )


def dashboard():
    try:
        cursor = get_db().cursor()
        datos = cargar_dashboard(cursor)
    except Exception:
        datos = panel_vacio("No se pudo conectar con la base de datos. Revisa que SQL Server esté encendido.")

    return render_template(
        "dashboard.html",
        usuario=_datos_usuario(),
        vista_inicial=request.args.get("vista") or "resumen",
        **datos,
    )


def dashboard_proveedor():
    if not _es_personal():
        return redirect(url_for("login"))
    if session.get("rol") not in ("Administrador", "Cajero"):
        flash("No tienes permisos para registrar proveedores.", "danger")
        return redirect(url_for("dashboard"))

    datos = {
        "nombre": _limpiar(request.form.get("nombre")),
        "telefono": _limpiar(request.form.get("telefono")),
        "correo": _limpiar(request.form.get("correo")).lower(),
        "direccion": _limpiar(request.form.get("direccion")),
    }

    errores = []
    if len(datos["nombre"]) < 3:
        errores.append("El nombre del proveedor debe tener al menos 3 caracteres.")
    # validación simple de teléfono/correo
    import re

    tel_re = __import__("re").compile(r"^[0-9+\-\s()]{8,20}$")
    correo_re = __import__("re").compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
    if datos["telefono"] and not tel_re.match(datos["telefono"]):
        errores.append("El teléfono del proveedor no tiene un formato válido.")
    if datos["correo"] and not correo_re.match(datos["correo"]):
        errores.append("El correo del proveedor no tiene un formato válido.")

    if errores:
        for mensaje in errores:
            flash(mensaje, "error")
        return redirect(url_for("dashboard", _anchor="proveedores"))

    try:
        cur = get_db().cursor()
        nombre = crear_proveedor(cur, datos)
        get_db().commit()
        flash(f"Proveedor «{nombre}» registrado correctamente.", "success")
    except ValueError as exc:
        get_db().rollback()
        flash(str(exc), "error")
    except Exception:
        get_db().rollback()
        flash("No se pudo registrar el proveedor. Revisa la conexión con la base de datos.", "error")
    return redirect(url_for("dashboard", _anchor="proveedores"))


def dashboard_producto():
    if not _es_personal():
        return redirect(url_for("login"))
    if session.get("rol") != "Administrador":
        flash("No tienes permisos para crear productos.", "danger")
        return redirect(url_for("dashboard"))

    datos = {
        "nombre": _limpiar(request.form.get("nombre")),
        "descripcion": _limpiar(request.form.get("descripcion")),
        "id_categoria": request.form.get("id_categoria"),
        "unidad": _limpiar(request.form.get("unidad")).upper() or "UNIDAD",
        "precio": request.form.get("precio"),
        "costo_compra": request.form.get("costo_compra"),
        "id_proveedor": request.form.get("id_proveedor"),
        "id_usuario": session.get("uid"),
        "stock_minimo": request.form.get("stock_minimo"),
        "controla_vencimiento": request.form.get("controla_vencimiento") in ("1", "on", "true"),
    }

    archivo = request.files.get("imagen")
    # validación básica de imagen
    if archivo is not None and archivo.filename:
        ext = os.path.splitext(archivo.filename)[1].lower().lstrip(".")
        if ext not in ("png", "jpg", "jpeg", "webp"):
            flash("La imagen debe ser JPG, PNG o WEBP.", "error")
            return redirect(url_for("dashboard", _anchor="productos"))

    try:
        cur = get_db().cursor()
        resultado = crear_producto(cur, datos)
        get_db().commit()

        if archivo is not None and archivo.filename:
            try:
                pid = resultado["producto_id"]
                ext = os.path.splitext(archivo.filename)[1].lower().lstrip(".")
                # guardar imagen
                carpeta = os.path.join("static", "img", "productos")
                os.makedirs(carpeta, exist_ok=True)
                for ex in os.listdir(carpeta):
                    if ex.lower().startswith(f"producto_{pid}."):
                        try:
                            os.remove(os.path.join(carpeta, ex))
                        except OSError:
                            pass
                archivo.save(os.path.join(carpeta, f"producto_{pid}.{ext}"))
            except Exception:
                flash("El producto se guardó, pero la imagen no se pudo almacenar.", "error")

        flash(f"Producto «{resultado['nombre']}» agregado al catálogo.", "success")
    except ValueError as exc:
        get_db().rollback()
        flash(str(exc), "error")
    except Exception:
        get_db().rollback()
        flash("No se pudo crear el producto. Revisa la conexión con la base de datos.", "error")
    return redirect(url_for("dashboard", _anchor="productos"))


def dashboard_producto_imagen(id_producto):
    if not _es_personal():
        return redirect(url_for("login"))

    archivo = request.files.get("imagen")
    if archivo is None or not archivo.filename:
        flash("Selecciona una imagen para el producto.", "error")
        return redirect(url_for("dashboard", _anchor="productos"))

    ext = os.path.splitext(archivo.filename)[1].lower().lstrip(".")
    if ext not in ("png", "jpg", "jpeg", "webp"):
        flash("La imagen debe ser JPG, PNG o WEBP.", "error")
        return redirect(url_for("dashboard", _anchor="productos"))

    try:
        cur = get_db().cursor()
        cur.execute("SELECT COUNT(*) FROM PRODUCTO WHERE IdProducto = ?", (id_producto,))
        if not cur.fetchone()[0]:
            raise ValueError("El producto seleccionado ya no existe.")
        carpeta = os.path.join("static", "img", "productos")
        os.makedirs(carpeta, exist_ok=True)
        for ex in os.listdir(carpeta):
            if ex.lower().startswith(f"producto_{id_producto}."):
                try:
                    os.remove(os.path.join(carpeta, ex))
                except OSError:
                    pass
        archivo.save(os.path.join(carpeta, f"producto_{id_producto}.{ext}"))
        flash("Imagen del producto actualizada.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    except Exception:
        flash("No se pudo guardar la imagen.", "error")
    return redirect(url_for("dashboard", _anchor="productos"))


def dashboard_movimiento():
    if not _es_personal():
        return redirect(url_for("login"))
    if session.get("rol") not in ("Administrador", "Cajero"):
        flash("No tienes permisos para registrar movimientos.", "danger")
        return redirect(url_for("dashboard"))

    try:
        id_lote = int(request.form.get("id_lote") or 0)
        cantidad = int(request.form.get("cantidad") or 0)
    except ValueError:
        flash("La cantidad o el lote no son válidos.", "error")
        return redirect(url_for("dashboard", _anchor="vencimientos"))

    tipo = _limpiar(request.form.get("tipo")).upper()
    motivo = _limpiar(request.form.get("motivo")) or "Ajuste desde el panel"

    try:
        cur = get_db().cursor()
        resultado = registrar_movimiento(cur, id_lote, tipo, cantidad, motivo, session.get("uid"))
        get_db().commit()
        flash(
            f"Movimiento registrado: {resultado['tipo'].title()} de "
            f"{resultado['cantidad']} unidades del lote {resultado['lote']} "
            f"({resultado['producto']}). Stock del lote: "
            f"{resultado['stock_anterior']} → {resultado['stock_nuevo']}.",
            "success",
        )
    except ValueError as exc:
        get_db().rollback()
        flash(str(exc), "error")
    except Exception:
        get_db().rollback()
        flash("No se pudo registrar el movimiento. Revisa la conexión con la base de datos.", "error")
    return redirect(url_for("dashboard", _anchor="vencimientos"))


def dashboard_cita_estado(id_reserva):
    if not _es_personal():
        return {"error": "No autorizado."}, 403

    datos = request.get_json(silent=True) or request.form
    estado = _limpiar(datos.get("estado")).upper()
    # colleague uses PROGRAMADA/ATENDIDA/CANCELADA; map from our states if needed
    try:
        cur = get_db().cursor()
        resultado = actualizar_estado_cita(cur, id_reserva, estado)
        get_db().commit()
        return {"success": True, "id": id_reserva, "anterior": resultado["anterior"], "estado": resultado["nuevo"]}
    except ValueError as exc:
        get_db().rollback()
        return {"error": str(exc)}, 400
    except Exception:
        get_db().rollback()
        return {"error": "No se pudo actualizar la cita."}, 500


def api_factura(id_venta):
    if not _es_personal():
        return {"error": "No autorizado."}, 403
    try:
        cur = get_db().cursor()
        factura = obtener_factura(cur, id_venta)
        if factura is None:
            return {"error": "La factura no existe."}, 404
        return factura
    except Exception:
        return {"error": "No se pudo cargar la factura."}, 500


# Portal/clinical API endpoints expected by portal.js
def api_cliente():
    if not _es_personal():
        return {"success": False, "error": "No autorizado."}, 403
    datos = request.get_json(silent=True) or {}
    try:
        cid = clinical_service.create_client(
            {
                "nombre": _limpiar(datos.get("nombre")),
                "apellido": _limpiar(datos.get("apellido")),
                "cedula": _limpiar(datos.get("cedula")),
                "telefono": _limpiar(datos.get("tel")),
                "correo": _limpiar(datos.get("correo")),
                "direccion": _limpiar(datos.get("direccion")),
            }
        )
        return {"success": True, "id": cid}
    except BusinessError as exc:
        return {"success": False, "error": exc.message}, 400
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def api_mascota():
    if not _es_personal():
        return {"success": False, "error": "No autorizado."}, 403
    datos = request.get_json(silent=True) or {}
    try:
        mid = clinical_service.create_pet(
            {
                "nombre": _limpiar(datos.get("nombre")),
                "especie": _limpiar(datos.get("especie")),
                "raza": _limpiar(datos.get("raza")) or "Criollo",
                "sexo": _limpiar(datos.get("sexo")),
                "color": _limpiar(datos.get("color")),
                "fecha_nac": _limpiar(datos.get("fecha_nacimiento")) or None,
                "senas": _limpiar(datos.get("senas")),
                "id_cliente": datos.get("duenoId"),
                "alergias": "",
            }
        )
        return {"success": True, "id": mid}
    except BusinessError as exc:
        return {"success": False, "error": exc.message}, 400
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def api_expediente_alergia():
    if not _es_personal():
        return {"success": False, "error": "No autorizado."}, 403
    datos = request.get_json(silent=True) or {}
    id_mascota = datos.get("id_mascota")
    tipo_examen = _limpiar(datos.get("tipo_examen"))
    tipo_alergia = _limpiar(datos.get("tipo_alergia"))
    animal = _limpiar(datos.get("animal"))
    observaciones = _limpiar(datos.get("observaciones"))

    if not id_mascota:
        return {"success": False, "error": "Selecciona un paciente válido."}, 400
    if not (tipo_examen or tipo_alergia or observaciones):
        return {"success": False, "error": "Indica al menos el tipo de examen, el tipo de alergia o una observación."}, 400

    partes = []
    if tipo_examen:
        partes.append(f"Tipo de examen: {tipo_examen}")
    if tipo_alergia:
        partes.append(f"Tipo de alergia: {tipo_alergia}")
    if animal:
        partes.append(f"Animal: {animal}")
    resumen = " | ".join(partes)
    condiciones = resumen[:300] if resumen else ""
    obs_texto = observaciones[:500] if observaciones else ""

    try:
        cur = get_db().cursor()
        cur.execute("SELECT COUNT(*) FROM MASCOTA WHERE IdMascota = ?", (id_mascota,))
        if not cur.fetchone()[0]:
            return {"success": False, "error": "La mascota seleccionada no existe."}, 404

        cur.execute("SELECT IdExp FROM EXPEDIENTE_CLINICO WHERE IdMascota = ?", (id_mascota,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE EXPEDIENTE_CLINICO SET Alergias = ?, Condiciones = ?, Obs = ? WHERE IdMascota = ?",
                (resumen, condiciones, obs_texto, id_mascota),
            )
        else:
            clinical_service._ensure_expediente(cur, int(id_mascota), resumen) if hasattr(clinical_service, "_ensure_expediente") else None
            cur.execute(
                "UPDATE EXPEDIENTE_CLINICO SET Alergias = ?, Condiciones = ?, Obs = ? WHERE IdMascota = ?",
                (resumen, condiciones, obs_texto, id_mascota),
            )
        get_db().commit()
        return {"success": True, "resumen": resumen, "condiciones": condiciones}
    except Exception as exc:
        get_db().rollback()
        return {"success": False, "error": str(exc)}, 500


def api_preventivos_mascota(id_mascota):
    if not _es_personal():
        return {"error": "No autorizado."}, 403
    try:
        cur = get_db().cursor()
        cur.execute(
            """
            SELECT RP.IdRegPrev, RP.TipoProc, RP.NombreProd,
                   RP.FechaAplic, RP.ProxAplic, RP.Dosis, RP.Obs,
                   RP.IdLote, RP.IdConsulta
            FROM REGISTRO_PREVENTIVO RP
            INNER JOIN EXPEDIENTE_CLINICO E ON E.IdExp = RP.IdExp
            WHERE E.IdMascota = ?
            ORDER BY RP.FechaAplic DESC, RP.IdRegPrev DESC
            """,
            (id_mascota,),
        )
        registros = []
        for r in cur.fetchall():
            registros.append(
                {
                    "id": int(r[0]),
                    "tipo": r[1] or "",
                    "producto": r[2] or "",
                    "fecha_aplicacion": r[3].strftime("%Y-%m-%d") if r[3] else "",
                    "proxima": r[4].strftime("%Y-%m-%d") if r[4] else "",
                    "dosis": r[5] or "",
                    "observaciones": r[6] or "",
                    "id_lote": r[7],
                    "id_consulta": r[8],
                }
            )
        return {"success": True, "registros": registros}
    except Exception as exc:
        return {"error": str(exc)}, 500


def api_preventivo():
    if not _es_personal():
        return {"success": False, "error": "No autorizado."}, 403
    datos = request.get_json(silent=True) or {}
    try:
        id_mascota = int(datos.get("id_mascota") or 0)
    except (TypeError, ValueError):
        id_mascota = 0

    tipo = _limpiar(datos.get("tipo_procedimiento"))
    producto = _limpiar(datos.get("producto"))
    fecha = _limpiar(datos.get("fecha_aplicacion"))
    proxima = _limpiar(datos.get("proxima_aplicacion")) or None
    dosis = _limpiar(datos.get("dosis")) or None
    observaciones = _limpiar(datos.get("observaciones")) or None

    if not id_mascota or not tipo or not fecha:
        return {"success": False, "error": "Selecciona mascota, tipo de procedimiento y fecha de aplicación."}, 400

    from datetime import date as _date

    try:
        cur = get_db().cursor()
        cur.execute("SELECT IdExp FROM EXPEDIENTE_CLINICO WHERE IdMascota = ?", (id_mascota,))
        row = cur.fetchone()
        if row:
            id_expediente = int(row[0])
        else:
            # crear expediente
            cur.execute(
                "INSERT INTO EXPEDIENTE_CLINICO (FechaApertura, EstadoReg, Alergias, IdMascota) VALUES (CAST(GETDATE() AS DATE), 'Activo', '', ?)",
                (id_mascota,),
            )
            cur.execute("SELECT IdExp FROM EXPEDIENTE_CLINICO WHERE IdMascota = ?", (id_mascota,))
            id_expediente = int(cur.fetchone()[0])

        # insert preventivo
        cur.execute(
            """
            INSERT INTO REGISTRO_PREVENTIVO (TipoProc, NombreProd, FechaAplic, ProxAplic, Dosis, Obs, IdExp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tipo, producto, fecha, proxima, dosis, observaciones, id_expediente),
        )
        get_db().commit()
        return {"success": True}
    except Exception as exc:
        get_db().rollback()
        return {"success": False, "error": str(exc)}, 500


def comprobante_tienda():
    datos = request.get_json(silent=True) or {}
    if not datos:
        try:
            import json as _json

            datos = _json.loads(request.form.get("datos") or "{}")
        except Exception:
            datos = {}

    items_raw = datos.get("items") or []
    items = []
    subtotal = 0.0
    concept_ids_present = any((it.get("id") is not None) for it in items_raw)

    # Intentar crear una venta real si el usuario es cliente y hay ids de concepto.
    venta_real = None
    if session.get("user_tipo") == "cliente":
        try:
            items_payload = []
            cur_lookup = get_db().cursor()
            for it in items_raw:
                nombre = _limpiar(it.get("nombre")) or "Producto"
                cid = it.get("id")
                # mapear id de producto a concepto facturable si es necesario
                if cid is not None:
                    # intentar por nombre (más seguro)
                    pass
                cur_lookup.execute(
                    "SELECT TOP 1 IdConcepto FROM CONCEPTO_FACTURABLE WHERE UPPER(TipoConcepto)='PRODUCTO' AND Nombre = ?",
                    (nombre,),
                )
                row = cur_lookup.fetchone()
                concept_id = row[0] if row else None
                if concept_id is None:
                    raise ValueError("concepto no encontrado")
                items_payload.append({"id_concepto": concept_id, "cantidad": it.get("cantidad", 1)})
            cur_lookup.close()

            from db import transaction

            with transaction() as cur:
                normalized = billing_service.normalize_items(cur, items_payload, allow_price_override=False)
                venta_real = billing_service.persist_sale(
                    cur,
                    cliente_id=int(session.get("cliente_id")),
                    usuario_id=int(session.get("uid")),
                    origen="Web",
                    items=normalized,
                    metodo="Tarjeta",
                    referencia=None,
                    sesion_id=None,
                )
        except Exception:
            venta_real = None
            with __import__("contextlib").nullcontext():
                pass
            # usar ecommerce_service.checkout requiere carrito en sesión; mejor persistir directo
            from db import transaction

            with transaction() as cur:
                normalized = billing_service.normalize_items(cur, items_payload, allow_price_override=False)
                venta_real = billing_service.persist_sale(
                    cur,
                    cliente_id=int(session.get("cliente_id")),
                    usuario_id=int(session.get("uid")),
                    origen="Web",
                    items=normalized,
                    metodo="Tarjeta",
                    referencia=None,
                    sesion_id=None,
                )
        except Exception:
            venta_real = None

    if venta_real:
        items = [
            {
                "nombre": it["nombre"],
                "cantidad": it["cantidad"],
                "precio": it["precio_unit"],
                "subtotal": it["subtotal"],
            }
            for it in venta_real["items"]
        ]
        subtotal = sum(it["subtotal"] for it in items)
        iva = 0.0  # nuestras ventas web no agregan IVA adicional
        total = venta_real["total"]
        numero = venta_real["factura"]
    else:
        for it in items_raw:
            try:
                cantidad = max(1, int(it.get("cantidad") or 1))
                precio = float(it.get("precio") or 0)
            except (TypeError, ValueError):
                continue
            nombre = _limpiar(it.get("nombre")) or "Producto"
            sub = round(cantidad * precio, 2)
            subtotal += sub
            items.append({"nombre": nombre, "cantidad": cantidad, "precio": precio, "subtotal": sub})

        subtotal = round(subtotal, 2)
        iva = round(subtotal * 0.15, 2)
        total = round(subtotal + iva, 2)
        numero = f"WEB-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    cliente_nombre = cliente_correo = cliente_telefono = ""
    if session.get("user_tipo") == "cliente":
        cliente_nombre = f"{session.get('user_nombre', '')} {session.get('user_apellido', '')}".strip()
        cliente_correo = session.get("user_correo") or ""
        try:
            cur = get_db().cursor()
            cur.execute("SELECT Telefono, Correo FROM CLIENTE WHERE IdCliente = ?", (session.get("cliente_id"),))
            fila = cur.fetchone()
            if fila:
                cliente_telefono = fila[0] or ""
                if not cliente_correo:
                    cliente_correo = fila[1] or ""
        except Exception:
            pass
    elif _es_personal():
        cliente_nombre = datos.get("cliente_nombre") or "Compra en mostrador"

    return render_template(
        "factura_tienda.html",
        numero=numero,
        fecha=datetime.now().strftime("%d/%m/%Y %I:%M %p"),
        items=items,
        subtotal=subtotal,
        iva=iva,
        total=total,
        cliente_nombre=cliente_nombre,
        cliente_correo=cliente_correo,
        cliente_telefono=cliente_telefono,
        atendido="Tienda en línea",
        auto_print=bool(datos.get("auto_print", True)),
    )


def register(app):
    from security import staff_required

    staff_views = {
        "portal_clinico": portal_clinico,
        "dashboard": dashboard,
        "dashboard_proveedor": dashboard_proveedor,
        "dashboard_producto": dashboard_producto,
        "dashboard_producto_imagen": dashboard_producto_imagen,
        "dashboard_movimiento": dashboard_movimiento,
        "dashboard_cita_estado": dashboard_cita_estado,
        "api_factura": api_factura,
        "api_cliente": api_cliente,
        "api_mascota": api_mascota,
        "api_expediente_alergia": api_expediente_alergia,
        "api_preventivos_mascota": api_preventivos_mascota,
        "api_preventivo": api_preventivo,
    }

    app.add_url_rule("/", endpoint="index", view_func=index)
    app.add_url_rule("/login", endpoint="login", view_func=login, methods=["GET", "POST"])
    app.add_url_rule("/registro", endpoint="registro", view_func=registro, methods=["GET", "POST"])
    app.add_url_rule("/cliente", endpoint="cliente_login", view_func=cliente_login, methods=["GET", "POST"])
    app.add_url_rule("/cliente/registro", endpoint="cliente_registro", view_func=cliente_registro, methods=["GET", "POST"])
    app.add_url_rule("/mi-cuenta", endpoint="mi_cuenta", view_func=mi_cuenta)
    app.add_url_rule("/logout", endpoint="logout", view_func=logout)
    app.add_url_rule("/portal-clinico", endpoint="portal_clinico", view_func=staff_required(portal_clinico))
    app.add_url_rule("/dashboard", endpoint="dashboard", view_func=staff_required(dashboard))
    app.add_url_rule("/dashboard/proveedor", endpoint="dashboard_proveedor", view_func=staff_required(dashboard_proveedor), methods=["POST"])
    app.add_url_rule("/dashboard/producto", endpoint="dashboard_producto", view_func=staff_required(dashboard_producto), methods=["POST"])
    app.add_url_rule("/dashboard/producto/<int:id_producto>/imagen", endpoint="dashboard_producto_imagen", view_func=staff_required(dashboard_producto_imagen), methods=["POST"])
    app.add_url_rule("/dashboard/movimiento", endpoint="dashboard_movimiento", view_func=staff_required(dashboard_movimiento), methods=["POST"])
    app.add_url_rule("/dashboard/cita/<int:id_reserva>/estado", endpoint="dashboard_cita_estado", view_func=staff_required(dashboard_cita_estado), methods=["POST"])
    app.add_url_rule("/api/factura/<int:id_venta>", endpoint="api_factura", view_func=staff_required(api_factura))
    app.add_url_rule("/api/cliente", endpoint="api_cliente", view_func=staff_required(api_cliente), methods=["POST"])
    app.add_url_rule("/api/mascota", endpoint="api_mascota", view_func=staff_required(api_mascota), methods=["POST"])
    app.add_url_rule("/api/expediente/alergia", endpoint="api_expediente_alergia", view_func=staff_required(api_expediente_alergia), methods=["POST"])
    app.add_url_rule("/api/mascota/<int:id_mascota>/preventivos", endpoint="api_preventivos_mascota", view_func=staff_required(api_preventivos_mascota))
    app.add_url_rule("/api/preventivo", endpoint="api_preventivo", view_func=staff_required(api_preventivo), methods=["POST"])
    app.add_url_rule("/tienda/comprobante", endpoint="comprobante_tienda", view_func=comprobante_tienda, methods=["POST"])
