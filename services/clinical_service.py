"""Flujo clínico: reservas, triaje, consultas, recetas y preventivos."""
from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import uuid4

from db import BusinessError, fetch_all, fetch_one, insert_returning, transaction
from services import inventory_service
from utils import parse_date, parse_datetime, to_decimal, to_int

PRIORIDADES = ("Baja", "Media", "Alta")
TIPOS_ATENCION = ("Emergencia", "Rutina", "Procedimiento")
ESTADOS_ATENCION = ("En Espera", "En Consulta", "Finalizada")
ESTADOS_RESERVA = ("Pendiente", "Confirmada", "Cancelada", "Completada")
TIPOS_PREVENTIVO = ("Vacuna", "Desparasitacion", "Vitaminas")


def _to_flag(value: Any, default: bool = True) -> int:
    """Convierte valores de formulario/JSON a 0/1 (el string "0" es falso)."""
    if value is None:
        return 1 if default else 0
    if isinstance(value, bool):
        return 1 if value else 0
    return 1 if str(value).strip().lower() in ("1", "true", "si", "sí", "on", "yes") else 0


# --------------------------------------------------------------------------
# Catálogos de apoyo
# --------------------------------------------------------------------------
def list_vets() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT V.IdVeterinario, V.NumRegistro, V.Estado, U.IdUsuario,
               U.Nombre, U.Apellido, U.Correo, U.Telefono
        FROM VETERINARIO V
        INNER JOIN USUARIO U ON U.IdUsuario = V.IdUsuario
        WHERE V.Estado = 'Activo' AND U.Estado = 'Activo'
        ORDER BY U.Nombre
        """
    )


def get_vet_by_user(usuario_id: int) -> dict[str, Any] | None:
    return fetch_one(
        "SELECT * FROM VETERINARIO WHERE IdUsuario = ? AND Estado = 'Activo'",
        (usuario_id,),
    )


def list_clients(search: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    condition = ""
    if search:
        condition = """
        WHERE (C.Nombre LIKE ? OR C.Apellido LIKE ? OR C.Cedula LIKE ?
               OR C.Correo LIKE ? OR C.Telefono LIKE ?)
        """
        like = f"%{search.strip()}%"
        params = [like] * 5
    return fetch_all(
        f"""
        SELECT C.IdCliente, C.Nombre, C.Apellido, C.Cedula, C.Telefono, C.Correo,
               C.Direccion, C.AceptaNotif, C.IdUsuario,
               (SELECT COUNT(*) FROM MASCOTA M WHERE M.IdCliente = C.IdCliente) AS Mascotas,
               (SELECT COUNT(*) FROM VENTA V WHERE V.IdCliente = C.IdCliente) AS Compras
        FROM CLIENTE C
        {condition}
        ORDER BY C.Nombre, C.Apellido
        """,
        params,
    )


def get_client(cliente_id: int) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM CLIENTE WHERE IdCliente = ?", (cliente_id,))
    if not row:
        raise BusinessError("Cliente no encontrado.", 404)
    return row


def create_client(data: dict[str, Any]) -> int:
    nombre = (data.get("nombre") or "").strip()
    apellido = (data.get("apellido") or "").strip()
    cedula = (data.get("cedula") or "").strip()
    if not all([nombre, apellido, cedula]):
        raise BusinessError("Nombre, apellido y cédula son obligatorios.")
    if fetch_one("SELECT 1 AS x FROM CLIENTE WHERE Cedula = ?", (cedula,)):
        raise BusinessError("Ya existe un cliente con esa cédula.")
    with transaction() as cur:
        return insert_returning(
            cur,
            """
            INSERT INTO CLIENTE (Nombre, Apellido, Cedula, Telefono, Correo, Direccion, AceptaNotif)
            OUTPUT INSERTED.IdCliente
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nombre,
                apellido,
                cedula,
                (data.get("telefono") or "").strip() or None,
                (data.get("correo") or "").strip() or None,
                (data.get("direccion") or "").strip() or None,
                _to_flag(data.get("acepta_notif", True)),
            ),
        )


def update_client(cliente_id: int, data: dict[str, Any]) -> None:
    current = get_client(cliente_id)
    with transaction() as cur:
        cur.execute(
            """
            UPDATE CLIENTE
            SET Nombre = ?, Apellido = ?, Telefono = ?, Correo = ?, Direccion = ?, AceptaNotif = ?
            WHERE IdCliente = ?
            """,
            (
                (data.get("nombre") or current["Nombre"]).strip(),
                (data.get("apellido") or current["Apellido"]).strip(),
                data.get("telefono", current["Telefono"]) or None,
                data.get("correo", current["Correo"]) or None,
                data.get("direccion", current["Direccion"]) or None,
                _to_flag(data.get("acepta_notif", current["AceptaNotif"])),
                cliente_id,
            ),
        )


def list_pets(cliente_id: int | None = None, search: str | None = None) -> list[dict[str, Any]]:
    conditions = ["1 = 1"]
    params: list[Any] = []
    if cliente_id:
        conditions.append("M.IdCliente = ?")
        params.append(cliente_id)
    if search:
        conditions.append("(M.Nombre LIKE ? OR M.Especie LIKE ? OR C.Nombre LIKE ? OR C.Apellido LIKE ?)")
        like = f"%{search.strip()}%"
        params.extend([like] * 4)
    return fetch_all(
        f"""
        SELECT M.*, C.Nombre + ' ' + C.Apellido AS Dueno, C.Telefono AS DuenoTelefono,
               C.Correo AS DuenoCorreo, E.IdExp, E.Alergias, E.Condiciones,
               DATEDIFF(month, M.FechaNac, GETDATE()) / 12 AS EdadAnios
        FROM MASCOTA M
        INNER JOIN CLIENTE C ON C.IdCliente = M.IdCliente
        LEFT JOIN EXPEDIENTE_CLINICO E ON E.IdMascota = M.IdMascota
        WHERE {' AND '.join(conditions)}
        ORDER BY M.Nombre
        """,
        params,
    )


def get_pet(mascota_id: int) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT M.*, C.Nombre AS ClienteNombre, C.Apellido AS ClienteApellido,
               C.Telefono AS ClienteTelefono, C.Correo AS ClienteCorreo, C.IdUsuario
        FROM MASCOTA M INNER JOIN CLIENTE C ON C.IdCliente = M.IdCliente
        WHERE M.IdMascota = ?
        """,
        (mascota_id,),
    )
    if not row:
        raise BusinessError("Mascota no encontrada.", 404)
    return row


def _ensure_expediente(cur, mascota_id: int, alergias: str | None = None) -> int:
    cur.execute("SELECT IdExp FROM EXPEDIENTE_CLINICO WHERE IdMascota = ?", (mascota_id,))
    row = cur.fetchone()
    if row:
        return int(row[0])
    return insert_returning(
        cur,
        """
        INSERT INTO EXPEDIENTE_CLINICO (FechaApertura, EstadoReg, Alergias, IdMascota)
        OUTPUT INSERTED.IdExp
        VALUES (CAST(GETDATE() AS DATE), 'Activo', ?, ?)
        """,
        (alergias or None, mascota_id),
    )


def create_pet(data: dict[str, Any]) -> int:
    cliente_id = to_int(data.get("id_cliente") or data.get("duenoId"), "cliente")
    nombre = (data.get("nombre") or "").strip()
    especie = (data.get("especie") or "").strip()
    if not nombre or not especie:
        raise BusinessError("Nombre y especie de la mascota son obligatorios.")
    if not fetch_one("SELECT 1 AS x FROM CLIENTE WHERE IdCliente = ?", (cliente_id,)):
        raise BusinessError("El cliente seleccionado no existe.")
    sexo = data.get("sexo") or None
    if sexo not in (None, "Macho", "Hembra"):
        raise BusinessError("El sexo debe ser Macho o Hembra.")
    fecha_nac = parse_date(data.get("fecha_nac"), "fecha de nacimiento", required=False)
    with transaction() as cur:
        mascota_id = insert_returning(
            cur,
            """
            INSERT INTO MASCOTA (Nombre, Especie, Raza, Sexo, Color, FechaNac, Senas, IdCliente)
            OUTPUT INSERTED.IdMascota
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nombre,
                especie,
                (data.get("raza") or "").strip() or None,
                sexo,
                (data.get("color") or "").strip() or None,
                fecha_nac,
                (data.get("senas") or "").strip() or None,
                cliente_id,
            ),
        )
        _ensure_expediente(cur, mascota_id, (data.get("alergias") or "").strip() or None)
    return mascota_id


def update_pet(mascota_id: int, data: dict[str, Any]) -> None:
    current = get_pet(mascota_id)
    with transaction() as cur:
        cur.execute(
            """
            UPDATE MASCOTA
            SET Nombre = ?, Especie = ?, Raza = ?, Sexo = ?, Color = ?, FechaNac = ?, Senas = ?
            WHERE IdMascota = ?
            """,
            (
                (data.get("nombre") or current["Nombre"]).strip(),
                (data.get("especie") or current["Especie"]).strip(),
                data.get("raza", current["Raza"]) or None,
                data.get("sexo", current["Sexo"]) or None,
                data.get("color", current["Color"]) or None,
                parse_date(data.get("fecha_nac") or current["FechaNac"], "fecha de nacimiento", required=False),
                data.get("senas", current["Senas"]) or None,
                mascota_id,
            ),
        )
        exp = cur.execute("SELECT IdExp FROM EXPEDIENTE_CLINICO WHERE IdMascota = ?", (mascota_id,)).fetchone()
        if exp and "alergias" in data:
            cur.execute(
                "UPDATE EXPEDIENTE_CLINICO SET Alergias = ? WHERE IdExp = ?",
                ((data.get("alergias") or "").strip() or None, exp[0]),
            )


# --------------------------------------------------------------------------
# Reservas
# --------------------------------------------------------------------------
def list_reservations(
    fecha: dt.date | None = None,
    estado: str | None = None,
    cliente_id: int | None = None,
    desde: dt.date | None = None,
    hasta: dt.date | None = None,
) -> list[dict[str, Any]]:
    conditions = ["1 = 1"]
    params: list[Any] = []
    if fecha:
        conditions.append("CAST(R.FechaIni AS DATE) = ?")
        params.append(fecha)
    if desde:
        conditions.append("CAST(R.FechaIni AS DATE) >= ?")
        params.append(desde)
    if hasta:
        conditions.append("CAST(R.FechaIni AS DATE) <= ?")
        params.append(hasta)
    if estado:
        conditions.append("R.Estado = ?")
        params.append(estado)
    if cliente_id:
        conditions.append("R.IdCliente = ?")
        params.append(cliente_id)
    return fetch_all(
        f"""
        SELECT R.*, C.Nombre + ' ' + C.Apellido AS Cliente, C.Telefono AS ClienteTelefono,
               C.Correo AS ClienteCorreo,
               M.Nombre AS Mascota, M.Especie,
               V.IdVeterinario, U.Nombre + ' ' + U.Apellido AS Veterinario,
               (SELECT COUNT(*) FROM ATENCION A WHERE A.IdReserva = R.IdReserva) AS Atenciones
        FROM RESERVA R
        INNER JOIN CLIENTE C ON C.IdCliente = R.IdCliente
        LEFT JOIN MASCOTA M ON M.IdMascota = R.IdMascota
        LEFT JOIN VETERINARIO V ON V.IdVeterinario = R.IdVeterinario
        LEFT JOIN USUARIO U ON U.IdUsuario = V.IdUsuario
        WHERE {' AND '.join(conditions)}
        ORDER BY R.FechaIni DESC
        """,
        params,
    )


def create_reservation(data: dict[str, Any], actor: dict[str, Any]) -> int:
    is_client = actor.get("rol") == "Cliente Web"
    cliente_id = actor.get("cliente_id") if is_client else (data.get("id_cliente") or data.get("clienteId"))
    cliente_id = to_int(cliente_id, "cliente")

    fecha_ini = parse_datetime(data.get("fecha_ini") or data.get("fechaIni"), "fecha de inicio")
    fecha_fin = parse_datetime(data.get("fecha_fin") or data.get("fechaFin"), "fecha de fin", required=False)
    if not fecha_fin:
        fecha_fin = fecha_ini + dt.timedelta(minutes=30)
    if fecha_fin <= fecha_ini:
        raise BusinessError("La fecha de fin debe ser posterior a la fecha de inicio.")

    if not get_client(cliente_id):
        raise BusinessError("Cliente no encontrado.", 404)

    mascota_id = data.get("id_mascota") or data.get("mascotaId")
    if mascota_id:
        mascota_id = to_int(mascota_id, "mascota")
        mascota = fetch_one(
            "SELECT IdMascota, IdCliente FROM MASCOTA WHERE IdMascota = ?", (mascota_id,)
        )
        if not mascota:
            raise BusinessError("Mascota no encontrada.")
        if int(mascota["IdCliente"]) != cliente_id:
            raise BusinessError("La mascota no pertenece a ese cliente.")
    else:
        mascota_id = None

    veterinario_id = data.get("id_veterinario") or data.get("veterinarioId") or None
    if veterinario_id:
        veterinario_id = to_int(veterinario_id, "veterinario")
        if not fetch_one(
            "SELECT 1 AS x FROM VETERINARIO WHERE IdVeterinario = ? AND Estado = 'Activo'",
            (veterinario_id,),
        ):
            raise BusinessError("El veterinario seleccionado no está disponible.")
    else:
        veterinario_id = None

    motivo = (data.get("motivo") or "Consulta general").strip()
    canal = (data.get("canal") or ("Web" if is_client else "Presencial")).strip()
    estado = (data.get("estado") or ("Pendiente" if is_client else "Confirmada")).strip()
    if estado not in ESTADOS_RESERVA:
        raise BusinessError("Estado de reserva inválido.")

    with transaction() as cur:
        reserva_id = insert_returning(
            cur,
            """
            INSERT INTO RESERVA (FechaIni, FechaFin, Canal, Motivo, Estado, Obs, IdCliente, IdMascota, IdVeterinario)
            OUTPUT INSERTED.IdReserva
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fecha_ini,
                fecha_fin,
                canal,
                motivo[:255],
                estado,
                (data.get("obs") or "").strip() or None,
                cliente_id,
                mascota_id,
                veterinario_id,
            ),
        )
        cur.execute(
            """
            INSERT INTO NOTIFICACION (Tipo, Canal, FechaProg, Estado, Clave, IdCliente, IdReserva)
            VALUES ('Cita', 'Correo', ?, 'Pendiente', ?, ?, ?)
            """,
            (
                fecha_ini - dt.timedelta(days=1),
                f"RES-{reserva_id}-{uuid4().hex[:6]}",
                cliente_id,
                reserva_id,
            ),
        )
    return reserva_id


def update_reservation_state(reserva_id: int, estado: str) -> None:
    if estado not in ESTADOS_RESERVA:
        raise BusinessError("Estado de reserva inválido.")
    reserva = fetch_one("SELECT * FROM RESERVA WHERE IdReserva = ?", (reserva_id,))
    if not reserva:
        raise BusinessError("Reserva no encontrada.", 404)
    with transaction() as cur:
        cur.execute(
            "UPDATE RESERVA SET Estado = ? WHERE IdReserva = ?",
            (estado, reserva_id),
        )
        if estado in ("Cancelada", "Completada"):
            cur.execute(
                "UPDATE NOTIFICACION SET Estado = 'Fallida' WHERE IdReserva = ? AND Estado = 'Pendiente'",
                (reserva_id,),
            )


def check_in(reserva_id: int, data: dict[str, Any], actor: dict[str, Any]) -> int:
    reserva = fetch_one("SELECT * FROM RESERVA WHERE IdReserva = ?", (reserva_id,))
    if not reserva:
        raise BusinessError("Reserva no encontrada.", 404)
    if reserva["Estado"] in ("Cancelada", "Completada"):
        raise BusinessError("No se puede hacer check-in de una reserva cancelada o completada.")

    existente = fetch_one(
        "SELECT IdAtencion FROM ATENCION WHERE IdReserva = ? AND Estado <> 'Finalizada'",
        (reserva_id,),
    )
    if existente:
        raise BusinessError("Esta reserva ya tiene una atención en curso.")

    veterinario_id = data.get("id_veterinario") or reserva["IdVeterinario"]
    if not veterinario_id and actor.get("rol") == "Veterinario":
        vet = get_vet_by_user(actor["id"])
        veterinario_id = vet["IdVeterinario"] if vet else None
    if not veterinario_id:
        vets = list_vets()
        if not vets:
            raise BusinessError("No hay veterinarios activos para asignar la atención.")
        veterinario_id = vets[0]["IdVeterinario"]
    veterinario_id = to_int(veterinario_id, "veterinario")

    tipo = data.get("tipo_atencion") or "Rutina"
    prioridad = data.get("prioridad") or "Media"
    if tipo not in TIPOS_ATENCION:
        raise BusinessError("Tipo de atención inválido.")
    if prioridad not in PRIORIDADES:
        raise BusinessError("Prioridad inválida.")

    with transaction() as cur:
        atencion_id = insert_returning(
            cur,
            """
            INSERT INTO ATENCION (TipoAtencion, FechaLleg, MotivoRep, Prioridad, Estado, IdReserva, IdMascota, IdVeterinario)
            OUTPUT INSERTED.IdAtencion
            VALUES (?, GETDATE(), ?, ?, 'En Espera', ?, ?, ?)
            """,
            (
                tipo,
                (reserva["Motivo"] or data.get("motivo") or "Consulta")[:255],
                prioridad,
                reserva_id,
                reserva["IdMascota"],
                veterinario_id,
            ),
        )
        cur.execute("UPDATE RESERVA SET Estado = 'Confirmada' WHERE IdReserva = ?", (reserva_id,))
    return atencion_id


# --------------------------------------------------------------------------
# Atenciones / triaje
# --------------------------------------------------------------------------
def list_attentions(estado: str | None = None, fecha: dt.date | None = None) -> list[dict[str, Any]]:
    conditions = ["1 = 1"]
    params: list[Any] = []
    if estado:
        conditions.append("A.Estado = ?")
        params.append(estado)
    if fecha:
        conditions.append("CAST(A.FechaLleg AS DATE) = ?")
        params.append(fecha)
    return fetch_all(
        f"""
        SELECT A.*, M.Nombre AS Mascota, M.Especie, M.Raza, M.IdCliente,
               C.Nombre + ' ' + C.Apellido AS Cliente, C.Telefono AS ClienteTelefono,
               U.Nombre + ' ' + U.Apellido AS Veterinario, V.NumRegistro,
               CM.IdConsulta, E.IdExp, E.Alergias
        FROM ATENCION A
        INNER JOIN MASCOTA M ON M.IdMascota = A.IdMascota
        INNER JOIN CLIENTE C ON C.IdCliente = M.IdCliente
        INNER JOIN VETERINARIO V ON V.IdVeterinario = A.IdVeterinario
        INNER JOIN USUARIO U ON U.IdUsuario = V.IdUsuario
        LEFT JOIN CONSULTA_MEDICA CM ON CM.IdAtencion = A.IdAtencion
        LEFT JOIN EXPEDIENTE_CLINICO E ON E.IdMascota = M.IdMascota
        WHERE {' AND '.join(conditions)}
        ORDER BY CASE A.Prioridad WHEN 'Alta' THEN 1 WHEN 'Media' THEN 2 ELSE 3 END,
                 A.FechaLleg ASC
        """,
        params,
    )


def create_attention(data: dict[str, Any], actor: dict[str, Any]) -> int:
    mascota_id = to_int(data.get("id_mascota") or data.get("mascotaId"), "mascota")
    pet = get_pet(mascota_id)
    motivo = (data.get("motivo") or "").strip()
    if not motivo:
        raise BusinessError("El motivo de la atención es obligatorio.")
    tipo = data.get("tipo_atencion") or "Rutina"
    prioridad = data.get("prioridad") or "Media"
    if tipo not in TIPOS_ATENCION:
        raise BusinessError("Tipo de atención inválido.")
    if prioridad not in PRIORIDADES:
        raise BusinessError("Prioridad inválida.")

    veterinario_id = data.get("id_veterinario")
    if not veterinario_id and actor.get("rol") == "Veterinario":
        vet = get_vet_by_user(actor["id"])
        veterinario_id = vet["IdVeterinario"] if vet else None
    if not veterinario_id:
        vets = list_vets()
        if not vets:
            raise BusinessError("No hay veterinarios activos.")
        veterinario_id = vets[0]["IdVeterinario"]
    veterinario_id = to_int(veterinario_id, "veterinario")

    with transaction() as cur:
        atencion_id = insert_returning(
            cur,
            """
            INSERT INTO ATENCION (TipoAtencion, FechaLleg, MotivoRep, Prioridad, Estado, IdMascota, IdVeterinario)
            OUTPUT INSERTED.IdAtencion
            VALUES (?, GETDATE(), ?, ?, 'En Espera', ?, ?)
            """,
            (tipo, motivo[:255], prioridad, mascota_id, veterinario_id),
        )
        _ensure_expediente(cur, pet["IdMascota"])
    return atencion_id


def update_attention_state(atencion_id: int, estado: str) -> None:
    if estado not in ESTADOS_ATENCION:
        raise BusinessError("Estado de atención inválido.")
    if not fetch_one("SELECT 1 AS x FROM ATENCION WHERE IdAtencion = ?", (atencion_id,)):
        raise BusinessError("Atención no encontrada.", 404)
    with transaction() as cur:
        cur.execute("UPDATE ATENCION SET Estado = ? WHERE IdAtencion = ?", (estado, atencion_id))


# --------------------------------------------------------------------------
# Consulta médica
# --------------------------------------------------------------------------
def register_consultation(data: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    atencion_id = to_int(data.get("id_atencion") or data.get("atencionId"), "atención")
    atencion = fetch_one(
        """
        SELECT A.*, M.IdCliente, M.Nombre AS Mascota
        FROM ATENCION A INNER JOIN MASCOTA M ON M.IdMascota = A.IdMascota
        WHERE A.IdAtencion = ?
        """,
        (atencion_id,),
    )
    if not atencion:
        raise BusinessError("Atención no encontrada.", 404)
    if atencion["Estado"] == "Finalizada":
        raise BusinessError("Esta atención ya fue finalizada con una consulta.")

    veterinario_id = atencion["IdVeterinario"]
    if actor.get("rol") == "Veterinario":
        vet = get_vet_by_user(actor["id"])
        if vet:
            veterinario_id = vet["IdVeterinario"]
    elif data.get("id_veterinario"):
        veterinario_id = to_int(data.get("id_veterinario"), "veterinario")

    peso = to_decimal(data.get("peso"), "peso")
    motivo = (data.get("motivo") or atencion["MotivoRep"] or "").strip()
    diagnostico = (data.get("diagnostico") or "").strip()
    tratamiento = (data.get("tratamiento") or "").strip()
    if peso <= 0:
        raise BusinessError("El peso debe ser mayor que cero.")
    if not diagnostico:
        raise BusinessError("El diagnóstico es obligatorio.")
    if not tratamiento:
        raise BusinessError("El tratamiento es obligatorio.")

    receta_items = data.get("receta") or []
    preventivos = data.get("preventivos") or []
    if not receta_items and data.get("farmaco"):
        receta_items = [
            {
                "nombre_med": data.get("farmaco"),
                "dosis": data.get("dosis") or "Según indicación",
                "frecuencia": data.get("frecuencia") or "Según indicación",
                "duracion": data.get("duracion") or "Según indicación",
                "via": data.get("via") or "Oral",
                "indicaciones": data.get("indicaciones_receta"),
            }
        ]

    result: dict[str, Any] = {}
    with transaction() as cur:
        exp_id = _ensure_expediente(cur, atencion["IdMascota"])
        consulta_id = insert_returning(
            cur,
            """
            INSERT INTO CONSULTA_MEDICA
                (FechaCons, Peso, Motivo, Diagnostico, Tratamiento, Obs, IdExp, IdAtencion)
            OUTPUT INSERTED.IdConsulta
            VALUES (GETDATE(), ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                peso,
                motivo[:255],
                diagnostico,
                tratamiento,
                (data.get("obs") or "").strip() or None,
                exp_id,
                atencion_id,
            ),
        )
        result["id_consulta"] = consulta_id

        if receta_items:
            receta_id = insert_returning(
                cur,
                """
                INSERT INTO RECETA_MEDICA (FechaEmision, IndGral, Estado, IdConsulta)
                OUTPUT INSERTED.IdReceta
                VALUES (GETDATE(), ?, 'Vigente', ?)
                """,
                ((data.get("indicaciones_generales") or "").strip() or None, consulta_id),
            )
            result["id_receta"] = receta_id
            for item in receta_items:
                nombre_med = (item.get("nombre_med") or item.get("nombre") or "").strip()
                if not nombre_med:
                    continue
                id_producto = item.get("id_producto")
                if id_producto in ("", "null"):
                    id_producto = None
                cur.execute(
                    """
                    INSERT INTO DETALLE_RECETA
                        (NombreMed, Dosis, Frecuencia, Duracion, Via, Ind, IdReceta, IdProducto)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        nombre_med[:150],
                        (item.get("dosis") or "Según indicación")[:100],
                        (item.get("frecuencia") or "Según indicación")[:100],
                        (item.get("duracion") or "Según indicación")[:100],
                        (item.get("via") or "Oral")[:50],
                        (item.get("indicaciones") or item.get("ind") or "").strip() or None,
                        receta_id,
                        to_int(id_producto, "producto") if id_producto else None,
                    ),
                )

        preventivos_creados: list[dict[str, Any]] = []
        for item in preventivos:
            tipo_proc = (item.get("tipo_proc") or item.get("tipo") or "Vacuna").strip()
            if tipo_proc not in TIPOS_PREVENTIVO:
                raise BusinessError(f"Tipo de preventivo inválido: {tipo_proc}")
            nombre_prod = (item.get("nombre_prod") or item.get("nombre") or "").strip()
            if not nombre_prod:
                raise BusinessError("El nombre del producto preventivo es obligatorio.")
            fecha_aplic = parse_date(item.get("fecha_aplic") or dt.date.today(), "fecha de aplicación")
            prox_aplic = parse_date(item.get("prox_aplic"), "próxima aplicación", required=False)
            lote_id = item.get("id_lote")
            lote_id = to_int(lote_id, "lote") if lote_id not in (None, "", "null") else None
            producto_id = item.get("id_producto")
            producto_id = to_int(producto_id, "producto") if producto_id not in (None, "", "null") else None
            cantidad = to_int(item.get("cantidad"), "cantidad", default=1)
            descontar = bool(item.get("descontar_inventario", producto_id is not None))

            if producto_id and descontar:
                movimientos = inventory_service.consume_fefo(
                    cur,
                    producto_id,
                    cantidad,
                    actor["id"],
                    f"Aplicación clínica: {nombre_prod} (consulta #{consulta_id})",
                    lote_id=lote_id,
                )
                if movimientos and not lote_id:
                    lote_id = movimientos[0]["id_lote"]

            reg_prev_id = insert_returning(
                cur,
                """
                INSERT INTO REGISTRO_PREVENTIVO
                    (TipoProc, NombreProd, FechaAplic, ProxAplic, Dosis, Obs, IdExp, IdConsulta, IdLote)
                OUTPUT INSERTED.IdRegPrev
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tipo_proc,
                    nombre_prod[:150],
                    fecha_aplic,
                    prox_aplic,
                    (item.get("dosis") or "").strip() or None,
                    (item.get("obs") or "").strip() or None,
                    exp_id,
                    consulta_id,
                    lote_id,
                ),
            )
            preventivos_creados.append({"id_reg_prev": reg_prev_id, "nombre": nombre_prod})

            if prox_aplic:
                cur.execute(
                    """
                    INSERT INTO NOTIFICACION
                        (Tipo, Canal, FechaProg, Estado, Clave, IdCliente, IdRegPrev)
                    VALUES (?, 'Correo', ?, 'Pendiente', ?, ?, ?)
                    """,
                    (
                        "Recordatorio Vacuna" if tipo_proc == "Vacuna" else "Aviso",
                        dt.datetime.combine(prox_aplic, dt.time(9, 0)),
                        f"PREV-{reg_prev_id}-{uuid4().hex[:6]}",
                        atencion["IdCliente"],
                        reg_prev_id,
                    ),
                )

        result["preventivos"] = preventivos_creados

        cur.execute("UPDATE ATENCION SET Estado = 'Finalizada' WHERE IdAtencion = ?", (atencion_id,))
        if atencion["IdReserva"]:
            cur.execute(
                "UPDATE RESERVA SET Estado = 'Completada' WHERE IdReserva = ?",
                (atencion["IdReserva"],),
            )
    return result


def get_expediente(mascota_id: int) -> dict[str, Any]:
    pet = get_pet(mascota_id)
    exp = fetch_one("SELECT * FROM EXPEDIENTE_CLINICO WHERE IdMascota = ?", (mascota_id,))
    consultas = fetch_all(
        """
        SELECT CM.*, A.TipoAtencion, A.Prioridad, A.FechaLleg, A.Estado AS EstadoAtencion,
               U.Nombre + ' ' + U.Apellido AS Veterinario,
               R.IdReceta, R.Estado AS EstadoReceta, R.IndGral
        FROM CONSULTA_MEDICA CM
        INNER JOIN ATENCION A ON A.IdAtencion = CM.IdAtencion
        INNER JOIN VETERINARIO V ON V.IdVeterinario = A.IdVeterinario
        INNER JOIN USUARIO U ON U.IdUsuario = V.IdUsuario
        LEFT JOIN RECETA_MEDICA R ON R.IdConsulta = CM.IdConsulta
        WHERE CM.IdExp = ?
        ORDER BY CM.FechaCons DESC
        """,
        (exp["IdExp"],) if exp else (0,),
    )

    if consultas:
        ids = [c["IdConsulta"] for c in consultas]
        placeholders = ",".join("?" for _ in ids)
        recetas = fetch_all(
            f"SELECT * FROM RECETA_MEDICA WHERE IdConsulta IN ({placeholders})",
            ids,
        )
        if recetas:
            rec_ids = [r["IdReceta"] for r in recetas]
            rec_placeholders = ",".join("?" for _ in rec_ids)
            detalles = fetch_all(
                f"SELECT * FROM DETALLE_RECETA WHERE IdReceta IN ({rec_placeholders})",
                rec_ids,
            )
            for rec in recetas:
                rec["detalles"] = [d for d in detalles if d["IdReceta"] == rec["IdReceta"]]
        for consulta in consultas:
            consulta["receta"] = next(
                (r for r in recetas if r["IdConsulta"] == consulta["IdConsulta"]), None
            )
        preventivos = fetch_all(
            f"""
            SELECT RP.*, L.CodigoLote
            FROM REGISTRO_PREVENTIVO RP
            LEFT JOIN LOTE L ON L.IdLote = RP.IdLote
            WHERE RP.IdConsulta IN ({placeholders})
            ORDER BY RP.FechaAplic DESC
            """,
            ids,
        )
        for consulta in consultas:
            consulta["preventivos"] = [
                p for p in preventivos if p["IdConsulta"] == consulta["IdConsulta"]
            ]

    pesos = [float(c["Peso"]) for c in reversed(consultas)] if consultas else []
    return {
        "mascota": pet,
        "expediente": exp,
        "consultas": consultas,
        "pesos": pesos,
        "vacunas": fetch_all(
            """
            SELECT RP.*, L.CodigoLote
            FROM REGISTRO_PREVENTIVO RP
            LEFT JOIN LOTE L ON L.IdLote = RP.IdLote
            WHERE RP.IdExp = ?
            ORDER BY RP.FechaAplic DESC
            """,
            (exp["IdExp"],) if exp else (0,),
        ),
    }
